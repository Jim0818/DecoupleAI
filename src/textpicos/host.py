"""Native host handoff. The host performs spawn/stop; this module records facts."""
from __future__ import annotations

import os
from pathlib import Path
import stat

from textpicos.context import assemble_context, context_prompt, normalize_input_reference
from textpicos.runtime.storage import atomic_json


def checked_ref(paths, value, *, exclusions=(), must_exist=False):
    """Check a selected runtime file before probing it; never walk directories."""
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError('A nonempty project file reference is required')
    root = Path(paths.root)
    ref = Path(value).expanduser()
    if '..' in ref.parts:
        raise ValueError(f'Parent traversal is not an input or write scope: {value}')
    path = Path(os.path.abspath(ref if ref.is_absolute() else root / ref))
    if not path.is_relative_to(root):
        raise ValueError(f'Runtime file reference is outside the project: {value}')
    relative = path.relative_to(root)
    if os.environ.get('TEXTPICOS_MAINTENANCE_SCOPE') == 'system' and 'articles' in {
        part.casefold() for part in relative.parts
    }:
        raise ValueError(f'Reference is excluded by this maintenance scope: {value}')
    for excluded in exclusions:
        boundary = Path(excluded)
        boundary = Path(os.path.abspath(boundary if boundary.is_absolute() else root / boundary))
        selected, protected = str(path).casefold(), str(boundary).casefold()
        if selected == protected or selected.startswith(protected + os.sep):
            raise ValueError(f'Reference is excluded by this maintenance scope: {value}')
    # Runtime file CAS rejects symlink components. Match that rule before the
    # context assembler can resolve a user-selected link to an external target.
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise ValueError(f'Runtime file reference contains a symlink: {value}')
    if must_exist and not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def validate_task_paths(paths, task, *, exclusions=()):
    """Validate future input/output references without requiring them to exist."""
    inputs = task.get('inputs') if task.get('inputs') is not None else task.get('input_refs', [])
    writes = task.get('write_scopes') if task.get('write_scopes') is not None else task.get('allowed_write_roots', [])
    for name, values in (('input_refs', inputs), ('allowed_write_roots', writes),
                         ('deliverables', task.get('deliverables', []))):
        if not isinstance(values, (list, tuple)):
            raise ValueError(f'{name} must be a list of project file references')
        for value in values:
            if name == 'input_refs':
                value = normalize_input_reference(value)
            checked_ref(paths, value.get('path') if isinstance(value, dict) else value,
                        exclusions=exclusions)


def prepare_dispatch(paths, runtime, run_id, task_id, *, host_id=None, exclusions=()):
    if host_id is not None and (not isinstance(host_id, str) or not host_id.strip()):
        raise ValueError('host_id must identify an actual host execution')
    task = runtime.task(run_id, task_id)
    state = runtime.status(run_id)
    task.setdefault('account_id', state.get('metadata', {}).get('account_id'))
    if not task.get('account_id'):
        task['account_id'] = state.get('metadata', {}).get('account_id')
    validate_task_paths(paths, task, exclusions=exclusions)
    # Preflight methods only: missing future inputs are the runtime's dependency
    # and blocked-state decision, not a reason to reject a planned task.
    assemble_context(paths, {**task, 'input_refs': []}, exclusions=exclusions)
    dispatch = runtime.dispatch(run_id, task_id, host_id=host_id)
    stage = Path(dispatch['staging_dir'])
    try:
        # A supervisor may have adjusted the task after preflight. Assemble the
        # exact snapshot authorized by dispatch, never that earlier task copy.
        task = dispatch['task']
        if not task.get('account_id'):
            task['account_id'] = state.get('metadata', {}).get('account_id')
        validate_task_paths(paths, task, exclusions=exclusions)
        context = assemble_context(paths, task, exclusions=exclusions)
        return _write_handoff(runtime, run_id, task_id, dispatch, context, stage)
    except Exception as exc:
        try:
            runtime.fail(run_id, task_id, dispatch['token'], reason=f'Could not prepare host handoff: {exc}')
        except Exception as fence:
            # A concurrent cancel/revision owns that newer state.
            if getattr(fence, 'code', None) not in {'fenced_result', 'commit_pending'}:
                raise
        raise


def _write_handoff(runtime, run_id, task_id, dispatch, context, stage):
    host_id = dispatch.get('host_id')
    host_action = 'deliver_to_bound_worker' if host_id else 'spawn_independent_worker'
    # Business write scopes describe destinations; the worker only writes staging.
    prompt = context_prompt(context) + (
        '\n\nExecution boundary:\n'
        f'Write all proposed result files inside {stage}. '
        'Do not write final destinations directly. The supervisor submits the staged '
        'files through the runtime, which checks versions and allowed destinations. '
        'Return a short summary and staged_path/target_path pairs. '
        'Do not invoke dispatch, finish, revise, or publish.\n'
    )
    handoff = {
        'run_id': run_id, 'task_id': task_id, 'attempt': dispatch['attempt'],
        'epoch': dispatch['epoch'], 'token': dispatch['token'],
        'staging_dir': str(stage), 'host_id': host_id,
        'host_action': host_action, 'execution_started': False,
        'context': context, 'prompt': prompt,
        'enforcement': {
            'promotion': 'runtime_checked',
            'worker_filesystem': 'host_must_supply_tool_scope_or_sandbox',
            'read_refs': [r['path'] for r in context['resources']],
            'write_root': str(stage),
        },
    }
    destination = stage / 'handoff.json'
    atomic_json(destination, handoff)
    return {
        'run_id': run_id, 'task_id': task_id, 'role': context['role'],
        'host_action': host_action, 'execution_started': False,
        'handoff_path': str(destination),
        'staging_dir': str(stage), 'attempt': dispatch['attempt'], 'epoch': dispatch['epoch'],
    }


def compact_status(state):
    tasks = state.get('tasks', {})
    result = {key: state.get(key) for key in ('run_id', 'status', 'epoch', 'ready_tasks', 'lifecycle') if key in state}
    result['tasks'] = [
        {'task_id': key, 'role': t.get('role', t.get('owner')), 'status': t['status'],
         **({'blockers': t['blockers']} if t.get('blockers') else {})}
        for key, t in tasks.items() if t.get('epoch') == state.get('epoch')
    ]
    for key in ('deliverables', 'completion', 'cancel_requests', 'recovery_conflict',
                'awaiting_hosts', 'recovery'):
        if state.get(key):
            result[key] = state[key]
    return result

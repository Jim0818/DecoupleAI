"""TextPicOS command surface: supervisor decisions, deterministic execution."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from textpicos.paths import ProjectPaths


def _json_file(value):
    return json.loads(sys.stdin.read() if value == '-' else Path(value).read_text(encoding='utf-8'))


def _json_object(value):
    result = _json_file(value)
    if not isinstance(result, dict):
        raise ValueError('The JSON payload must be an object')
    return result


def _error(exc):
    return exc.as_dict() if hasattr(exc, 'as_dict') else {
        'error': type(exc).__name__, 'message': str(exc),
    }


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def _parser():
    parser = argparse.ArgumentParser(description='TextPicOS supervisor task runtime')
    parser.add_argument('--root', type=Path, help='Explicit project root; otherwise discover the installed project')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('start', aliases=['init'])
    p.add_argument('run_id'); p.add_argument('goal')
    p.add_argument('--account', default='decoupleai')
    p.add_argument('--input', action='append', default=[])
    p.add_argument('--deliverable', action='append', default=[])
    p.add_argument('--session-id')
    p.add_argument('--profile', default='standard')
    p.add_argument('--workflow', default='default')
    p = sub.add_parser('add-task')
    p.add_argument('run_id'); p.add_argument('--spec', help='JSON object, or - for stdin')
    p.add_argument('--id'); p.add_argument('--role'); p.add_argument('--mode'); p.add_argument('--goal')
    p.add_argument('--account'); p.add_argument('--skill', action='append', default=None)
    p.add_argument('--input', action='append', default=[])
    p.add_argument('--write', action='append', default=[])
    p.add_argument('--deliverable', action='append', default=[])
    p.add_argument('--depends-on', action='append', default=[])
    p.add_argument('--accept', action='append', default=[])
    p.add_argument('--optional', action='store_true')
    p = sub.add_parser('update-task')
    p.add_argument('run_id'); p.add_argument('task_id'); p.add_argument('--spec', required=True)
    p.add_argument('--reason', required=True)
    p = sub.add_parser('dispatch')
    p.add_argument('run_id'); p.add_argument('task_id'); p.add_argument('--host-id')
    p = sub.add_parser('drive-next', aliases=['next'])
    p.add_argument('run_id'); p.add_argument('--limit', type=int, default=4)
    p = sub.add_parser('bind-host')
    p.add_argument('run_id'); p.add_argument('task_id'); p.add_argument('--token', required=True)
    p.add_argument('--host-id', required=True)
    p = sub.add_parser('submit')
    p.add_argument('run_id'); p.add_argument('task_id'); p.add_argument('--token', required=True)
    p.add_argument('--result', required=True, help='JSON: outputs, summary, blockers')
    p = sub.add_parser('status')
    p.add_argument('run_id'); p.add_argument('--verbose', action='store_true')
    p = sub.add_parser('task')
    p.add_argument('run_id'); p.add_argument('task_id')
    p = sub.add_parser('context')
    p.add_argument('run_id'); p.add_argument('task_id', nargs='?'); p.add_argument('--role', default='supervisor')
    p = sub.add_parser('cancel')
    p.add_argument('run_id'); p.add_argument('task_id', nargs='?'); p.add_argument('--reason', default='cancelled by supervisor')
    p = sub.add_parser('fail')
    p.add_argument('run_id'); p.add_argument('task_id'); p.add_argument('--token', required=True)
    p.add_argument('--reason', required=True); p.add_argument('--waiting-user', action='store_true')
    p = sub.add_parser('unblock')
    p.add_argument('run_id'); p.add_argument('task_id'); p.add_argument('--resolution', required=True)
    p = sub.add_parser('revise')
    p.add_argument('run_id'); p.add_argument('--feedback', required=True); p.add_argument('--goal')
    p = sub.add_parser('finish')
    p.add_argument('run_id'); p.add_argument('--completion', required=True)
    p.add_argument('--deliverable', action='append')
    p = sub.add_parser('resume')
    p.add_argument('run_id'); p.add_argument('--host-states'); p.add_argument('--abort-conflict', action='store_true')
    sub.add_parser('capabilities'); sub.add_parser('paths')
    p = sub.add_parser('audit'); p.add_argument('--scope', choices=['system'], default='system')
    p = sub.add_parser('legacy'); p.add_argument('args', nargs=argparse.REMAINDER)
    return parser


def _exclusions(paths):
    if os.environ.get('TEXTPICOS_MAINTENANCE_SCOPE') != 'system':
        return ()
    return (paths.articles, paths.root / 'archive/未命名文件夹---这里内容不要动')


def _legacy_command(paths, args):
    from textpicos.entry import identity_guard, legacy_engine_process
    from textpicos.host import checked_ref
    commands = {'init', 'next', 'drive-next', 'run-script', 'receipt', 'submit',
                'status', 'human-event', 'resume'}
    if len(args) < 2 or args[0] not in commands:
        raise ValueError('legacy requires an Engine command and its run or dispatch reference')
    if args[0] == 'receipt':
        path = checked_ref(paths, args[1], exclusions=_exclusions(paths), must_exist=True)
        run_id = json.loads(path.read_text(encoding='utf-8'))['run_id']
    else:
        run_id = args[1]
    with identity_guard(paths, run_id) as identity:
        if identity == 'supervisor':
            raise ValueError('This run ID belongs to the supervisor runtime')
        if args[0] == 'init' and identity is not None:
            raise ValueError('Legacy run already exists; resume it instead of overwriting its state')
        return legacy_engine_process(paths, args)


def main(argv=None):
    args = _parser().parse_args(argv)
    command = args.command
    exit_code = 0
    try:
        paths = ProjectPaths.from_root(args.root) if args.root else ProjectPaths.discover()
        if command == 'paths':
            _emit(paths.as_dict()); return 0
        if command == 'capabilities':
            from textpicos.context import list_capabilities
            _emit(list_capabilities(paths)); return 0
        if command == 'audit':
            from textpicos.maintenance.system_audit import audit_system
            result = audit_system(paths)
            _emit(result); return 0 if result['ok'] else 1
        if command == 'legacy':
            return _legacy_command(paths, args.args)
        from textpicos.runtime import Runtime
        from textpicos.host import compact_status, prepare_dispatch, checked_ref, validate_task_paths
        from textpicos.context import assemble_context
        from textpicos.entry import runtime_identity, identity_guard
        identity = runtime_identity(paths, args.run_id)
        if identity == 'legacy':
            raise ValueError('This run ID belongs to the legacy runtime; use the explicit legacy command')
        runtime = Runtime(paths)
        if command in {'start', 'init'}:
            # Validate selected source paths; no directory walks or automatic input copying.
            for ref in args.input:
                checked_ref(paths, ref, must_exist=True, exclusions=_exclusions(paths))
            for ref in args.deliverable:
                checked_ref(paths, ref, exclusions=_exclusions(paths))
            assemble_context(paths, {'role': 'supervisor', 'account_id': args.account,
                                     'goal': args.goal}, exclusions=_exclusions(paths))
            with identity_guard(paths, args.run_id) as current:
                if current == 'legacy':
                    raise ValueError('This run ID belongs to the legacy runtime')
                state = runtime.create(args.run_id, args.goal, metadata={
                    'account_id': args.account, 'input_refs': args.input,
                    'production_profile': args.profile, 'workflow': args.workflow,
                    **({'host_session_id': args.session_id} if args.session_id else {}),
                }, deliverables=args.deliverable)
            if args.session_id:
                from textpicos.maintenance.hooks import bind_session
                bind_session(paths, args.session_id, args.run_id)
            result = {'run_id': args.run_id, 'status': state.get('status', 'planning'),
                      'next_action': 'supervisor_plan', 'role_ref': str(paths.agents / 'supervisor/SKILL.md'),
                      'state_path': str(paths.runs / args.run_id / 'engine-state.json')}
        elif command == 'add-task':
            spec = _json_object(args.spec) if args.spec else {
                'role': args.role, 'mode': args.mode, 'goal': args.goal,
                'account_id': args.account, 'skill_ids': args.skill,
                'input_refs': args.input, 'allowed_write_roots': args.write,
                'deliverables': args.deliverable, 'depends_on': args.depends_on,
                'acceptance_criteria': args.accept, 'required': not args.optional,
            }
            task_id = spec.pop('task_id', None) or args.id or ('task-' + uuid.uuid4().hex[:10])
            if not spec.get('account_id'):
                spec['account_id'] = runtime.status(args.run_id).get('metadata', {}).get('account_id')
            # The registry validates the chosen capability; runtime remains business-agnostic.
            validate_task_paths(paths, spec, exclusions=_exclusions(paths))
            assemble_context(paths, {**spec, 'input_refs': []}, exclusions=_exclusions(paths))
            task = runtime.add(args.run_id, task_id, **spec)
            result = {'run_id': args.run_id, 'task_id': task_id, 'status': task['status']}
        elif command == 'update-task':
            changes = _json_object(args.spec)
            proposed = {**runtime.task(args.run_id, args.task_id), **changes}
            validate_task_paths(paths, proposed, exclusions=_exclusions(paths))
            assemble_context(paths, {**proposed, 'input_refs': []}, exclusions=_exclusions(paths))
            result = runtime.update(args.run_id, args.task_id, reason=args.reason, **changes)
        elif command == 'dispatch':
            result = prepare_dispatch(paths, runtime, args.run_id, args.task_id, host_id=args.host_id, exclusions=_exclusions(paths))
        elif command in {'drive-next', 'next'}:
            if args.limit < 1:
                raise ValueError('limit must be positive')
            state = runtime.status(args.run_id)
            jobs = []
            errors = []
            for task_id in state.get('ready_tasks', [])[:args.limit]:
                try:
                    jobs.append(prepare_dispatch(paths, runtime, args.run_id, task_id, exclusions=_exclusions(paths)))
                except Exception as exc:
                    if not isinstance(exc, (OSError, ValueError, TypeError, KeyError)) and not hasattr(exc, 'as_dict'):
                        raise
                    errors.append({'task_id': task_id, **_error(exc)})
            result = {'action': 'dispatch', 'execution_started': False, 'jobs': jobs} if jobs else compact_status(runtime.status(args.run_id))
            if errors:
                result['errors'] = errors
                exit_code = 0 if jobs else 1
        elif command == 'bind-host':
            if not args.host_id.strip():
                raise ValueError('host_id must identify an actual host execution')
            result = runtime.bind_host(args.run_id, args.task_id, args.token, args.host_id)
        elif command == 'submit':
            payload = _json_object(args.result)
            task = runtime.task(args.run_id, args.task_id)
            validate_task_paths(paths, task, exclusions=_exclusions(paths))
            stage = Path((task.get('dispatch') or {}).get('staging_dir', paths.runs))
            for output in payload.get('outputs', []):
                checked_ref(paths, output['target_path'], exclusions=_exclusions(paths))
                checked_ref(paths, stage / output['staged_path'], exclusions=_exclusions(paths))
            result = runtime.submit(args.run_id, args.task_id, args.token, **payload)
        elif command == 'status':
            state = runtime.status(args.run_id)
            result = state if args.verbose else compact_status(state)
        elif command == 'task':
            result = runtime.task(args.run_id, args.task_id)
        elif command == 'context':
            state = runtime.status(args.run_id)
            task = runtime.task(args.run_id, args.task_id) if args.task_id else {
                'role': args.role, 'goal': state['goal'],
                'input_refs': state.get('metadata', {}).get('input_refs', []),
                'account_id': state.get('metadata', {}).get('account_id'),
            }
            validate_task_paths(paths, task, exclusions=_exclusions(paths))
            result = assemble_context(paths, task, exclusions=_exclusions(paths))
        elif command == 'cancel':
            result = runtime.cancel(args.run_id, args.task_id, reason=args.reason)
        elif command == 'fail':
            result = runtime.fail(args.run_id, args.task_id, args.token, reason=args.reason, waiting_user=args.waiting_user)
        elif command == 'unblock':
            result = runtime.unblock(args.run_id, args.task_id, resolution=args.resolution)
        elif command == 'revise':
            result = runtime.revise(args.run_id, feedback=args.feedback, goal=args.goal)
        elif command == 'finish':
            state = runtime.status(args.run_id)
            for ref in [*state.get('deliverables', []), *(args.deliverable or [])]:
                checked_ref(paths, ref, exclusions=_exclusions(paths))
            for task in state['tasks'].values():
                if task['epoch'] == state['epoch'] and task['required']:
                    validate_task_paths(paths, task, exclusions=_exclusions(paths))
            result = runtime.finish(args.run_id, completion=args.completion, deliverables=args.deliverable)
        elif command == 'resume':
            result = runtime.resume(args.run_id, host_states=_json_object(args.host_states) if args.host_states else None, abort_conflict=args.abort_conflict)
        else:
            raise ValueError(f'Unknown command: {command}')
        if isinstance(result, dict) and isinstance(result.get("tasks"), dict) and "lifecycle" in result and not (command == "status" and args.verbose):
            result = compact_status(result)
        elif command in {'update-task', 'fail', 'unblock'}:
            result = {'run_id': args.run_id, 'task_id': result['id'], 'status': result['status'],
                      **({'blockers': result['blockers']} if result.get('blockers') else {})}
        _emit(result)
        return exit_code
    except (OSError, ValueError, TypeError, KeyError) as exc:
        _emit({'error': type(exc).__name__, 'message': str(exc)})
        return 1
    except Exception as exc:
        if hasattr(exc, 'as_dict'):
            _emit(exc.as_dict())
            return 1
        # Configuration errors have a useful message without a raw traceback in normal use.
        if exc.__class__.__name__ == 'ContextError':
            _emit({'error': 'context_error', 'message': str(exc)})
            return 1
        raise


if __name__ == '__main__':
    raise SystemExit(main())

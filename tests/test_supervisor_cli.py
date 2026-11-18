from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from textpicos.paths import ProjectPaths


@pytest.fixture
def cli_project(tmp_path):
    source = ProjectPaths.discover().root
    root = tmp_path / 'project'
    root.mkdir()
    registry = json.loads((source / 'config/system/capabilities.json').read_text())
    refs = set()

    def collect(value):
        if isinstance(value, dict):
            for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
        elif isinstance(value, str) and value.startswith(('agents/', 'skills/', 'config/')) and 'legacy/' not in value:
            if (source / value).is_file(): refs.add(value)

    collect(registry)
    for account in registry['accounts'].values():
        for name in ('L1_identity.md', 'L2_values.md', 'L3_content_dna.md', 'voice-overlay.md'):
            refs.add(account['directory'] + '/' + name)
    refs.add('config/system/capabilities.json')
    refs.add('config/system/paths.json')
    for ref in refs:
        dest = root / ref
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / ref, dest)
    # Python subprocesses do not inherit the parent's audit hook. Install the
    # same real-project boundary in every child (including the legacy child).
    guard_dir = tmp_path / 'test_guard'
    guard_dir.mkdir()
    (guard_dir / 'sitecustomize.py').write_text(
        "import os, runpy\n"
        "_configured = os.environ.pop('TEXTPICOS_ROOT', None)\n"
        "try:\n"
        f"    runpy.run_path({str(source / 'tests/conftest.py')!r})\n"
        "finally:\n"
        "    if _configured is not None: os.environ['TEXTPICOS_ROOT'] = _configured\n"
    )
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join((str(guard_dir), str(source / 'src'))),
           'PYTHONDONTWRITEBYTECODE': '1', 'TEXTPICOS_MAINTENANCE_SCOPE': 'system'}
    env.pop('TEXTPICOS_ROOT', None)

    def invoke(*args, success=True):
        result = subprocess.run([sys.executable, str(source / 'scripts/textpicos.py'), '--root', str(root), *args],
                                cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return json.loads(result.stdout)

    def pipeline(*args, success=True):
        result = subprocess.run([sys.executable, '-m', 'textpicos.entry', *args], cwd=tmp_path,
                                env={**env, 'TEXTPICOS_ROOT': str(root)}, text=True,
                                capture_output=True, timeout=20)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result

    invoke.pipeline = pipeline
    invoke.source = source
    invoke.env = env
    return root, invoke


def test_start_is_planning_without_legacy_phases(cli_project):
    root, invoke = cli_project
    out = invoke('start', 'editing', 'Edit an existing draft', '--account', 'studio')
    assert out['next_action'] == 'supervisor_plan'
    state = invoke('status', 'editing', '--verbose')
    assert state['status'] == 'planning'
    assert state['tasks'] == {}
    assert not (root / 'artifacts').exists()
    assert not (root / 'workspace/runs/editing/content-contract.json').exists()


def test_same_id_cannot_have_two_runtimes(cli_project):
    root, invoke = cli_project
    old = root / 'artifacts/old/engine-state.json'
    old.parent.mkdir(parents=True)
    old.write_text('{}')
    out = invoke('start', 'old', 'do work', success=False)
    assert 'legacy' in out['message']
    assert not (root / 'workspace/runs/old/engine-state.json').exists()


def test_future_dependency_input_can_be_planned(cli_project):
    root, invoke = cli_project
    invoke('start', 'work', 'Use evidence when ready', '--account', 'studio')
    invoke('add-task', 'work', '--id', 'research', '--role', 'research', '--goal', 'Verify source')
    invoke('add-task', 'work', '--id', 'draft', '--role', 'writer', '--goal', 'Use verified evidence',
           '--depends-on', 'research', '--input', 'evidence.json', '--write', 'out.md')
    state = invoke('status', 'work', '--verbose')
    assert 'draft' not in state['ready_tasks']
    assert state['tasks']['draft']['input_refs'][0]['path'].endswith('evidence.json')


def _write_and_submit(root, invoke, run_id, task_id, output, text):
    dispatch = invoke('dispatch', run_id, task_id)
    handoff = json.loads(Path(dispatch['handoff_path']).read_text())
    assert handoff['host_action'] == 'spawn_independent_worker'
    assert handoff['enforcement']['promotion'] == 'runtime_checked'
    assert '正文只有这里' not in json.dumps(handoff, ensure_ascii=False)
    stage = Path(dispatch['staging_dir'])
    (stage / 'result.md').write_text(text)
    result = root / 'result.json'
    result.write_text(json.dumps({'outputs': [{'staged_path': 'result.md', 'target_path': output}], 'summary': 'Updated requested scope'}))
    invoke('submit', run_id, task_id, '--token', handoff['token'], '--result', str(result))
    return handoff


def test_edit_then_local_revision_same_run(cli_project):
    root, invoke = cli_project
    original = root / 'source.md'
    original.write_text('报告式开头。\n\n正文只有这里。\n\n```python\nprint(1)\n```\n\n![示例](images/a.png)\n')
    body = original.read_text().split('\n\n', 1)[1]
    invoke('start', 'edit', 'Only revise the opening', '--account', 'studio', '--input', str(original), '--deliverable', 'result.md')
    invoke('add-task', 'edit', '--id', 'opening', '--role', 'writer', '--mode', 'edit', '--goal', 'Replace opening only',
           '--input', str(original), '--write', 'result.md', '--deliverable', 'result.md')
    _write_and_submit(root, invoke, 'edit', 'opening', 'result.md', '先看一个具体例子。\n\n' + body)
    invoke('finish', 'edit', '--completion', 'Opening changed; remaining source retained')
    assert invoke('status', 'edit')['status'] == 'completed'
    invoke('revise', 'edit', '--feedback', 'Make the opening shorter')
    invoke('add-task', 'edit', '--id', 'shorter', '--role', 'writer', '--mode', 'edit', '--goal', 'Shorten opening only',
           '--input', 'result.md', '--write', 'result.md', '--deliverable', 'result.md')
    _write_and_submit(root, invoke, 'edit', 'shorter', 'result.md', '看个例子。\n\n' + body)
    invoke('finish', 'edit', '--completion', 'Only the requested opening changed')
    state = invoke('status', 'edit', '--verbose')
    assert state['status'] == 'completed'
    assert state['epoch'] == 2
    assert (root / 'result.md').read_text().split('\n\n', 1)[1] == body
    assert original.read_text().startswith('报告式开头。')
    assert not (root / 'workspace/runs/edit/content-contract.json').exists()


def test_title_mode_does_not_load_body_method(cli_project):
    root, invoke = cli_project
    invoke('start', 'title', 'Only change title', '--account', 'studio')
    invoke('add-task', 'title', '--id', 'title', '--role', 'writer', '--mode', 'title', '--goal', 'Shorten a title')
    context = invoke('context', 'title', 'title')
    assert context['skill_ids'] == ['writing']
    assert not any('/legacy/' in r['path'] for r in context['resources'])


@pytest.mark.parametrize('role,mode', [('writer', 'compose'), ('writer', 'edit'), ('reviewer', 'review')])
def test_cli_omitted_skills_reach_real_handoff_with_current_policy(cli_project, role, mode):
    root, invoke = cli_project
    invoke('start', 'default-methods', 'Work with the current content methods', '--account', 'studio')
    invoke('add-task', 'default-methods', '--id', 'work', '--role', role, '--mode', mode,
           '--goal', 'Complete the assigned content task')
    job = invoke('dispatch', 'default-methods', 'work')
    handoff = json.loads(Path(job['handoff_path']).read_text())
    assert 'natural-prose' in handoff['context']['skill_ids']
    assert handoff['context']['task']['prose_policy_revision'] == 2
    assert sum('/natural-prose/SKILL.md' in item['path'] for item in handoff['context']['resources']) == 1


def test_cli_explicit_empty_skills_preserve_the_supervisors_selection(cli_project):
    root, invoke = cli_project
    invoke('start', 'selected-methods', 'Use only the selected writing capability', '--account', 'studio')
    spec = {'role': 'writer', 'mode': 'edit', 'goal': 'A bounded edit', 'skill_ids': []}
    spec_file = root / 'task.json'
    spec_file.write_text(json.dumps(spec))
    invoke('add-task', 'selected-methods', '--id', 'work', '--spec', str(spec_file))
    result = invoke('context', 'selected-methods', 'work')
    assert result['skill_ids'] == ['writing']


def test_no_ready_does_not_mean_completed(cli_project):
    root, invoke = cli_project
    invoke('start', 'waiting', 'Needs a user decision', '--account', 'studio')
    invoke('add-task', 'waiting', '--id', 'decision', '--role', 'research', '--goal', 'Resolve a source conflict')
    job = invoke('dispatch', 'waiting', 'decision')
    handoff = json.loads(Path(job['handoff_path']).read_text())
    invoke('fail', 'waiting', 'decision', '--token', handoff['token'], '--reason', 'Sources conflict', '--waiting-user')
    result = invoke('drive-next', 'waiting')
    assert result['status'] == 'waiting_user'
    invoke('finish', 'waiting', '--completion', 'Cannot finish', success=False)


def test_dispatch_is_handoff_and_duplicate_does_not_allocate_attempt(cli_project):
    root, invoke = cli_project
    invoke('start', 'dispatch', 'A bounded research task', '--account', 'studio')
    invoke('add-task', 'dispatch', '--id', 'r', '--role', 'research', '--goal', 'Check evidence')
    dispatch = invoke('dispatch', 'dispatch', 'r')
    assert dispatch['execution_started'] is False
    handoff = json.loads(Path(dispatch['handoff_path']).read_text())
    assert handoff['execution_started'] is False
    duplicate = invoke('dispatch', 'dispatch', 'r', success=False)
    assert duplicate['error'] == 'not_dispatchable'
    task = invoke('task', 'dispatch', 'r')
    assert task['attempt'] == 1
    assert task['dispatch']['token'] == handoff['token']
    invoke('bind-host', 'dispatch', 'r', '--token', handoff['token'], '--host-id', 'worker-1')
    conflict = invoke('bind-host', 'dispatch', 'r', '--token', handoff['token'], '--host-id', 'worker-2', success=False)
    assert conflict['error'] == 'host_already_bound'
    observations = root / 'hosts.json'
    observations.write_text(json.dumps({'worker-1': 'completed'}))
    resumed = invoke('resume', 'dispatch', '--host-states', str(observations))
    assert resumed['status'] == 'running'
    assert resumed['awaiting_hosts'][0]['action'] == 'collect_result'
    assert resumed['awaiting_hosts'][0]['host_id'] == 'worker-1'


def test_batch_dispatch_preserves_successful_handoffs_when_another_input_is_missing(cli_project):
    root, invoke = cli_project
    invoke('start', 'batch', 'Parallel work', '--account', 'studio')
    invoke('add-task', 'batch', '--id', 'ready', '--role', 'research', '--goal', 'Check available evidence')
    invoke('add-task', 'batch', '--id', 'missing', '--role', 'research', '--goal', 'Use a future file',
           '--input', 'future.json')
    response = invoke('drive-next', 'batch')
    assert response['execution_started'] is False
    assert [job['task_id'] for job in response['jobs']] == ['ready']
    assert response['errors'][0]['task_id'] == 'missing'
    assert response['errors'][0]['error'] == 'missing_input'
    assert Path(response['jobs'][0]['handoff_path']).is_file()
    blocked = invoke('task', 'batch', 'missing')
    assert blocked['status'] == 'blocked'
    assert blocked['attempt'] == 0


def test_handoff_uses_the_task_snapshot_authorized_by_dispatch(cli_project, monkeypatch):
    from textpicos import host
    from textpicos.runtime import Runtime

    root, invoke = cli_project
    invoke('start', 'race', 'Use the current task')
    (root / 'new.txt').write_text('not embedded in the handoff')
    paths = ProjectPaths.from_root(root)
    runtime = Runtime(paths)
    runtime.add('race', 'r', role='research', goal='old goal')
    original = host.assemble_context
    changed = False

    def assemble(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            runtime.update('race', 'r', reason='supervisor adjusted the task',
                           goal='new goal', input_refs=['new.txt'])
        return result

    monkeypatch.setattr(host, 'assemble_context', assemble)
    dispatch = host.prepare_dispatch(paths, runtime, 'race', 'r')
    handoff = json.loads(Path(dispatch['handoff_path']).read_text())
    assert handoff['context']['task']['goal'] == 'new goal'
    assert any(ref['path'].endswith('/new.txt') for ref in handoff['context']['resources'])
    assert 'not embedded in the handoff' not in handoff['prompt']


def test_failed_context_after_dispatch_does_not_leave_an_unowned_running_attempt(cli_project, monkeypatch):
    from textpicos import host
    from textpicos.runtime import Runtime

    root, invoke = cli_project
    invoke('start', 'failure', 'Handle a resource disappearing')
    paths = ProjectPaths.from_root(root)
    runtime = Runtime(paths)
    runtime.add('failure', 'r', role='research', goal='Check a fact')
    original = host.assemble_context
    calls = 0

    def assemble(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError('resource disappeared after preflight')
        return original(*args, **kwargs)

    monkeypatch.setattr(host, 'assemble_context', assemble)
    with pytest.raises(ValueError, match='disappeared'):
        host.prepare_dispatch(paths, runtime, 'failure', 'r')
    task = runtime.task('failure', 'r')
    assert task['status'] == 'failed'
    assert task['attempt'] == 1
    assert not (Path(task['dispatch']['staging_dir']) / 'handoff.json').exists()


def test_maintenance_paths_are_rejected_before_any_probe(cli_project, monkeypatch, capsys):
    from textpicos.cli import main

    root, invoke = cli_project
    invoke('start', 'scope', 'Plan in scope')
    invoke('add-task', 'scope', '--id', 'r', '--role', 'research', '--goal', 'Check a fact')
    monkeypatch.setenv('TEXTPICOS_MAINTENANCE_SCOPE', 'system')
    original = Path.lstat

    def guarded(path, *args, **kwargs):
        if 'articles' in path.parts or '未命名文件夹---这里内容不要动' in path.parts:
            raise AssertionError('Excluded content must not be probed')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'lstat', guarded)
    assert main(['--root', str(root), 'start', 'bad', 'no read', '--input', 'articles/missing.md']) == 1
    assert 'excluded' in json.loads(capsys.readouterr().out)['message']
    assert main(['--root', str(root), 'add-task', 'scope', '--id', 'bad', '--role', 'writer',
                 '--goal', 'no write', '--write', 'resources/articles/future.md']) == 1
    assert 'excluded' in json.loads(capsys.readouterr().out)['message']
    spec = root / 'change.json'
    spec.write_text(json.dumps({'allowed_write_roots': ['archive/未命名文件夹---这里内容不要动/result.md']}))
    assert main(['--root', str(root), 'update-task', 'scope', 'r', '--spec', str(spec), '--reason', 'test boundary']) == 1
    assert 'excluded' in json.loads(capsys.readouterr().out)['message']
    assert invoke('task', 'scope', 'r')['allowed_write_roots'] == []


def test_start_rejects_parent_traversal_before_checking_old_state(cli_project):
    root, invoke = cli_project
    result = invoke('start', '../articles', 'not a run id', success=False)
    assert result['error'] == 'invalid_identifier'
    assert not (root / 'workspace/runs').exists()


def test_invalid_update_does_not_mutate_task_and_default_receipt_is_compact(cli_project):
    root, invoke = cli_project
    invoke('start', 'update', 'Adjust a task')
    invoke('add-task', 'update', '--id', 'r', '--role', 'research', '--goal', 'Initial scope')
    spec = root / 'change.json'
    spec.write_text(json.dumps({'mode': 'does-not-exist'}))
    invoke('update-task', 'update', 'r', '--spec', str(spec), '--reason', 'invalid method', success=False)
    assert invoke('task', 'update', 'r')['mode'] is None
    spec.write_text(json.dumps({'goal': 'New scope', 'input_refs': ['future.json']}))
    result = invoke('update-task', 'update', 'r', '--spec', str(spec), '--reason', 'Refined task')
    assert set(result) == {'run_id', 'task_id', 'status'}


def _legacy_fixture(root, source):
    for directory in ('workflows/schemas', 'workflows/governance'):
        destination = root / directory
        destination.mkdir(parents=True, exist_ok=True)
        for path in (source / directory).iterdir():
            if path.suffix in {'.json', '.yaml', '.yml'}:
                shutil.copyfile(path, destination / path.name)
    for ref in ('src/textpicos/legacy/run_pipeline.sh', 'scripts/engine/__init__.py',
                'scripts/engine/cli.py', 'scripts/wf_state.py', 'scripts/phase_manifest.py'):
        destination = root / ref
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / ref, destination)


def test_legacy_creation_and_status_are_callable_and_cannot_reinitialize(cli_project):
    root, invoke = cli_project
    _legacy_fixture(root, invoke.source)
    legacy = invoke('legacy', 'init', 'historical', 'Test goal', 'studio')
    assert legacy['schema_version'] == 4
    before = (root / 'artifacts/historical/engine-state.json').read_bytes()
    status = invoke('legacy', 'status', 'historical')
    assert status['run_id'] == 'historical'
    invoke('legacy', 'init', 'historical', 'overwrite', 'studio', success=False)
    assert (root / 'artifacts/historical/engine-state.json').read_bytes() == before
    assert not (root / 'workspace/runs/historical/engine-state.json').exists()
    routed = invoke.pipeline('status', 'historical')
    assert json.loads(routed.stdout)['run_id'] == 'historical'


def test_legacy_pipeline_normalization_cannot_create_second_state_for_native_id(cli_project):
    root, invoke = cli_project
    _legacy_fixture(root, invoke.source)
    invoke('start', '2026-11-18-test', 'Native goal')
    invoke('legacy', 'init', '2026-11-18-test', 'Legacy goal', 'studio', success=False)
    invoke.pipeline('start', 'run_20261118_001_test', 'Legacy goal', 'studio', '--legacy', success=False)
    assert not (root / 'artifacts/2026-11-18-test').exists()
    # An actual isolated shell -> old CLI bootstrap also remains usable.
    invoke.pipeline('start', 'old-shell', 'Old goal', 'studio', '--legacy')
    state = json.loads((root / 'artifacts/old-shell/engine-state.json').read_text())
    assert state['run_id'] == 'old-shell'
    assert not (root / 'workspace/runs/old-shell/engine-state.json').exists()


def test_competing_native_and_legacy_initializers_have_one_owner(cli_project):
    root, invoke = cli_project
    _legacy_fixture(root, invoke.source)
    prefix = [sys.executable, str(invoke.source / 'scripts/textpicos.py'), '--root', str(root)]
    commands = [
        prefix + ['start', 'competing', 'Native goal'],
        prefix + ['legacy', 'init', 'competing', 'Historical goal', 'studio'],
    ]

    def launch(command):
        return subprocess.run(command, cwd=root.parent, env=invoke.env, text=True,
                              capture_output=True, timeout=20)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(launch, commands))
    assert sorted(result.returncode for result in results) == [0, 1], [
        result.stdout + result.stderr for result in results
    ]
    assert sum(path.is_file() for path in (
        root / 'workspace/runs/competing/engine-state.json',
        root / 'artifacts/competing/engine-state.json',
    )) == 1

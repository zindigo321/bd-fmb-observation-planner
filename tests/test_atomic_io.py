"""Serial atomic-write regressions with real Windows hardlinks and process guards."""
import json
import os
import sys
from pathlib import Path

import pytest

from planner import atomic_io
from planner.common import csv_write, json_write
from planner.path_safety import guard_writes, tree_snapshot
from scripts import budget_run
from test_path_safety import fixture_spec, invoke


def poisoned_temp(root, name):
    raw = root / 'raw'
    raw.mkdir()
    (raw / 'empty').mkdir()
    source = raw / 'input.txt'
    source.write_text('synthetic protected input', encoding='utf-8')
    alias = root / name
    os.link(source, alias)
    assert os.path.samefile(source, alias)
    guard_writes([alias], [raw])  # The protected object is the DIRECTORY.
    return raw, source, alias, tree_snapshot(raw)


def assert_preserved(raw, source, alias, before):
    assert tree_snapshot(raw) == before
    assert os.path.samefile(source, alias)
    assert alias.read_text(encoding='utf-8') == 'synthetic protected input'


def test_budget_directory_alias_and_real_running_completed_saves(tmp_path):
    raw, source, alias, before = poisoned_temp(tmp_path, 'ledger.tmp')
    ledger = tmp_path / 'ledger.json'
    script = ('import json,sys; d=json.load(open(sys.argv[1])); '
              'assert d["entries"][-1]["status"]=="RUNNING"; print("observed RUNNING")')
    assert budget_run.execute(ledger, [sys.executable, '-c', script, str(ledger)],
                              timeout=10, protected=[raw]) == 0
    result = json.loads(ledger.read_text(encoding='utf-8'))
    entry = result['entries'][0]
    assert entry['status'] == 'PASS' and entry['exit_code'] == 0
    assert 0 < result['used_seconds'] == entry['seconds'] < 10
    assert result['remaining_seconds'] == 600 - entry['seconds']
    assert entry['start'] <= entry['end']
    assert Path(entry['log']).read_text().strip() == 'observed RUNNING'
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.ledger.json.*.tmp'))


def test_full_experiment_cli_preserves_directory_alias_on_later_failure(tmp_path):
    spec, sources = fixture_spec(tmp_path)
    raw = tmp_path / 'raw'
    source = raw / 'input.txt'
    alias = tmp_path / 'ledger.tmp'
    os.link(source, alias)
    assert os.path.samefile(source, alias)
    guard_writes([alias], [raw])
    before = tree_snapshot(raw)
    sealed_before = [tree_snapshot(p) for p in sources]
    result = invoke(spec, tmp_path / 'new_output', tmp_path / 'ledger.json')
    # The deliberately incomplete synthetic config fails after preparation.
    assert result.returncode == 2, result.stdout + result.stderr
    ledger = json.loads((tmp_path / 'ledger.json').read_text(encoding='utf-8'))
    assert [e['status'] for e in ledger['entries']] == ['PASS', 'FAIL']
    assert tree_snapshot(raw) == before
    assert [tree_snapshot(p) for p in sources] == sealed_before
    assert os.path.samefile(source, alias) and alias.read_text() == 'synthetic only'
    assert not list(tmp_path.rglob('.*.tmp'))


@pytest.mark.parametrize('kind', ['json', 'csv'])
@pytest.mark.parametrize('existing', [False, True])
def test_public_writers_preserve_poisoned_temp_and_format(tmp_path, kind, existing):
    target = tmp_path / ('result.' + kind)
    raw, source, alias, before = poisoned_temp(tmp_path, target.name + '.tmp')
    if existing:
        target.write_bytes(b'previous target')
    if kind == 'json':
        json_write(target, {'z': '中文', 'a': [1, None]})
        expected = '{\n  "z": "中文",\n  "a": [\n    1,\n    null\n  ]\n}'.replace('\n', os.linesep).encode('utf-8')
    else:
        csv_write(target, [{'z': '中,文', 'a': 'line1\nline2', 'ignored': 9}], ['z', 'a'])
        expected = 'z,a\r\n"中,文","line1\nline2"\r\n'.encode('utf-8')
    assert target.read_bytes() == expected
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))


@pytest.mark.parametrize('kind', ['json', 'csv', 'ledger'])
def test_ordinary_legacy_temp_is_not_removed_or_truncated(tmp_path, kind):
    target = tmp_path / ('ledger.json' if kind == 'ledger' else 'result.' + kind)
    legacy = target.with_suffix('.tmp') if kind == 'ledger' else target.with_name(target.name + '.tmp')
    legacy.write_bytes(b'unknown pre-existing ordinary file')
    if kind == 'json':
        json_write(target, {'value': 1}); json_write(target, {'value': 2})
        assert json.loads(target.read_text()) == {'value': 2}
    elif kind == 'csv':
        csv_write(target, [{'value': 1}], ['value']); csv_write(target, [{'value': 2}], ['value'])
        assert target.read_bytes() == b'value\r\n2\r\n'
    else:
        for _ in range(2):
            assert budget_run.execute(target, [sys.executable, '-c', 'print("ok")'], timeout=10) == 0
        assert len(json.loads(target.read_text())['entries']) == 2
    assert legacy.read_bytes() == b'unknown pre-existing ordinary file'
    assert not list(tmp_path.glob('.*.tmp'))


@pytest.mark.parametrize('value', [float('nan'), float('inf'), object()])
def test_json_serialization_failure_preserves_target_and_input(tmp_path, value):
    target = tmp_path / 'result.json'
    raw, source, alias, before = poisoned_temp(tmp_path, target.name + '.tmp')
    target.write_bytes(b'previous target')
    with pytest.raises((ValueError, TypeError)):
        json_write(target, {'value': value})
    assert target.read_bytes() == b'previous target'
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))


def test_csv_streaming_serialization_failure_discards_partial_output(tmp_path):
    target = tmp_path / 'result.csv'
    raw, source, alias, before = poisoned_temp(tmp_path, target.name + '.tmp')
    target.write_bytes(b'previous target')
    def rows():
        yield {'value': 'written to owned temporary'}
        raise ValueError('synthetic row serialization failed')
    with pytest.raises(ValueError, match='serialization failed'):
        csv_write(target, rows(), ['value'])
    assert target.read_bytes() == b'previous target'
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))


@pytest.mark.parametrize('phase', ['fdopen', 'write', 'replace'])
def test_failures_close_owned_handle_and_clean_only_owned_temp(tmp_path, monkeypatch, phase):
    target = tmp_path / 'result.json'
    raw, source, alias, before = poisoned_temp(tmp_path, target.name + '.tmp')
    target.write_bytes(b'previous target')
    created = []
    mkstemp, fdopen = atomic_io.tempfile.mkstemp, atomic_io.os.fdopen
    def capture(**kwargs):
        fd, name = mkstemp(**kwargs); created.append((fd, Path(name))); return fd, name
    monkeypatch.setattr(atomic_io.tempfile, 'mkstemp', capture)
    if phase == 'fdopen':
        def fail_open(*args, **kwargs): raise OSError('injected fdopen failure')
        monkeypatch.setattr(atomic_io.os, 'fdopen', fail_open)
    elif phase == 'write':
        class FailingWriter:
            def __init__(self, *args, **kwargs): self.stream = fdopen(*args, **kwargs)
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def write(self, text):
                self.stream.write(text[:2]); self.stream.flush()
                raise OSError('injected write failure')
        monkeypatch.setattr(atomic_io.os, 'fdopen', FailingWriter)
    else:
        def fail_replace(*args):
            with pytest.raises(OSError): os.fstat(created[0][0])
            raise OSError('injected replace failure')
        monkeypatch.setattr(atomic_io.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='injected'):
        json_write(target, {'value': 'new'})
    assert len(created) == 1
    fd, name = created[0]
    with pytest.raises(OSError): os.fstat(fd)
    assert not name.exists()
    assert target.read_bytes() == b'previous target'
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))


def test_replace_occurs_after_close_and_detaches_existing_target_alias(tmp_path, monkeypatch):
    raw, source, alias, before = poisoned_temp(tmp_path, 'result.json.tmp')
    target = tmp_path / 'result.json'
    os.link(source, target)
    created = []
    mkstemp, replace = atomic_io.tempfile.mkstemp, atomic_io.os.replace
    def capture(**kwargs):
        fd, name = mkstemp(**kwargs); created.append((fd, name)); return fd, name
    def check_closed(temporary, destination):
        with pytest.raises(OSError): os.fstat(created[0][0])
        assert Path(temporary).parent == target.parent
        return replace(temporary, destination)
    monkeypatch.setattr(atomic_io.tempfile, 'mkstemp', capture)
    monkeypatch.setattr(atomic_io.os, 'replace', check_closed)
    json_write(target, {'ok': True})
    assert json.loads(target.read_text()) == {'ok': True}
    assert not os.path.samefile(source, target)
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))


def test_cleanup_failure_is_reported_with_original_error(tmp_path, monkeypatch):
    target = tmp_path / 'result.json'
    raw, source, alias, before = poisoned_temp(tmp_path, target.name + '.tmp')
    target.write_bytes(b'previous target')
    attempted = []
    def fail_replace(*args): raise OSError('injected replace failure')
    def fail_cleanup(name):
        attempted.append(Path(name)); raise PermissionError('injected cleanup failure')
    with monkeypatch.context() as m:
        m.setattr(atomic_io.os, 'replace', fail_replace)
        m.setattr(atomic_io.os, 'unlink', fail_cleanup)
        with pytest.raises(OSError, match='replace failure') as caught:
            json_write(target, {'value': 'new'})
    assert len(attempted) == 1 and attempted[0] != alias
    assert 'cleanup failed' in ' '.join(caught.value.__notes__)
    assert 'injected cleanup failure' in ' '.join(caught.value.__notes__)
    assert str(attempted[0]) in ' '.join(caught.value.__notes__)
    assert target.read_bytes() == b'previous target'
    assert_preserved(raw, source, alias, before)
    # The injected inability to clean is reversible; remove only this test's owned file.
    attempted[0].unlink()


@pytest.mark.parametrize('mode, expected', [('failure', 'FAIL'), ('timeout', 'BLOCKED'), ('exception', 'FAIL')])
def test_budget_failure_timeout_and_exception_saves(tmp_path, monkeypatch, mode, expected):
    raw, source, alias, before = poisoned_temp(tmp_path, 'ledger.tmp')
    ledger = tmp_path / 'ledger.json'
    if mode == 'exception':
        def fail_guard(*args, **kwargs): raise OSError('injected process startup failure')
        monkeypatch.setattr(budget_run, 'run_guarded', fail_guard)
    script = 'import time; print("started",flush=True); time.sleep(10)' if mode == 'timeout' else 'import sys; print("failed"); sys.exit(2)'
    code = budget_run.execute(ledger, [sys.executable, '-c', script], timeout=0.5 if mode == 'timeout' else 10, protected=[raw])
    assert code == (3 if mode == 'timeout' else 2)
    state = json.loads(ledger.read_text(encoding='utf-8')); entry = state['entries'][0]
    assert entry['status'] == expected and entry['seconds'] > 0 and entry['end'] >= entry['start']
    assert state['used_seconds'] == entry['seconds'] and state['remaining_seconds'] == 600 - entry['seconds']
    if mode == 'exception': assert 'process startup failure' in entry['reason']
    else:
        assert entry['timed_out'] == (mode == 'timeout')
        assert ('started' if mode == 'timeout' else 'failed') in Path(entry['log']).read_text()
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))


@pytest.mark.parametrize('save_number', [1, 2])
def test_budget_save_failure_does_not_claim_completion_and_refuses_unresolved(tmp_path, monkeypatch, save_number):
    raw, source, alias, before = poisoned_temp(tmp_path, 'ledger.tmp')
    ledger = tmp_path / 'ledger.json'
    replace = atomic_io.os.replace
    calls = []
    def fail_selected_save(*args):
        calls.append(args)
        if len(calls) == save_number: raise OSError('injected ledger replacement failure')
        return replace(*args)
    with monkeypatch.context() as m:
        m.setattr(atomic_io.os, 'replace', fail_selected_save)
        with pytest.raises(OSError, match='ledger replacement failure'):
            budget_run.execute(ledger, [sys.executable, '-c', 'print("executed")'], timeout=10, protected=[raw])
    if save_number == 1:
        assert not ledger.exists() and not (tmp_path / 'command_01.log').exists()
    else:
        assert json.loads(ledger.read_text())['entries'][0]['status'] == 'RUNNING'
        full_before = tree_snapshot(tmp_path)
        with pytest.raises(ValueError, match='unresolved'):
            budget_run.execute(ledger, ['must-not-run'], protected=[raw])
        assert tree_snapshot(tmp_path) == full_before
    assert_preserved(raw, source, alias, before)
    assert not list(tmp_path.glob('.*.tmp'))

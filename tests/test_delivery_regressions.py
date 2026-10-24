"""Delivery regressions use temporary Git history and synthetic evidence only."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import pytest
import yaml

from planner.path_safety import tree_snapshot
from planner.runner import tree_hashes
from scripts import build_handoff

ROOT = Path(__file__).resolve().parents[1]
GITHUB_FILES = ('.github/pull_request_template.md', '.github/workflows/ci.yml')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def packaging_fixture(tmp_path, monkeypatch):
    repo = tmp_path/'synthetic repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo, stderr=subprocess.PIPE, timeout=15)
    git('init')
    git('config', 'core.autocrlf', 'false')
    names = (*GITHUB_FILES, '.gitattributes', '.editorconfig', 'CONTRIBUTING.md',
             'scripts/team3_run.py', 'scripts/inspect_team1_input.py',
             'docs/STABLE_HANDOFF.md', 'docs/DEMO_SCRIPT.md')
    for name in names:
        target = repo/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    git('add', '--', *names)
    git('-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
        'commit', '-m', 'synthetic packaging fixture')
    # The builder requires this candidate ref; no real project Git history is used.
    git('tag', 'b0eb3b5')
    commit = git('rev-parse', 'HEAD').decode().strip()
    base = tmp_path/'synthetic history'
    for name in ('targets.csv', 'stations.csv', 'windows.csv', 'metadata.json'):
        target = base/'experiments/E3_seed42/standard_input'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'examples/synthetic'/name, target)
    for directory in ('experiments', 'E5_common_baseline'):
        for name in ('comparison.csv', 'comparison.md', 'summary.json'):
            write_json(base/directory/name, {'synthetic': True})
    for directory in ('experiments/E3_seed42', 'experiments/E3_seed17',
                      'experiments/E3_seed23', 'experiments/E4_seed42_late', 'E5_common_baseline'):
        path = base/directory
        (path/'empty').mkdir(parents=True)
        write_json(path/'evidence_manifest.json', tree_hashes(path))
    html = base/'demo/index.html'
    html.parent.mkdir()
    html.write_bytes(b'<!doctype html><title>Synthetic offline fixture</title>')
    write_json(base/'demo/demo_data_check.json', {'html_sha256': hashlib.sha256(html.read_bytes()).hexdigest()})
    write_json(base/'browser/browser_checks.json', {'screenshots': ['synthetic.png']})
    (base/'browser/synthetic.png').write_bytes(b'synthetic screenshot placeholder')
    monkeypatch.setattr(build_handoff, 'ROOT', repo)
    return repo, base, commit, git


def test_build_exports_github_files_from_committed_blobs(packaging_fixture, tmp_path):
    repo, base, commit, git = packaging_fixture
    # Working-tree edits must never leak into the exported commit.
    for name in GITHUB_FILES:
        (repo/name).write_bytes(b'UNCOMMITTED\r\n')
    protected = {str(p): tree_snapshot(p) for p in (repo, base)}
    out = tmp_path/'packages'
    result = build_handoff.build(out, base, commit)
    assert set(result) == {'source_kit', 'local_demo_reference_kit'}
    for entry in result.values():
        path = Path(entry['path'])
        manifest = build_handoff.verify_archive(path)
        assert manifest['source_commit'] == commit
        assert entry['bytes'] == path.stat().st_size
        assert entry['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert path.with_suffix('.zip.sha256').read_text().split()[0] == entry['sha256']
    with zipfile.ZipFile(result['source_kit']['path']) as archive:
        manifest = json.loads(archive.read('MANIFEST.json'))
        assert set(GITHUB_FILES) <= set(manifest['files'])
        assert set(manifest['files']) == set(git('ls-tree', '-r', '--name-only', commit).decode().splitlines())
        for name in manifest['files']:
            assert archive.read(name) == git('show', commit+':'+name)
    assert protected == {str(p): tree_snapshot(p) for p in (repo, base)}


@pytest.mark.parametrize('unknown', ['unexpected.txt', '.secret', '.github/new.md', '.github/workflows/other.yml'])
def test_build_rejects_unknown_committed_file_before_output(packaging_fixture, tmp_path, unknown):
    repo, base, _, git = packaging_fixture
    (repo/unknown).parent.mkdir(parents=True, exist_ok=True)
    (repo/unknown).write_text('synthetic unknown', encoding='utf-8')
    git('add', '--', unknown)
    git('-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
        'commit', '-m', 'synthetic unknown file')
    protected = {str(p): tree_snapshot(p) for p in (repo, base)}
    out = tmp_path/'must not exist'
    with pytest.raises(ValueError, match='outside source kit whitelist: '+re.escape(unknown)):
        build_handoff.build(out, base, 'HEAD')
    assert not out.exists()
    assert protected == {str(p): tree_snapshot(p) for p in (repo, base)}


def cli(*args):
    return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts/team3_run.py'), *map(str,args)],
                          cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)


def passed(result, out):
    assert result.returncode == 0, result.stdout+result.stderr
    receipt = json.loads((out/'workflow.json').read_text(encoding='utf-8'))
    assert receipt['status'] == 'PASS' and receipt['protected_unchanged']
    assert receipt['commands'] and all(c['exit_code'] == 0 and not c['timed_out'] for c in receipt['commands'])
    return receipt


def test_explicit_fault_recheck_and_effective_config_evaluation_are_read_only(tmp_path):
    fixture = tmp_path/'fixture'
    event = fixture/'fault.json'
    write_json(event, dict(station_id=7, start_s=100, end_s=400,
                          start_utc='2026-08-03T06:01:40Z', end_utc='2026-08-03T06:06:40Z'))
    (fixture/'empty').mkdir()
    inputs_before = tree_snapshot(ROOT/'examples/synthetic')
    fixture_before = tree_snapshot(fixture)
    workflow = tmp_path/'explicit'
    automatic = passed(cli('synthetic', '--fault-event', event, '--out', workflow), workflow)
    assert len(automatic['commands']) == 4 and automatic['run_source_unchanged']
    source = workflow/'run'
    config = source/'effective_config.json'
    assert json.loads(config.read_text())['fault_event_path'] == str(event)
    (source/'empty').mkdir()  # Full tree protection includes directories omitted by file manifests.
    before = tree_snapshot(source)
    out = tmp_path/'separate recheck'
    passed(cli('recheck', '--source', source, '--out', out), out)
    assert json.loads((out/'recheck/recheck.json').read_text())['status'] == 'PASS'
    assert 'fault_event_path' not in yaml.safe_load((out/'config.yaml').read_text())
    common = ['evaluate', '--input-dir', source/'standard_input', '--config', config]
    initial = source/'tasks_baseline.csv'
    out = tmp_path/'initial evaluation'
    passed(cli(*common, '--tasks', initial, '--out', out), out)
    assert 'fault_event_path' not in yaml.safe_load((out/'config.yaml').read_text())
    out = tmp_path/'fault evaluation'
    evidence = [('--initial-plan', initial), ('--event', source/'fault_event.json'),
                ('--interrupted', source/'interrupted_baseline.csv')]
    passed(cli(*common, '--tasks', source/'tasks_baseline_replanned.csv',
               *[x for pair in evidence for x in pair], '--out', out), out)
    # Each partial combination must be rejected even with a legitimate effective config.
    for n in (1, 2):
        for i, subset in enumerate(itertools.combinations(evidence, n)):
            out = tmp_path/f'incomplete_{n}_{i}'
            result = cli(*common, '--tasks', source/'tasks_baseline_replanned.csv',
                         *[x for pair in subset for x in pair], '--out', out)
            assert result.returncode == 2 and 'initial-plan, event AND interrupted' in result.stderr
            assert not out.exists()
    # Persisted planning injection remains forbidden in planning mode.
    out = tmp_path/'implicit injection'
    result = cli('windows', '--input-dir', source/'standard_input', '--config', config, '--out', out)
    assert result.returncode == 2 and '--fault-event' in result.stderr and not out.exists()
    assert tree_snapshot(source) == before
    assert tree_snapshot(fixture) == fixture_before
    assert tree_snapshot(ROOT/'examples/synthetic') == inputs_before


@pytest.mark.parametrize('field', ['reuse_source', 'frozen_sample'])
@pytest.mark.parametrize('mode', ['windows', 'evaluate', 'recheck'])
def test_frozen_tle_and_reuse_config_still_rejected(tmp_path, field, mode):
    source = tmp_path/'source'
    shutil.copytree(ROOT/'examples/synthetic', source/'standard_input')
    config = yaml.safe_load((ROOT/'configs/synthetic.yaml').read_text())
    config.update({field: str(tmp_path/'unavailable'), 'fault_event_path': str(tmp_path/'unused event')})
    path = source/'effective_config.json'
    write_json(path, config)
    (source/'empty').mkdir()
    before = tree_snapshot(source)
    out = tmp_path/'must not exist'
    args = ['--source', source] if mode == 'recheck' else ['--input-dir', source/'standard_input', '--config', path]
    if mode == 'evaluate':
        args += ['--tasks', source/'standard_input/targets.csv']
    result = cli(mode, *args, '--out', out)
    assert result.returncode == 2 and 'frozen TLE/reuse' in result.stderr
    assert not out.exists() and tree_snapshot(source) == before

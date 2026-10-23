"""Read standard window tables without scheduling, propagation or input mutation."""
import argparse
import collections
import json
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yaml
from planner.atomic_io import atomic_write_text
from planner.common import json_write
from planner.config import normalize
from planner.io_contract import integer, load_tables, parse_utc, table
from planner.path_safety import file_hash, guard_writes, tree_snapshot
from planner.process_guard import run_guarded

FILES = ('targets.csv', 'stations.csv', 'windows.csv', 'metadata.json')


def inspect(directory, out, source_label, station_ids=None, start_utc=None, end_utc=None):
    """Report full-table validation separately from an explicitly selected planning slice."""
    before = tree_snapshot(directory) if directory.is_dir() else None
    report = dict(status='RUNNING', source_label=source_label, source_claim_verified=False,
                  input_directory=str(directory), files={}, checked_scope='NOT_COMPLETED',
                  checks={}, errors=[], physical_conditions_independently_verified=False,
                  scheduling='NOT_RUN', orbit_propagation='NOT_RUN')
    code = 0
    try:
        for name in FILES:
            path = directory / name
            data = path.read_bytes()
            encoding = 'utf-8' if name.endswith('.json') else 'utf-8-sig'
            item = dict(bytes=len(data), sha256=file_hash(path), required_encoding=encoding)
            report['files'][name] = item
            try:
                data.decode(encoding, errors='strict')
                item['decoding'] = 'PASS'
                item['bom_present'] = data.startswith(b'\xef\xbb\xbf')
            except UnicodeError:
                item['decoding'] = 'FAIL'
                raise
            json_write(out / 'inspection.json', report)
        meta = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
        start, end = parse_utc(meta['horizon_start_utc']), parse_utc(meta['horizon_end_utc'])
        ids = [integer(row['station_id'], 'station_id', 1)
               for row in table(directory / 'stations.csv', {'station_id'}, 'station_id')]
        base = yaml.safe_load((ROOT / 'configs/synthetic.yaml').read_text(encoding='utf-8'))
        base.update(input_mode='windows', input_dir=str(directory), station_ids=ids,
                    start_utc=meta['horizon_start_utc'], horizon_seconds=int((end-start).total_seconds()),
                    method='baseline', cache_dir=str(out.parent / (out.name + '_runtime_cache')))
        full = normalize(base)
        records, stations, windows, _, metadata = load_tables(directory, full)
        durations = [w['duration_s'] for w in windows]
        report.update(checked_scope='ALL_FOUR_FILES_ALL_ROWS', metadata=metadata,
                      counts=dict(targets=len(records), stations=len(stations), windows=len(windows)),
                      targets_by_priority=dict(collections.Counter(r['priority'] for r in records)),
                      utc_range=dict(start=meta['horizon_start_utc'], end=meta['horizon_end_utc']),
                      window_duration_seconds=dict(min=min(durations, default=None), max=max(durations, default=None),
                          median=statistics.median(durations) if durations else None,
                          less_than_120=sum(d<120 for d in durations),
                          can_fit_120=sum(d>=120 for d in durations), can_fit_240=sum(d>=240 for d in durations)),
                      filters_applied_declaration=meta['filters_applied'],
                      checks=dict(references='PASS', duplicates='PASS', utc='PASS', metadata='PASS', scores='PASS'))
        config = dict(full)
        if station_ids is not None: config['station_ids'] = station_ids
        if start_utc is not None: config['start_utc'] = start_utc
        selected_end = end_utc or meta['horizon_end_utc']
        config['horizon_seconds'] = int((parse_utc(selected_end)-parse_utc(config['start_utc'])).total_seconds())
        config = normalize(config)
        _, selected_stations, selected_windows, _, _ = load_tables(directory, config)
        report['planning_selection'] = dict(station_ids=config['station_ids'], start_utc=config['start_utc'],
            end_utc=selected_end, horizon_seconds=config['horizon_seconds'], windows=len(selected_windows),
            explicit_subset=station_ids is not None or start_utc is not None or end_utc is not None,
            clipping='Only the explicitly selected planning slice may clip windows; original files unchanged')
        atomic_write_text(out / 'prepared_windows.yaml', yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        report.update(status='PASS', prepared_config='prepared_windows.yaml',
                      notes=['Short legal windows are retained; overlapping windows do not allow concurrent tasks.',
                             'Window mode uses all supplied targets; seed does not resample.',
                             'Parsing success does not establish scheduling success or physical validity.'])
    except (FileNotFoundError, ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as error:
        code = 3 if isinstance(error, FileNotFoundError) else 2
        report.update(status='BLOCKED' if code == 3 else 'FAIL')
        report['errors'].append(dict(type=type(error).__name__, reason=str(error), coverage='first error; later checks not certified'))
    finally:
        after = tree_snapshot(directory) if directory.is_dir() else None
        report.update(input_tree_before=before, input_tree_after=after, input_unchanged=before == after)
        if before != after:
            code = 2; report.update(status='FAIL')
            report['errors'].append(dict(reason='input tree changed during read-only inspection'))
        json_write(out / 'inspection.json', report)
    return code


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', required=True); p.add_argument('--out', required=True)
    p.add_argument('--source-label', required=True, help='Declared provenance, never inferred from folder name')
    p.add_argument('--station-ids', type=int, nargs='+'); p.add_argument('--start-utc'); p.add_argument('--end-utc')
    p.add_argument('--budget-seconds', type=float, default=30)
    p.add_argument('--worker-parent', type=int, help=argparse.SUPPRESS)
    a = p.parse_args(); directory = Path(a.input_dir).resolve(); out = Path(a.out).resolve()
    try:
        guard_writes([out], [directory])
        if not 0 < a.budget_seconds <= 300: raise ValueError('budget must be >0 and <=300 seconds')
        if a.worker_parent is not None:
            launch = json.loads((out / 'launch.json').read_text(encoding='utf-8'))
            if a.worker_parent != os.getppid() or launch['parent_pid'] != os.getppid() or {x.name for x in out.iterdir()} != {'launch.json','console.log'}:
                raise ValueError('worker requires a fresh live parent-owned directory')
            return inspect(directory, out, a.source_label, a.station_ids, a.start_utc, a.end_utc)
        if out.exists(): raise ValueError('inspection output must be a new directory')
        out.mkdir(parents=True, exist_ok=False)
        json_write(out / 'launch.json', dict(parent_pid=os.getpid(), input_directory=str(directory)))
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), *sys.argv[1:], '--worker-parent', str(os.getpid())]
        try:
            receipt = run_guarded(command, timeout=a.budget_seconds, log_path=out/'console.log')
        except OSError as error:
            receipt = dict(exit_code=3, timed_out=False, reason=str(error))
        json_write(out / 'execution.json', receipt)
        if receipt['exit_code'] not in (0, 2, 3): receipt['exit_code'] = 2
        partial = json.loads((out / 'inspection.json').read_text(encoding='utf-8')) if (out / 'inspection.json').exists() else {}
        if receipt.get('timed_out') or partial.get('status') not in ('PASS','FAIL','BLOCKED'):
            json_write(out / 'inspection.json', dict(status='BLOCKED' if receipt['exit_code']==3 else 'FAIL',
                source_label=a.source_label, checked_scope='NOT_COMPLETED', input_unchanged='NOT_VERIFIED',
                reason=receipt.get('reason','worker did not finish within its guarded execution'), execution=receipt, partial_report=partial))
        print(json.dumps(dict(report=str(out/'inspection.json'), exit_code=receipt['exit_code'])))
        return receipt['exit_code']
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('FAIL: '+str(error), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())

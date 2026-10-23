"""Read-only reuse of a sealed run; no re-sampling or changed candidate rules."""
import csv
import hashlib
import json
import shutil
from pathlib import Path
from .common import digest, json_write, csv_tasks, utc_at
from .io_contract import load_tables, parse_utc
from .validator import IndependentValidator


def json_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def verify_seal(source):
    from .runner import tree_hashes
    source=Path(source)
    actual=tree_hashes(source)
    expected=json.loads((source/'evidence_manifest.json').read_text(encoding='utf-8'))
    if any(actual.get(k)!=v for k,v in expected.items()) or set(actual)!=set(expected)|{'evidence_manifest.json'}:
        raise ValueError('frozen source seal differs: '+str(source))
    return actual


def prepare_frozen(config,out,clock):
    source=Path(config['reuse_source']).resolve()
    before=verify_seal(source)
    old=json.loads((source/'effective_config.json').read_text(encoding='utf-8'))
    context=json.loads((source/'evaluation_context.json').read_text(encoding='utf-8'))
    keys=['seed','station_ids','sample_counts','start_utc','horizon_seconds','candidate_start_step_seconds',
          'max_starts_per_window_duration','durations_seconds','switch_seconds','elevation_degrees']
    for key in keys:
        if config.get(key)!=old.get(key): raise ValueError('frozen experiment parameter mismatch: '+key)
    if old['input_mode']!='tle' or config['input_mode']!='tle':
        raise ValueError('frozen real experiment requires an authoritative TLE source')
    day=parse_utc(context['day']); sample=context['sample']
    records,stations=context['records'],context['stations']
    if sorted(r['satnum'] for r in records)!=sorted(n for group in sample['selected'].values() for n in group):
        raise ValueError('frozen sample/target linkage mismatch')
    raw=Path(config['input_dir']).resolve()
    raw_hashes={p.name:dict(sha256=digest(p),bytes=p.stat().st_size) for p in raw.iterdir() if p.is_file()}
    if raw_hashes!=sample['input_hashes']: raise ValueError('raw input differs from frozen source')
    _,_,standard_windows,_,metadata=load_tables(source/'standard_input',config)
    with (source/'windows.csv').open(encoding='utf-8',newline='') as f: windows=list(csv.DictReader(f))
    for row in windows:
        for key in ('satnum','station_id','start_s','end_s','duration_s'): row[key]=int(row[key])
        for key in ('min_elevation','max_elevation'):
            if row.get(key): row[key]=float(row[key])
    fields=('window_id','satnum','station_id','start_s','end_s')
    if [[w[k] for k in fields] for w in windows]!=[[w[k] for k in fields] for w in standard_windows]:
        raise ValueError('standard and raw window tables differ')
    for filename in ('windows.csv','frozen_sample.json','input_hashes.json','propagation_errors.json'):
        shutil.copyfile(source/filename,out/filename)
    config['frozen_sample']=str(source/'frozen_sample.json')
    json_write(out/'effective_config.json',config)
    json_write(out/'cache.json',dict(hit=True,mode='sealed_source_reuse',source=str(source),
                                    cold_window_computation=False,source_window_sha256=digest(source/'windows.csv')))
    identity=dict(source=str(source),source_hashes_before=before,parameters={k:config[k] for k in keys},
                  original_input_hashes=raw_hashes,sample_ids_sha256=json_hash(sorted(r['satnum'] for r in records)),
                  windows_sha256=digest(source/'windows.csv'),reference_candidates_sha256=digest(source/'candidates.csv'),
                  source_versions=json.loads((source/'versions.json').read_text(encoding='utf-8')))
    json_write(out/'input_reuse.json',identity)
    validator=IndependentValidator(config,day,sample,windows,clock)
    errors=json.loads((source/'propagation_errors.json').read_text(encoding='utf-8'))
    return records,stations,day,sample,metadata,windows,validator,errors,identity


def check_candidates(candidates,config,out,identity):
    source=Path(config['reuse_source'])
    reference=csv_tasks(source/'candidates.csv')
    identical=candidates==reference
    identity.update(generated_candidates_sha256=digest(out/'candidates.csv'),
                    candidate_bytes_identical=digest(out/'candidates.csv')==digest(source/'candidates.csv'),
                    candidate_semantics_identical=identical,
                    shared_candidate_semantics_sha256=json_hash(candidates),
                    methods_share_complete_candidate_list=True)
    json_write(out/'input_reuse.json',identity)
    if not identical: raise ValueError('regenerated candidate list differs from frozen candidates')


def load_fixed_event(path,station_ids,day,horizon):
    """Keep source-plan annotations separately; inject only physical event parameters."""
    event=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(event,dict) or any(type(event.get(k)) is not int for k in ('station_id','start_s','end_s')):
        raise ValueError('fixed fault requires integer station_id/start_s/end_s')
    if event['station_id'] not in station_ids or not 0<=event['start_s']<event['end_s']<=horizon:
        raise ValueError('fixed fault station/interval invalid')
    for key,s in [('start_utc',event['start_s']),('end_utc',event['end_s'])]:
        if event.get(key)!=utc_at(day,s): raise ValueError('fixed fault UTC/seconds mismatch')
    physical={k:event[k] for k in ('station_id','start_s','end_s','start_utc','end_utc')}
    return dict(physical,effective=True,selection='explicit_frozen_physical_event'),event


def fault_impact(initial,event):
    a,b,sid=event['start_s'],event['end_s'],event['station_id']
    groups=dict(completed=[],locked=[],interrupted=[],affected_future=[])
    for r in initial:
        if r['end_s']<=a: groups['completed'].append(r['task_id'])
        elif r['start_s']<a<r['end_s']:
            groups['interrupted' if r['station_id']==sid else 'locked'].append(r['task_id'])
        elif r['station_id']==sid and r['start_s']<b and r['end_s']>a:
            groups['affected_future'].append(r['task_id'])
    return dict(counts={k:len(v) for k,v in groups.items()},task_ids=groups)


def changes_by_target(initial,new):
    old={r['satnum']:r for r in initial}; after={r['satnum']:r for r in new}
    changes=[]
    for n in sorted(set(old)|set(after)):
        a,b=old.get(n),after.get(n)
        kind='added' if a is None else 'deleted' if b is None else 'retained' if all(a[k]==b[k] for k in ('station_id','start_utc','end_utc','duration_s')) else 'moved_or_duration_changed'
        changes.append(dict(target_id=n,change=kind,before=a,after=b))
    counts={k:sum(r['change']==k for r in changes) for k in ('added','deleted','retained','moved_or_duration_changed')}
    return dict(counts=counts,net_adjusted_target_count=len(changes)-counts['retained'],changes=changes)

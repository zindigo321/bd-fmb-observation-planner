"""Experiment parameters versus explicitly fixed smoke business assumptions."""
from pathlib import Path
from .io_contract import integer, parse_utc


def normalize(config):
    c=dict(config)
    c.setdefault('input_mode','tle')
    c.setdefault('method','both')
    c.setdefault('horizon_seconds',86400)
    c.setdefault('budget_seconds',300)
    c.setdefault('save_margin_seconds',1)
    c.setdefault('cache_dir','outputs/window_cache')
    if c.get('end_utc'):
        if not c.get('start_utc'): raise ValueError('end_utc requires start_utc')
        c['horizon_seconds']=int((parse_utc(c['end_utc'])-parse_utc(c['start_utc'])).total_seconds())
    elif c.get('start_utc'):
        parse_utc(c['start_utc'])
    for key in ('horizon_seconds','coarse_step_seconds','fine_step_seconds','candidate_start_step_seconds','max_starts_per_window_duration','fault_seconds'):
        c[key]=integer(c[key],key,1)
    c['seed']=integer(c['seed'],'seed')
    counts=c.get('sample_counts',c.get('sample_per_priority',20))
    if isinstance(counts,int): counts={k:counts for k in ('high','medium','low')}
    if not isinstance(counts,dict) or set(counts)!= {'high','medium','low'}: raise ValueError('invalid sample_counts')
    c['sample_counts']={k:integer(v,'sample_counts') for k,v in counts.items()}
    if sum(c['sample_counts'].values())==0: raise ValueError('empty sample')
    if not isinstance(c.get('station_ids'),list) or not c['station_ids']: raise ValueError('station_ids required')
    c['station_ids']=[integer(x,'station_id',1) for x in c['station_ids']]
    if len(set(c['station_ids']))!=len(c['station_ids']): raise ValueError('duplicate station_ids')
    if c['input_mode'] not in ('tle','windows') or c['method'] not in ('baseline','improved','both'): raise ValueError('invalid input_mode/method')
    if isinstance(c['budget_seconds'],bool) or not 0<float(c['budget_seconds'])<=300: raise ValueError('budget must be >0 and <=300 seconds')
    if not 0<=float(c['save_margin_seconds'])<float(c['budget_seconds']): raise ValueError('invalid save margin')
    if c['durations_seconds'] != [120,240] or c['switch_seconds']!=30 or c['elevation_degrees']!=[10,85]:
        raise ValueError('fixed smoke assumptions: durations [120,240], switch 30, elevation [10,85]')
    if c['coarse_step_seconds']>30 or c['fine_step_seconds']!=1: raise ValueError('invalid geometry resolution')
    c['input_dir']=str(Path(c['input_dir']).resolve())
    return c

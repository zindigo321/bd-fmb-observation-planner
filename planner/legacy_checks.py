"""Inherited real-geometry negative fixtures."""
from .common import *

def counterexample_tests(validator, base, day, event, out, clock):
    if len(base)<2:
        raise ValueError('Too few actual tasks for counterexample fixtures')
    fixtures=[]
    first=dict(base[0]); second=dict(next(r for r in base if r['satnum']!=first['satnum']))
    def shift(r,a):
        r=dict(r); r.update(start_s=a,end_s=a+r['duration_s'],start_utc=utc_at(day,a),end_utc=utc_at(day,a+r['duration_s']))
        return r
    overlap=shift(second, first['start_s']+1); overlap['station_id']=first['station_id']; overlap['task_id']='BAD_OVERLAP'
    fixtures.append(('overlap',[first,overlap],None))
    gap=shift(second,first['end_s']+1); gap['station_id']=first['station_id']; gap['task_id']='BAD_SWITCH'
    fixtures.append(('switch_gap',[first,gap],None))
    outside=shift(first,-1); outside['task_id']='BAD_HORIZON'
    fixtures.append(('window_or_horizon',[outside],None))
    duplicate=dict(first,task_id='BAD_DUPLICATE')
    fixtures.append(('duplicate_success',[first,duplicate],None))
    missing=dict(first); del missing['satnum']; missing['task_id']='BAD_MISSING'
    fixtures.append(('invalid_data',[missing],None))
    illegal=dict(first,station_id=999,task_id='BAD_ILLEGAL_STATION')
    fixtures.append(('invalid_data',[illegal],None))
    nonfinite=dict(first,score=float('nan'),task_id='BAD_NONFINITE')
    # JSON is strict: represent this fixture's illegal value explicitly when saving.
    fixtures.append(('invalid_data',[nonfinite],None))
    interrupted_wrong=dict(first,status='interrupted',points_int=0,score=0,task_id='BAD_INTERRUPTED_BYPASS')
    fixtures.append(('invalid_data',[interrupted_wrong],None))
    if event.get('effective'):
        fault=shift(first,event['start_s']); fault['station_id']=event['station_id']; fault['task_id']='BAD_FAULT'
        fixtures.append(('fault_occupancy',[fault],event))
    # Find an actual below-threshold second from new true propagation, not hardcode an angle.
    n=first['satnum']; sid=first['station_id']
    ss=np.arange(0,validator.config['horizon_seconds'],120,dtype=int)
    clock.check()
    t=validator.ts.utc(day.year,day.month,day.day,day.hour,day.minute,day.second+ss)
    alt=(validator.targets[n].at(t)-validator.sites[sid].at(t)).altaz()[0].degrees
    bad=np.flatnonzero(np.isfinite(alt)&((alt<10)|(alt>85)))
    if len(bad):
        angle=shift(first,int(ss[bad[0]])); angle['task_id']='BAD_ELEVATION'
        fixtures.append(('elevation',[angle],None))
    else:
        for r in base:
            clock.check()
            n,sid=r['satnum'],r['station_id']
            alt=(validator.targets[n].at(t)-validator.sites[sid].at(t)).altaz()[0].degrees
            bad=np.flatnonzero(np.isfinite(alt)&((alt<10)|(alt>85)))
            if len(bad):
                angle=shift(r,int(ss[bad[0]])); angle['task_id']='BAD_ELEVATION'
                fixtures.append(('elevation',[angle],None)); break
    results=[]
    covered=set()
    for i,(expected,tasks,fault) in enumerate(fixtures):
        clock.check()
        report=validator.check(tasks,fault=fault,label=f'counterexample_{i}_{expected}')
        triggered=report['violations_by_category'][expected]>0
        serializable_tasks=[{k:('NaN (actual float NaN tested)' if isinstance(v,float) and not math.isfinite(v) else v)
                             for k,v in row.items()} for row in tasks]
        json_write(out / 'checks' / f'counterexample_{i}_{expected}.json',dict(expected_category=expected,triggered=triggered,
                                                                                 mutated_actual_tasks=serializable_tasks,fault=fault,report=report))
        results.append(dict(test=i,expected_category=expected,triggered=triggered,actual_categories=report['violations_by_category'],
                            detailed_report=f'checks/counterexample_{i}_{expected}.json'))
        if triggered: covered.add(expected)
    summary=dict(tests=results,required_categories=CHECK_CATEGORIES,covered_categories=sorted(covered),
                 all_required_triggered=set(CHECK_CATEGORIES).issubset(covered),actual_execution=True)
    json_write(out / 'counterexample_tests.json',summary)
    return summary

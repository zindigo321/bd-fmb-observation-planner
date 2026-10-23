"""Generate an offline HTML replay from sealed, independently checked experiment artifacts."""
import argparse
import collections
import json
import sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import csv_tasks,digest,json_write
from planner.experiment_inputs import verify_seal


def load_case(case):
    directory=Path(case['directory'])
    verify_seal(directory)
    def read(name): return json.loads((directory/name).read_text(encoding='utf-8'))
    metrics=read('metrics.json'); context=read('evaluation_context.json')
    if metrics['status']=='BLOCKED': raise FileNotFoundError('source run is BLOCKED; complete evidence is unavailable')
    if metrics['status']!='PASS': raise ValueError('source run status is '+metrics['status'])
    if case['seed']!=metrics['seed']: raise ValueError('case seed differs from actual run')
    targets={r['satnum']:r for r in context['records']}
    plans={}; evidence={}
    for method in ('baseline','improved'):
        initial_name=method; after_name='baseline_replanned' if method=='baseline' else 'replanned'
        tasks={}; checks={}
        for phase,name in [('initial',initial_name),('replanned',after_name)]:
            rows=csv_tasks(directory/f'schedule_{name}.csv'); check=read(f'checks/{name}.json')
            summary=metrics['plans'][name]
            for r in rows:
                if r['duration_s'] not in (120,240): raise ValueError('unsupported task duration')
                expected={'high':5,'medium':3,'low':2}[targets[r['satnum']]['priority']]*(3 if r['duration_s']==120 else 5)
                if r['points_int']!=expected or r['score']!=expected/5:
                    raise ValueError('task score differs from authoritative priority/duration')
            points=sum({'high':5,'medium':3,'low':2}[targets[r['satnum']]['priority']]*(3 if r['duration_s']==120 else 5) for r in rows)
            coverage=len({r['satnum'] for r in rows})
            priorities=dict(collections.Counter(targets[n]['priority'] for n in {r['satnum'] for r in rows}))
            for result in (check,summary):
                if result['status']!='PASS' or result['violation_count']!=0: raise ValueError('independent validation did not pass')
                if result['points_int']!=points or result['task_score']!=points/5 or result['coverage']!=coverage or result['by_priority_coverage']!=priorities:
                    raise ValueError('task/source-priority/check/metric mismatch')
            for key,denominator in [('coverage_all',metrics['target_count']),('coverage_executable',metrics['executable_target_count'])]:
                expected=dict(numerator=coverage,denominator=denominator,rate=coverage/denominator if denominator else None)
                if summary[key]!=expected: raise ValueError('coverage denominator/rate mismatch')
            if check['evaluation_scope']=='raw_TLE_per_second' and any(not r['propagated_from_raw_TLE'] for r in check['task_geometry_details']):
                raise ValueError('TLE scope has missing propagation evidence')
            tasks[phase]=rows; checks[phase]=check
            evidence[name]=dict(tasks_sha256=digest(directory/f'schedule_{name}.csv'),checks_sha256=digest(directory/'checks'/f'{name}.json'),
                                task_count=len(rows),points_int=points,coverage=coverage)
        stages={r['stage']:r['seconds'] for r in read('timing.json')}
        plans[method]=dict(**tasks,checks=checks,history=read(f'history_{method}.json'),impact=metrics['fault_impacts'][method],
                          changes=read(f'changes_{method}.json'),initial_metrics=metrics['plans'][initial_name],replanned_metrics=metrics['plans'][after_name],
                          initial_seconds=stages['scheduling_'+method],replanned_seconds=stages['replanning_'+method])
    return dict(id=case['id'],seed=case['seed'],scenario=case['scenario'],status='PASS',methods=plans,
                event=read('fault_event.json'),data_version=metrics['data_version'],horizon_seconds=metrics['horizon_seconds'],
                start_utc=context['day'],run_id=directory.name,evidence_path=str(directory),
                station_ids=[s['station_id'] for s in context['stations']],
                candidate_upper_bound=metrics['candidate_upper_bound'],cache=read('cache.json'),evidence=evidence,
                scope=metrics['plans']['baseline']['evaluation_scope'])


def build(summary_path,out):
    summary_path=Path(summary_path); out=Path(out)
    if out.exists(): raise ValueError('demo output directory must be new')
    if summary_path.exists():
        try: destinations=json.loads(summary_path.read_text(encoding='utf-8')).get('cases',[])
        except (ValueError,AttributeError): destinations=[]
        for case in destinations:
            if isinstance(case,dict) and case.get('directory'):
                directory=Path(case['directory']).resolve()
                if out.resolve()==directory or out.resolve().is_relative_to(directory):
                    raise ValueError('demo must not write inside sealed source')
    out.mkdir(parents=True,exist_ok=False)
    cases=[]; issues=[]
    try:
        summary=json.loads(summary_path.read_text(encoding='utf-8'))
        if not summary.get('cases'): raise FileNotFoundError('summary has no case evidence')
        for case in summary['cases']:
            directory=Path(case['directory']).resolve()
            if out.resolve()==directory or out.resolve().is_relative_to(directory): raise ValueError('demo must not write inside sealed source')
            try: cases.append(load_case(case))
            except (FileNotFoundError,ValueError,KeyError,json.JSONDecodeError) as e:
                issues.append(dict(case=case.get('id'),status='BLOCKED' if isinstance(e,FileNotFoundError) else 'FAIL',reason=str(e)))
    except (FileNotFoundError,ValueError,KeyError,json.JSONDecodeError) as e:
        issues.append(dict(status='BLOCKED' if isinstance(e,FileNotFoundError) else 'FAIL',reason=str(e)))
    status='FAIL' if any(i['status']=='FAIL' for i in issues) else 'BLOCKED' if issues or not cases else 'PASS'
    synthetic=bool(cases) and all('synthetic' in c['data_version'].lower() for c in cases)
    physical=bool(cases) and all(c['scope']=='raw_TLE_per_second' for c in cases)
    disclaimer='合成契约示例；不代表真实观测。' if synthetic else '真实轨道几何冒烟演示；完整光学条件未验证。' if physical else '供应窗口调度演示；窗口物理及光学条件未独立验证。'
    payload=dict(schema_version=1,status=status,cases=cases,issues=issues,synthetic=synthetic,
                 generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                 disclaimer=disclaimer+'预计算结果回放，非实时卫星运行，浏览器不重新求解。')
    text=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=Path(__file__).resolve().parents[1]/'demo'/'template.html'
    html=template.read_text(encoding='utf-8').replace('__DEMO_PAYLOAD__',text)
    (out/'index.html').write_text(html,encoding='utf-8')
    json_write(out/'demo_data_check.json',dict(status=status,case_count=len(cases),issues=issues,
        source_summary=str(summary_path.resolve()),summary_sha256=digest(summary_path) if summary_path.exists() else None,
        html_sha256=digest(out/'index.html'),cases={c['id']:c['evidence'] for c in cases},
        browser_interaction='NOT_RUN',checks='authoritative priority + actual duration + coverage + per-plan reports + sealed inputs'))
    return 0 if status=='PASS' else 3 if status=='BLOCKED' else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--summary',required=True); p.add_argument('--out',required=True)
    a=p.parse_args(); raise SystemExit(build(a.summary,a.out))

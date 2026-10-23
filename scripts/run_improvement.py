"""Prepare frozen cases, run E3/E4 serially under the round ledger, and summarize."""
import argparse
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.budget_run import execute


def prepare(spec_path,out):
    from planner.common import json_write,digest
    from planner.experiment_inputs import verify_seal,json_hash
    spec=json.loads(Path(spec_path).read_text(encoding='utf-8'))
    snapshots=out/'snapshots'; snapshots.mkdir(exist_ok=False)
    cases=[]; sources={}
    for item in spec['seeds']:
        source=Path(item['source']).resolve(); hashes=verify_seal(source)
        config=json.loads((source/'effective_config.json').read_text(encoding='utf-8'))
        sample=json.loads((source/'frozen_sample.json').read_text(encoding='utf-8'))
        if config['seed']!=item['seed'] or sample['seed']!=item['seed']: raise ValueError('seed/source mismatch')
        event=snapshots/f'event_seed{item["seed"]}.json'; shutil.copyfile(source/'fault_event.json',event)
        sources[str(item['seed'])]=dict(path=str(source),hashes_before=hashes,
            selected_ids_sha256=json_hash(sorted(n for g in sample['selected'].values() for n in g)),
            sample_sha256=digest(source/'frozen_sample.json'),windows_sha256=digest(source/'windows.csv'),
            candidates_sha256=digest(source/'candidates.csv'),input_hashes_sha256=digest(source/'input_hashes.json'))
        cases.append(dict(id=f'E3_seed{item["seed"]}',scenario='early',seed=item['seed'],source=str(source),
                          config=str(Path(item['config']).resolve()),event=str(event.resolve())))
    late=snapshots/'late_fault.json'; shutil.copyfile(spec['late_fault'],late)
    base=next(c for c in cases if c['seed']==42)
    cases.append(dict(base,id='E4_seed42_late',scenario='late',event=str(late.resolve())))
    json_write(out/'frozen_inputs.json',dict(spec_sha256=digest(spec_path),sources=sources,cases=cases))
    return 0


def summarize(out):
    from planner.common import json_write,csv_write,digest,csv_tasks
    from planner.experiment_inputs import verify_seal
    from planner.runner import tree_hashes
    frozen=json.loads((out/'frozen_inputs.json').read_text(encoding='utf-8'))
    rows=[]; cases=[]; checks={}
    for case in frozen['cases']:
        directory=out/case['id']; verify_seal(directory)
        metrics=json.loads((directory/'metrics.json').read_text(encoding='utf-8'))
        event=json.loads((directory/'fault_event.json').read_text(encoding='utf-8'))
        source_event=json.loads(Path(case['event']).read_text(encoding='utf-8'))
        reuse=json.loads((directory/'input_reuse.json').read_text(encoding='utf-8'))
        timing={r['stage']:r['seconds'] for r in metrics['runtime']['stages']}
        same_event=all(event[k]==source_event[k] for k in ('station_id','start_s','end_s','start_utc','end_utc'))
        shared=reuse['candidate_semantics_identical'] and reuse['methods_share_complete_candidate_list']
        evidence={}
        for method in ('baseline','improved'):
            after_name='baseline_replanned' if method=='baseline' else 'replanned'
            a,b=metrics['plans'][method],metrics['plans'][after_name]
            reports=[json.loads((directory/'checks'/f'{n}.json').read_text(encoding='utf-8')) for n in (method,after_name)]
            for n,r in zip((method,after_name),reports):
                tasks=csv_tasks(directory/f'schedule_{n}.csv')
                if r['task_score']!=sum(t['points_int'] for t in tasks)/5 or r['coverage']!=len({t['satnum'] for t in tasks}):
                    raise ValueError('task/report mismatch')
                if r['status']!='PASS' or r['evaluation_scope']!='raw_TLE_per_second': raise ValueError('missing actual TLE validation')
            impact=metrics['fault_impacts'][method]['counts']
            upper=metrics['candidate_upper_bound']['task_score']
            row=dict(case=case['id'],scenario=case['scenario'],seed=case['seed'],method=method,
                     targets=metrics['target_count'],stations=metrics['station_count'],windows=metrics['window_count'],candidates=metrics['candidate_count'],
                     initial_score=a['task_score'],replanned_score=b['task_score'],
                     initial_gain_over_baseline=(a['points_int']-metrics['plans']['baseline']['points_int'])/5,
                     replanned_gain_over_baseline=(b['points_int']-metrics['plans']['baseline_replanned']['points_int'])/5,
                     initial_coverage=a['coverage'],replanned_coverage=b['coverage'],all_denominator=metrics['target_count'],executable_denominator=metrics['executable_target_count'],
                     initial_all_rate=a['coverage_all']['rate'],replanned_all_rate=b['coverage_all']['rate'],
                     initial_executable_rate=a['coverage_executable']['rate'],replanned_executable_rate=b['coverage_executable']['rate'],
                     initial_by_priority=json.dumps(a['by_priority_coverage'],sort_keys=True),replanned_by_priority=json.dumps(b['by_priority_coverage'],sort_keys=True),
                     initial_violations=a['violation_count'],replanned_violations=b['violation_count'],
                     prepare_seconds=timing['read_audit_and_freeze']+timing['window_computation_or_cache'],candidate_seconds=timing['candidate_generation'],
                     initial_seconds=timing['scheduling_'+method],replanned_seconds=timing['replanning_'+method],
                     validation_seconds=timing['validation_initial']+timing['validation_replanned'],
                     total_seconds=json.loads((directory/'execution.json').read_text())['seconds'],
                     cache_mode='sealed_source_reuse_not_cold',candidate_upper_bound=upper,initial_gap_to_upper=upper-a['task_score'],replanned_gap_to_initial_upper=upper-b['task_score'],
                     **impact,net_adjusted_targets=json.loads((directory/f'changes_{method}.json').read_text())['net_adjusted_target_count'],
                     evidence=str(directory.resolve()))
            rows.append(row); evidence[method]=dict(initial_status=reports[0]['status'],replanned_status=reports[1]['status'])
        late_ok=True
        if case['scenario']=='late':
            expected={'baseline':dict(completed=14,locked=1,interrupted=1,affected_future=2),
                      'improved':dict(completed=10,locked=1,interrupted=1,affected_future=4)}
            late_ok=all(metrics['fault_impacts'][k]['counts']==v for k,v in expected.items())
        checks[case['id']]=dict(candidate_bytes_identical=reuse['candidate_bytes_identical'],candidate_semantics_identical=shared,
                               physical_event_identical=same_event,source_unchanged=reuse['source_unchanged'],
                               late_expected_counts=late_ok,independent_checks=evidence)
        if not (shared and same_event and reuse['source_unchanged'] and late_ok): raise ValueError('fairness/history check failed: '+case['id'])
        cases.append(dict(case,directory=str(directory.resolve()),status=metrics['status']))
    sources_unchanged=all(tree_hashes(Path(v['path']))==v['hashes_before'] for v in frozen['sources'].values())
    if not sources_unchanged: raise ValueError('source evidence changed during experiment suite')
    csv_write(out/'comparison.csv',rows,list(rows[0]))
    lines=['# 本轮 E3/E4 实测对比','','已有算法整体流程比较；初始计划不同，因此故障后收益不单独归因于重规划器。',
           '','| 场景/seed | 方法 | 初始分 | 故障后分 | 初始/故障后收益 | 覆盖（全部/可执行） | 违例 | 排程/重规划秒 | 初始候选上界 |',
           '| --- | --- | ---: | ---: | --- | --- | --- | --- | ---: |']
    for r in rows:
        lines.append(f"| {r['scenario']}/{r['seed']} | {r['method']} | {r['initial_score']} | {r['replanned_score']} | {r['initial_gain_over_baseline']:+.1f}/{r['replanned_gain_over_baseline']:+.1f} | {r['replanned_coverage']}/{r['all_denominator']} · {r['replanned_coverage']}/{r['executable_denominator']} | {r['initial_violations']}/{r['replanned_violations']} | {r['initial_seconds']:.6f}/{r['replanned_seconds']:.6f} | {r['candidate_upper_bound']} |")
    lines+=['','完整字段（分档、两个覆盖率、准备/候选/校验/总耗时、故障影响、差距与证据路径）见 comparison.csv。',
            '改进耗时包含内部基线回退成本。数据准备为封存窗口复用，不是冷启动轨道计算。校验耗时为该案例两方法合计。',
            '上界为初始候选中逐目标最高分之和，忽略站点冲突，不是普遍最优性结论或故障后精确上界。',
            '三样本仅描述性比较，不声称统计显著或正式赛事成绩。完整光学条件未验证。']
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    json_write(out/'summary.json',dict(cases=cases,rows=rows,fairness=checks,sources_unchanged=sources_unchanged,
               acceptance=dict(algorithm_execution='PASS',independent_legality='PASS',history_preservation='PASS',
                               demo_data='NOT_RUN',browser_interaction='NOT_RUN',team_confirmation='PENDING_EXTERNAL',optional_evaluator='BLOCKED')))
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',default='configs/improvement_demo.json'); p.add_argument('--out',required=True)
    p.add_argument('--ledger'); p.add_argument('--prepare',action='store_true'); p.add_argument('--summarize',action='store_true')
    a=p.parse_args(); out=Path(a.out).resolve()
    if a.prepare: return prepare(a.spec,out)
    if a.summarize: return summarize(out)
    if not a.ledger: p.error('--ledger required')
    out.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-X','utf8',str(Path(__file__).resolve())]
    code=execute(a.ledger,command+['--prepare','--spec',a.spec,'--out',str(out)],timeout=60,output=out/'snapshots')
    if code: return code
    cases=json.loads((out/'frozen_inputs.json').read_text(encoding='utf-8'))['cases']
    for case in cases:
        ledger=json.loads(Path(a.ledger).read_text(encoding='utf-8')); cap=min(300,ledger['remaining_seconds'])
        if cap<=2: return 3
        cmd=[sys.executable,'-X','utf8','smoke_test.py','--config',case['config'],'--reuse-source',case['source'],
             '--fault-event',case['event'],'--method','both','--budget-seconds',str(cap),'--out',str(out/case['id'])]
        code=execute(a.ledger,cmd,timeout=cap,output=out/case['id'])
        if code: return code
    return execute(a.ledger,command+['--summarize','--out',str(out)],timeout=60,output=out/'summary.json')


if __name__=='__main__': raise SystemExit(main())

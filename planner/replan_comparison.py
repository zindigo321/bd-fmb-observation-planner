"""Controlled replanning from one independently frozen initial plan and shared history."""
import copy
import json
import shutil
import time
from pathlib import Path
from .common import Clock,TASK_FIELDS,csv_tasks,csv_write,digest,json_write
from .experiment_inputs import json_hash,verify_seal,load_fixed_event,fault_impact,changes_by_target
from .io_contract import load_tables,parse_utc
from .path_safety import tree_snapshot
from .runner import tree_hashes,versions
from .scheduler import replay_state,future_candidates,schedule
from .validator import IndependentValidator

CONDITIONS=('origin','initial','event','candidates','future','fixed','interrupted')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def plan_rows(rows):
    return [{k:r[k] for k in TASK_FIELDS} for r in rows]


def fingerprints(bundle):
    return {key:json_hash(bundle[key]) for key in CONDITIONS}


def assert_contract(bundle,expected):
    if set(expected)!=set(CONDITIONS) or fingerprints(bundle)!=expected:
        raise ValueError('common initial/history/candidate/source contract mismatch')


def paired_method(bundle,method,expected,clock):
    local=copy.deepcopy(bundle)
    assert_contract(local,expected)
    started=time.perf_counter()
    tasks=schedule(local['future'],method,fixed=local['fixed'],interrupted=local['interrupted'],clock=clock)
    seconds=time.perf_counter()-started
    assert_contract(local,expected)
    assert_contract(bundle,expected)
    return tasks,dict(seconds=seconds,inputs_before=expected,inputs_after=fingerprints(local),input_unchanged=True)


def points(rows,values):
    return sum(values[r['satnum']]*(3 if r['duration_s']==120 else 5) for r in rows)


def conditional_upper(fixed,future,values):
    occupied={r['satnum'] for r in fixed};best={}
    for c in future:
        if c['satnum'] in occupied:continue
        score=points([c],values);best[c['satnum']]=max(best.get(c['satnum'],0),score)
    fixed_points=points(fixed,values)
    return dict(points_int=fixed_points+sum(best.values()),task_score=(fixed_points+sum(best.values()))/5,
                fixed_points_int=fixed_points,future_points_int=sum(best.values()),
                definition='fixed successful history plus per-unfixed-target best fault-legal future candidate; ignores resource conflicts')


def validator_for(source,clock):
    config=read(source/'effective_config.json');context=read(source/'evaluation_context.json')
    raw=Path(config['input_dir'])
    raw_hashes={p.name:dict(sha256=digest(p),bytes=p.stat().st_size) for p in raw.iterdir() if p.is_file()}
    if raw_hashes!=context['sample']['input_hashes']:raise ValueError('authoritative raw inputs changed')
    if config['input_mode']!='tle':raise ValueError('E5 requires raw TLE verification')
    _,_,windows,day,_=load_tables(source/'standard_input',config)
    validator=IndependentValidator(config,day,context['sample'],windows,clock)
    if {r['satnum']:r['priority'] for r in context['records']}!=validator.priority:
        raise ValueError('source target priorities differ from raw input')
    return validator,config,context,day


def run(source,initial_path,event_path,reference_method,out,budget):
    started=time.perf_counter();source=Path(source).resolve();out=Path(out).resolve()
    verify_seal(source);source_before=tree_snapshot(source)
    config=read(source/'effective_config.json');context=read(source/'evaluation_context.json')
    if config['seed']!=42 or config['station_ids']!=[1,2,3] or config['horizon_seconds']!=86400:
        raise ValueError('E5 requires the frozen seed42 three-station day')
    raw_before=tree_snapshot(Path(config['input_dir']))
    out.mkdir(parents=True,exist_ok=False);clock=Clock(dict(config,budget_seconds=budget),out)
    try:
        t=time.perf_counter();validator,config,context,day=validator_for(source,clock)
        initial=plan_rows(read(initial_path));reference=csv_tasks(source/f'schedule_{reference_method}.csv')
        if initial!=reference:raise ValueError('common initial plan differs from authoritative source CSV')
        event,_=load_fixed_event(event_path,config['station_ids'],day,config['horizon_seconds'])
        expected_event=read(source/'fault_event.json')
        if any(event[k]!=expected_event[k] for k in ('station_id','start_s','end_s','start_utc','end_utc')):
            raise ValueError('E5 event differs from frozen late event')
        candidates=csv_tasks(source/'candidates.csv')
        reuse=read(source/'input_reuse.json')
        if digest(source/'candidates.csv')!=reuse['reference_candidates_sha256']:
            raise ValueError('source candidates differ from frozen reference')
        preparation_seconds=time.perf_counter()-t
        t=time.perf_counter();initial_report=validator.check(initial,label='common_initial')
        initial_validation_seconds=time.perf_counter()-t
        old=read(source/'metrics.json')['plans'][reference_method]
        if initial_report['status']!='PASS' or initial_report['points_int']!=old['points_int'] or initial_report['coverage']!=old['coverage']:
            raise ValueError('common initial independent check failed')
        t=time.perf_counter()
        completed,locked,interrupted,cancelled=replay_state(copy.deepcopy(initial),event,day)
        fixed=completed+locked;future=future_candidates(candidates,fixed,event)
        impact=fault_impact(initial,event)
        expected_counts=dict(completed=14,locked=1,interrupted=1,affected_future=2) if reference_method=='baseline' else dict(completed=10,locked=1,interrupted=1,affected_future=4)
        if impact['counts']!=expected_counts:raise ValueError('unexpected shared history counts')
        history_seconds=time.perf_counter()-t
        origin=dict(source=str(source),reference_method=reference_method,initial_plan_path=str(Path(initial_path).resolve()),
                    initial_file_sha256=digest(initial_path),reference_csv_sha256=digest(source/f'schedule_{reference_method}.csv'))
        bundle=dict(origin=origin,initial=initial,event=event,candidates=candidates,future=future,fixed=fixed,interrupted=interrupted)
        expected=fingerprints(bundle)
        shared=out/'shared';shared.mkdir()
        shutil.copyfile(initial_path,shared/'initial_plan.json')
        shutil.copyfile(source/f'schedule_{reference_method}.csv',shared/'initial_plan.csv')
        shutil.copyfile(source/'candidates.csv',shared/'candidates.csv')
        json_write(shared/'event.json',event);json_write(shared/'bundle.json',bundle)
        json_write(shared/'history.json',dict(completed=completed,locked=locked,interrupted=interrupted,cancelled_future=cancelled))
        json_write(shared/'contract.json',expected)
        shared_before=tree_snapshot(shared)
        json_write(out/'common_inputs.json',dict(origin=origin,semantic_hashes=expected,shared_files=shared_before,impact=impact,
                    candidate_count=len(candidates),future_candidate_count=len(future),initial_check=initial_report))
        json_write(out/'effective_config.json',config);json_write(out/'evaluation_context.json',context)
        json_write(out/'versions.json',versions());shutil.copytree(source/'standard_input',out/'standard_input')
        json_write(out/'checks/common_initial.json',initial_report)
        upper=conditional_upper(fixed,future,validator.value)
        total=len(context['records']);executable=len({c['satnum'] for c in candidates if c['duration_s']==120})
        results={};rows=[]
        for method in ('baseline','improved'):
            # Each method gets a distinct deserialized copy of exactly the same sealed conditions.
            method_bundle=read(shared/'bundle.json')
            tasks,execution=paired_method(method_bundle,method,expected,clock)
            frozen_initial=plan_rows(read(shared/'initial_plan.json'))
            t=time.perf_counter()
            report=validator.check(tasks,read(shared/'bundle.json')['interrupted'],event,original_plan=frozen_initial,label=method)
            validation_seconds=time.perf_counter()-t
            if tree_snapshot(shared)!=shared_before:raise ValueError('shared snapshots modified')
            changes=changes_by_target(initial,tasks)
            csv_write(out/f'schedule_{method}.csv',tasks,TASK_FIELDS)
            csv_write(out/f'tasks_{method}.csv',[dict(r,target_id=r['satnum']) for r in tasks],['target_id']+TASK_FIELDS)
            csv_write(out/f'interrupted_{method}.csv',[dict(r,target_id=r['satnum']) for r in interrupted],['target_id']+TASK_FIELDS+['planned_end_s','planned_duration_s','planned_end_utc'])
            json_write(out/f'checks/{method}.json',report);json_write(out/f'changes_{method}.json',changes)
            json_write(out/f'conditions_{method}.json',execution)
            fixed_points=points(fixed,validator.value)
            row=dict(method=method,common_initial_source=str(Path(initial_path).resolve()),initial_file_sha256=origin['initial_file_sha256'],
                     initial_semantic_sha256=expected['initial'],common_conditions_sha256=json_hash(expected),
                     final_score=report['task_score'],points_int=report['points_int'],fixed_history_score=fixed_points/5,
                     new_tasks_score=(report['points_int']-fixed_points)/5,coverage=report['coverage'],all_denominator=total,executable_denominator=executable,
                     coverage_all_rate=report['coverage']/total,coverage_executable_rate=report['coverage']/executable,
                     by_priority_coverage=json.dumps(report['by_priority_coverage'],sort_keys=True),violations=report['violation_count'],
                     input_preparation_seconds=preparation_seconds,initial_validation_seconds=initial_validation_seconds,
                     shared_history_future_seconds=history_seconds,replan_seconds=execution['seconds'],validation_seconds=validation_seconds,
                     net_adjusted_targets=changes['net_adjusted_target_count'],**changes['counts'],
                     conditional_upper=upper['task_score'],gap_to_upper=(upper['points_int']-report['points_int'])/5,
                     history_preserved=report['status']=='PASS',evidence=str(out))
            results[method]=dict(report=report,execution=execution,changes=changes);rows.append(row)
        gain=(results['improved']['report']['points_int']-results['baseline']['report']['points_int'])/5
        source_unchanged=tree_snapshot(source)==source_before and tree_snapshot(Path(config['input_dir']))==raw_before
        passed=source_unchanged and all(r['report']['status']=='PASS' for r in results.values())
        elapsed=time.perf_counter()-started
        for row in rows:row.update(total_seconds=elapsed,gain_over_baseline=(row['points_int']-rows[0]['points_int'])/5)
        csv_write(out/'comparison.csv',rows,list(rows[0]))
        lines=['# E5：同初始计划、同历史的重规划对照','',f'共同初始来源：{origin["initial_plan_path"]}',f'初始文件 SHA256：`{origin["initial_file_sha256"]}`',
               f'初始语义 SHA256：`{expected["initial"]}`',f'共同条件 SHA256：`{json_hash(expected)}`','',
               '| 方法 | 总分 | 固定历史分 | 新任务分 | 覆盖（全部/可执行） | 高/中/低 | 违例 | 重规划秒 | 独立验证秒 | 新增/删除/移动/保留 | 净调整 | 条件上界 |',
               '| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |']
        for row in rows:
            coverage=json.loads(row['by_priority_coverage'])
            lines.append(f"| {row['method']} | {row['final_score']} | {row['fixed_history_score']} | {row['new_tasks_score']} | {row['coverage']}/{total} · {row['coverage']}/{executable} | {coverage.get('high',0)}/{coverage.get('medium',0)}/{coverage.get('low',0)} | {row['violations']} | {row['replan_seconds']:.6f} | {row['validation_seconds']:.6f} | {row['added']}/{row['deleted']}/{row['moved_or_duration_changed']}/{row['retained']} | {row['net_adjusted_targets']} | {upper['task_score']} |")
        lines += ['',f'改进减基线任务分：{gain:+.1f}。两方法完成/锁定/中断/受影响未来相同：'+str(impact['counts']),
                  f'共享输入准备 {preparation_seconds:.6f}s；共同初始独立验证 {initial_validation_seconds:.6f}s；历史/未来候选准备 {history_seconds:.6f}s；总计 {elapsed:.6f}s。',
                  f'证据目录：{out}',
                  '均为本次单次perf_counter观测；改进包含内部基线回退，校验与读取均在方法计时之外。',
                  '条件宽松上界为固定成功历史分＋未固定目标的故障后合法未来候选最高分，忽略资源冲突。',
                  '固定场景的受控验证，不声称统计显著、所有场景更优、正式评分或普遍最优；完整光学条件未验证。']
        (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        json_write(out/'summary.json',dict(schema='shared_initial_replanning_v1',status='PASS' if passed else 'FAIL',origin=origin,
            shared_conditions=expected,common_conditions_sha256=json_hash(expected),impact=impact,initial_score=initial_report['task_score'],
            initial_coverage=initial_report['coverage'],conditional_upper=upper,gain=gain,rows=rows,
            source_unchanged=source_unchanged,shared_snapshots_unchanged=tree_snapshot(shared)==shared_before,
            timing=dict(input_preparation_seconds=preparation_seconds,initial_validation_seconds=initial_validation_seconds,
                        history_future_seconds=history_seconds,total_seconds=elapsed),
            evaluation_scope='raw_TLE_per_second',optical_conditions='NOT_VERIFIED'))
        return 0 if passed else 2
    finally:clock.logfile.close()


def recheck(source,out,budget):
    source=Path(source).resolve();out=Path(out).resolve();verify_seal(source);before=tree_snapshot(source)
    config=read(source/'effective_config.json');out.mkdir(parents=True,exist_ok=False)
    clock=Clock(dict(config,budget_seconds=budget),out)
    try:
        validator,_,_,_=validator_for(source,clock)
        bundle=read(source/'shared/bundle.json');expected=read(source/'shared/contract.json')
        assert_contract(bundle,expected)
        if read(source/'summary.json')['shared_conditions']!=expected:raise ValueError('summary common contract differs')
        initial=plan_rows(read(source/'shared/initial_plan.json'))
        if initial!=bundle['initial'] or initial!=csv_tasks(source/'shared/initial_plan.csv'):raise ValueError('initial snapshot differs')
        if csv_tasks(source/'shared/candidates.csv')!=bundle['candidates'] or read(source/'shared/event.json')!=bundle['event']:raise ValueError('shared candidate/event snapshot differs')
        reports={'common_initial':validator.check(initial,label='common_initial')}
        for method in ('baseline','improved'):
            condition=read(source/f'conditions_{method}.json')
            if condition['inputs_before']!=expected or condition['inputs_after']!=expected:raise ValueError('method common conditions differ')
            fragments=csv_tasks(source/f'interrupted_{method}.csv')
            for fragment in fragments:
                fragment.pop('target_id',None)
                for key in ('planned_end_s','planned_duration_s'):fragment[key]=int(fragment[key])
            if fragments!=bundle['interrupted']:raise ValueError('method interrupted history differs')
            report=validator.check(csv_tasks(source/f'schedule_{method}.csv'),fragments,bundle['event'],original_plan=initial,label=method)
            reports[method]=report;json_write(out/f'checks/{method}.json',report)
        after=tree_snapshot(source);passed=before==after and all(r['status']=='PASS' for r in reports.values())
        json_write(out/'recheck.json',dict(status='PASS' if passed else 'FAIL',source=str(source),source_tree_unchanged=before==after,
            source_file_count=sum(v['type']=='file' for v in before.values()),source_directory_count=sum(v['type']=='dir' for v in before.values()),
            before=before,after=after,reports=reports,common_conditions=expected))
        return 0 if passed else 2
    finally:clock.logfile.close()

"""Controlled E5 common-condition and history tests using synthetic tasks only."""
import copy
import pytest
from planner.experiment_inputs import json_hash
from planner.replan_comparison import fingerprints,paired_method,conditional_upper
from planner.scheduler import replay_state,future_candidates
from test_regressions import history_case,QuietClock,task,DAY


@pytest.fixture
def comparison(history_case):
    validator,initial,event,_,_=history_case
    completed,locked,interrupted,_=replay_state(initial,event,DAY)
    candidates=initial+[task(6,1,900)]
    bundle=dict(origin={'source':'synthetic','initial_file_sha256':'synthetic'},initial=initial,event=event,
                candidates=candidates,fixed=completed+locked,interrupted=interrupted,
                future=future_candidates(candidates,completed+locked,event))
    return validator,bundle,fingerprints(bundle)


def test_paired_methods_share_conditions_and_inputs_are_immutable(comparison):
    validator,bundle,expected=comparison;before=copy.deepcopy(bundle)
    for method in ('baseline','improved'):
        tasks,receipt=paired_method(bundle,method,expected,QuietClock())
        assert bundle==before and receipt['inputs_before']==receipt['inputs_after']==expected
        assert validator.check(tasks,bundle['interrupted'],bundle['event'],original_plan=bundle['initial'])['status']=='PASS'


@pytest.mark.parametrize('field',['origin','initial','fixed','interrupted','future','candidates','event'])
def test_mismatched_conditions_are_rejected_before_scheduling(comparison,monkeypatch,field):
    import planner.replan_comparison as module
    _,bundle,expected=comparison;altered=copy.deepcopy(bundle)
    if field=='origin':altered[field]['source']='different source'
    elif field=='event':altered[field]['end_s']+=1
    else:altered[field]=altered[field][1:]
    def must_not_run(*args,**kwargs):pytest.fail('scheduler ran despite common-condition mismatch')
    monkeypatch.setattr(module,'schedule',must_not_run)
    with pytest.raises(ValueError,match='contract mismatch'):paired_method(altered,'improved',expected,QuietClock())


def test_scheduler_input_mutation_is_detected(comparison,monkeypatch):
    import planner.replan_comparison as module
    _,bundle,expected=comparison;before=json_hash(bundle)
    def mutating(candidates,*args,**kwargs):
        candidates[0]['start_s']+=1;return []
    monkeypatch.setattr(module,'schedule',mutating)
    with pytest.raises(ValueError,match='contract mismatch'):paired_method(bundle,'improved',expected,QuietClock())
    assert json_hash(bundle)==before,'the shared original remains isolated from each method'


@pytest.mark.parametrize('attack',['delete_completed','delete_locked','delete_interrupted','forge_interrupted','backfill'])
def test_e5_histories_cannot_be_replaced_or_backfilled(comparison,attack):
    validator,bundle,expected=comparison
    tasks,_=paired_method(bundle,'baseline',expected,QuietClock());fragments=copy.deepcopy(bundle['interrupted'])
    if attack=='delete_completed':tasks=[r for r in tasks if r['status']!='completed']
    elif attack=='delete_locked':tasks=[r for r in tasks if r['status']!='locked']
    elif attack=='delete_interrupted':fragments=[]
    elif attack=='forge_interrupted':fragments.append(dict(fragments[0],task_id='SYN_FORGED'))
    else:
        # Target5/third station has a legal pre-fault window and no other occupation.
        tasks=[r for r in tasks if r['satnum']!=5]+[task(5,3,20,status='new_success')]
    report=validator.check(tasks,fragments,bundle['event'],original_plan=bundle['initial'])
    assert report['status']=='FAIL'
    assert any('history set' in v['reason'] for v in report['violations'])


def test_conditional_upper_excludes_fixed_targets_but_allows_interrupted_target():
    fixed=[task(1,1,0)]
    future=[task(1,2,600,duration=240),task(2,2,600),task(2,2,900,duration=240)]
    upper=conditional_upper(fixed,future,{1:5,2:3})
    assert upper['fixed_points_int']==15 and upper['future_points_int']==15
    assert upper['points_int']==30 and upper['task_score']==6

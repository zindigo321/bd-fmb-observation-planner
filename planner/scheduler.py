"""Inherited deterministic candidate generation and schedulers."""
from .common import *

def make_candidates(windows, records, config, day, out, clock):
    by_number = {r['satnum']:r for r in records}
    candidates = []
    prune = []
    raw_total = 0
    for window in windows:
        clock.check()
        for duration in config['durations_seconds']:
            last = window['end_s'] - duration
            if last < window['start_s']:
                prune.append(dict(window_id=window['window_id'], duration_s=duration, raw_count=0,
                                  retained_count=0, reason='window shorter than duration'))
                continue
            starts = list(range(window['start_s'], last+1, config['candidate_start_step_seconds']))
            if starts[-1] != last:
                starts.append(last)
            before = len(starts); raw_total += before
            if before > config['max_starts_per_window_duration']:
                positions = np.linspace(0, before-1, config['max_starts_per_window_duration']).round().astype(int)
                starts = [starts[i] for i in positions]
            prune.append(dict(window_id=window['window_id'], duration_s=duration, raw_count=before,
                              retained_count=len(starts), reason='evenly spaced grid indices; preserve first/last' if before > len(starts) else 'no pruning'))
            for start in starts:
                r = by_number[window['satnum']]
                end = start+duration
                points = r['full_score'] * (3 if duration == 120 else 5)
                cid = f'C{len(candidates)+1:06d}'
                candidates.append(dict(task_id=cid, candidate_id=cid, window_id=window['window_id'],
                                       satnum=r['satnum'], station_id=window['station_id'], priority=r['priority'],
                                       start_s=start, end_s=end, duration_s=duration, points_int=points,
                                       score=points/5, start_utc=utc_at(day,start), end_utc=utc_at(day,end), status='success'))
    csv_write(out / 'candidates.csv', candidates, TASK_FIELDS)
    json_write(out / 'candidate_pruning.json', dict(raw_grid_candidates=raw_total,
               retained_candidates=len(candidates), removed=raw_total-len(candidates), per_window_duration=prune,
               shared_for_all_methods=True, continuous_start_space_not_enumerated=True,
               start_grid_seconds=config['candidate_start_step_seconds'], cap=config['max_starts_per_window_duration']))
    return candidates


# ---------------- SCHEDULER MODULE: no checker code called for insertion ----------------
def planner_conflict(a, b):
    return a['station_id'] == b['station_id'] and not (
        a['start_s'] >= b['end_s'] + (30 if a['satnum'] != b['satnum'] else 0) or
        b['start_s'] >= a['end_s'] + (30 if a['satnum'] != b['satnum'] else 0))


def objective(rows):
    return sum(r['points_int'] for r in rows), len({r['satnum'] for r in rows})


def greedy(candidates, fixed, interrupted, clock):
    selected = [dict(r) for r in fixed]
    used = {r['satnum'] for r in fixed}
    occupancy = selected + list(interrupted)
    for index, c in enumerate(sorted(candidates, key=lambda x:(x['start_s'], -x['duration_s'], x['station_id'], x['satnum'], x['candidate_id']))):
        if index % 100 == 0:
            clock.check()
        if c['satnum'] in used or any(planner_conflict(c, p) for p in occupancy):
            continue
        r = dict(c)
        selected.append(r); occupancy.append(r); used.add(r['satnum'])
    return sorted(selected, key=lambda r:(r['start_s'],r['station_id'],r['satnum']))


def improved_construct(candidates, fixed, interrupted, clock):
    selected = [dict(r) for r in fixed]
    occupied = selected + list(interrupted)
    used = {r['satnum'] for r in fixed}
    groups = collections.defaultdict(list)
    for c in candidates:
        if c['satnum'] not in used:
            groups[c['satnum']].append(c)
    ordering = sorted(groups, key=lambda n:(-max(c['points_int'] for c in groups[n]),
                       len({c['window_id'] for c in groups[n]}), len(groups[n]), n))
    arrays = {}
    for station in sorted({c['station_id'] for c in candidates}):
        members = [c for c in candidates if c['station_id'] == station]
        arrays[station] = (np.array([c['start_s'] for c in members]), np.array([c['end_s'] for c in members]),
                           np.array([c['satnum'] for c in members]), np.array([c['points_int'] for c in members]))
    for target in ordering:
        clock.check()
        feasible = [c for c in groups[target] if not any(planner_conflict(c,p) for p in occupied)]
        if not feasible:
            used.add(target)  # no residual feasible choices; exclude from subsequent conflict loss
            continue
        best_points = max(c['points_int'] for c in feasible)
        best = None
        best_key = None
        for i, c in enumerate(feasible):
            if i % 50 == 0:
                clock.check()
            if c['points_int'] != best_points:
                continue
            starts, ends, ids, pts = arrays[c['station_id']]
            mask = (starts < c['end_s']+30) & (ends+30 > c['start_s']) & (ids != target)
            affected = {}
            for number, points in zip(ids[mask], pts[mask]):
                number = int(number)
                if number not in used:
                    affected[number] = max(affected.get(number,0), int(points))
            # Priority weighted loss with scarcity denominator, only a tie-break heuristic, NOT objective.
            loss = sum(p / max(1, len(groups[n])) for n,p in affected.items() if n in groups)
            key = (loss, len(affected), c['start_s'], c['station_id'], c['candidate_id'])
            if best_key is None or key < best_key:
                best, best_key = c, key
        r = dict(best)
        selected.append(r); occupied.append(r); used.add(target)
    return sorted(selected, key=lambda r:(r['start_s'],r['station_id'],r['satnum']))


def select_fault(schedule, day, horizon_seconds=86400, fault_seconds=7200):
    options = []
    for task in sorted(schedule, key=lambda r:(r['start_s'],r['station_id'],r['satnum'])):
        a = task['start_s'] + task['duration_s']//2
        b = min(horizon_seconds, a+fault_seconds)
        later = [r for r in schedule if r['station_id']==task['station_id'] and r['start_s'] > a and r['start_s'] < b]
        options.append((not bool(later), a, task['station_id'], b, task, later))
    if not options:
        return dict(effective=False, reason='empty improved schedule; no effective event')
    _, a, station, b, task, later = min(options, key=lambda x:(x[0],x[1],x[2]))
    return dict(effective=True, station_id=station, start_s=a, end_s=b, start_utc=utc_at(day,a), end_utc=utc_at(day,b),
                requested_duration_s=fault_seconds, actual_duration_s=b-a, truncated=b-a<fault_seconds,
                selection='interrupt current AND affect future' if later else 'interrupt current only; no future affected',
                selected_current_task=task['task_id'], affected_future_ids=[r['task_id'] for r in later],
                current_interruption=True, future_affected=bool(later))


def replay_state(schedule, event, day):
    a, sid = event['start_s'], event['station_id']
    completed, locked, interrupted, cancelled = [], [], [], []
    for task in schedule:
        r = dict(task)
        if r['end_s'] <= a:
            r['status']='completed'; completed.append(r)
        elif r['start_s'] < a < r['end_s']:
            if r['station_id'] != sid:
                r['status']='locked'; locked.append(r)
            else:
                r.update(status='interrupted', planned_end_s=r['end_s'], planned_duration_s=r['duration_s'],
                         planned_end_utc=r['end_utc'], end_s=a, duration_s=a-r['start_s'],
                         end_utc=utc_at(day,a), points_int=0, score=0.0)
                interrupted.append(r)
        else:
            cancelled.append(r)
    return completed, locked, interrupted, cancelled


def future_candidates(candidates, fixed, event):
    seen = {r['satnum'] for r in fixed}
    return [dict(c, status='new_success') for c in candidates if c['satnum'] not in seen and c['start_s'] >= event['start_s']
            and not (c['station_id']==event['station_id'] and c['start_s'] < event['end_s'] and c['end_s'] > event['start_s'])]


def schedule(candidates, method='baseline', *, fixed=(), interrupted=(), clock):
    """Return a new task list. Inputs are not mutated; fixed history is retained."""
    if method not in ('baseline', 'improved'):
        raise ValueError('method must be baseline or improved')
    baseline = greedy(candidates, fixed, interrupted, clock)
    if method == 'baseline':
        return baseline
    alternative = improved_construct(candidates, fixed, interrupted, clock)
    return alternative if objective(alternative) >= objective(baseline) else baseline

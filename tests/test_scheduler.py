from dayplanner.scheduler import Task, free_gaps, schedule


def h(hm):
    hh, mm = hm.split(":")
    return int(hh) * 60 + int(mm)


def task_blocks(result, task_id):
    return [(b.start, b.end) for b in result.blocks if b.task_id == task_id and b.kind == "task"]


LUNCH = (h("12:00"), h("13:00"))


def test_free_gaps_subtracts_breaks_and_meetings():
    gaps = free_gaps(h("09:00"), h("18:00"), [LUNCH, (h("14:00"), h("15:00"))])
    assert gaps == [[h("09:00"), h("12:00")], [h("13:00"), h("14:00")], [h("15:00"), h("18:00")]]


def test_free_gaps_ignores_blocks_outside_working_hours():
    gaps = free_gaps(h("09:00"), h("17:00"), [(h("07:00"), h("08:00")), (h("16:30"), h("19:00"))])
    assert gaps == [[h("09:00"), h("16:30")]]


def test_higher_priority_is_allocated_first():
    # Only 2h free; the P0 task must win even though it was entered last.
    r = schedule(h("09:00"), h("11:00"), [], [Task(1, 120, 3, 0), Task(2, 120, 0, 1)])
    assert task_blocks(r, 2) == [(h("09:00"), h("11:00"))]
    assert r.cannot_do == [1]


def test_short_task_fills_small_gap_long_task_gets_big_block():
    # 09:00-12:00 free, lunch, 13:00-13:30 free, meeting 13:30-18:00.
    blocked = [LUNCH, (h("13:30"), h("18:00"))]
    r = schedule(h("09:00"), h("18:00"), blocked, [Task(1, 30, 1, 0), Task(2, 180, 1, 1)])
    assert task_blocks(r, 2) == [(h("09:00"), h("12:00"))]
    assert task_blocks(r, 1) == [(h("13:00"), h("13:30"))]


def test_long_task_split_over_fewest_gaps():
    # Gaps: 1h, 2h, 30m, 3h. A 4.5h task needs the 3h and 2h gaps only.
    blocked = [(h("10:00"), h("11:00")), (h("13:00"), h("13:30")), (h("14:00"), h("15:00"))]
    r = schedule(h("09:00"), h("18:00"), blocked, [Task(1, 270, 0)])
    assert task_blocks(r, 1) == [(h("11:00"), h("13:00")), (h("15:00"), h("17:30"))]
    assert r.cannot_do == []


def test_task_that_does_not_fit_is_cannot_do():
    r = schedule(h("09:00"), h("10:00"), [], [Task(1, 30, 0), Task(2, 60, 1)])
    assert task_blocks(r, 1) == [(h("09:00"), h("09:30"))]
    assert r.cannot_do == [2]


def test_durations_round_up_to_slot():
    r = schedule(h("09:00"), h("12:00"), [], [Task(1, 20, 0)], slot=30)
    assert task_blocks(r, 1) == [(h("09:00"), h("09:30"))]


def test_rest_after_long_tasks_only():
    r = schedule(h("09:00"), h("12:00"), [], [Task(1, 60, 0, 0), Task(2, 30, 0, 1)],
                 slot=15, rest_minutes=15, rest_min_task=60)
    rests = [(b.task_id, b.start, b.end) for b in r.blocks if b.kind == "rest"]
    assert rests == [(1, h("10:00"), h("10:15"))]
    assert task_blocks(r, 2) == [(h("10:15"), h("10:45"))]


def test_rest_is_cut_short_by_next_fixed_block():
    r = schedule(h("11:00"), h("13:00"), [LUNCH], [Task(1, 60, 0)], slot=30, rest_minutes=30)
    assert task_blocks(r, 1) == [(h("11:00"), h("12:00"))]
    assert [b for b in r.blocks if b.kind == "rest"] == []


def test_nothing_scheduled_inside_meetings_or_breaks():
    blocked = [LUNCH, (h("14:00"), h("15:00"))]
    tasks = [Task(i, d, i % 4, i) for i, d in enumerate([90, 60, 45, 120, 30, 30, 60])]
    r = schedule(h("09:00"), h("18:00"), blocked, tasks, slot=15, rest_minutes=15)
    for b in r.blocks:
        for s, e in blocked:
            assert b.end <= s or b.start >= e
    spans = sorted((b.start, b.end) for b in r.blocks)
    for (s1, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2

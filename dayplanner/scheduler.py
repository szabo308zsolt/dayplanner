"""Pure scheduling engine (plan section 4). No Flask or database code here.

All times are minutes since midnight in the user's local time zone.
"""
from dataclasses import dataclass, field


@dataclass
class Task:
    id: int
    duration: int
    priority: int  # 0 = P0 (highest) .. 3 = P3
    order: int = 0  # tie-breaker: entry order


@dataclass
class Block:
    task_id: int
    start: int
    end: int
    kind: str = "task"  # "task" or "rest" (post-task break)


@dataclass
class Result:
    blocks: list = field(default_factory=list)
    cannot_do: list = field(default_factory=list)  # task ids that did not fit


def round_up(minutes, slot):
    return max(slot, -(-minutes // slot) * slot)


def free_gaps(work_start, work_end, blocked):
    """Working window minus blocked intervals, as sorted [start, end] lists."""
    gaps = []
    cursor = work_start
    for s, e in sorted((max(s, work_start), min(e, work_end)) for s, e in blocked):
        if e <= s:
            continue
        if s > cursor:
            gaps.append([cursor, s])
        cursor = max(cursor, e)
    if cursor < work_end:
        gaps.append([cursor, work_end])
    return gaps


def schedule(work_start, work_end, blocked, tasks, slot=30, rest_minutes=0, rest_min_task=0):
    """Place tasks into free time.

    Rules:
      1. Free time = working hours minus `blocked` (fixed breaks, meetings) and
         the post-task rest inserted as tasks are placed.
      2. Priorities are allocated in order: all P0, then P1, P2, P3.
      3. Within one priority, longest task first, each into the tightest gap
         it fits (best-fit decreasing): long tasks end up in big blocks, short
         ones fill the small gaps before lunch or a meeting.
      4. A task longer than every gap is split over the fewest gaps possible.
      5. Tasks that cannot fit at all are returned in `cannot_do`.

    Durations are rounded up to the slot size. A rest of `rest_minutes` follows
    a task whose duration is at least `rest_min_task`; it is shortened when the
    gap ends first (the next thing is a meeting, a fixed break or end of day).
    """
    gaps = free_gaps(work_start, work_end, blocked)
    result = Result()
    ordered = sorted(tasks, key=lambda t: (t.priority, -round_up(t.duration, slot), t.order))

    for task in ordered:
        need = round_up(task.duration, slot)
        rest = rest_minutes if rest_minutes and task.duration >= rest_min_task else 0

        fitting = [g for g in gaps if g[1] - g[0] >= need]
        if fitting:
            gap = min(fitting, key=lambda g: (g[1] - g[0], g[0]))
            segments = [(gap, need)]
        else:
            segments = _split(gaps, need)
            if segments is None:
                result.cannot_do.append(task.id)
                continue

        for i, (gap, length) in enumerate(segments):
            start = gap[0]
            end = start + length
            result.blocks.append(Block(task.id, start, end))
            gap[0] = end
            if i == len(segments) - 1 and rest:
                rest_end = min(end + round_up(rest, slot), gap[1])
                if rest_end > end:
                    result.blocks.append(Block(task.id, end, rest_end, "rest"))
                    gap[0] = rest_end
        gaps = [g for g in gaps if g[1] > g[0]]

    result.blocks.sort(key=lambda b: b.start)
    return result


def _split(gaps, need):
    """Fewest gaps whose total covers `need`, filled in time order.

    Returns [(gap, minutes)] or None when the day has too little free time.
    """
    by_size = sorted(gaps, key=lambda g: (-(g[1] - g[0]), g[0]))
    chosen, total = [], 0
    for g in by_size:
        chosen.append(g)
        total += g[1] - g[0]
        if total >= need:
            break
    else:
        return None
    segments, remaining = [], need
    for g in sorted(chosen, key=lambda g: g[0]):
        length = min(g[1] - g[0], remaining)
        segments.append((g, length))
        remaining -= length
    return segments

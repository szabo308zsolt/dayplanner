from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import scheduler
from .auth import onboarded_required
from .db import get_db
from .settings import load_settings, work_days_of
from .timeutil import (WEEKDAYS, hm_to_min, min_to_hm, minute_of_day, next_working_day,
                       parse_date, today_in)

bp = Blueprint("planner", __name__)

PRIORITIES = ["P0", "P1", "P2", "P3"]


# ---------- helpers ----------

def _settings():
    s, breaks = load_settings(g.user["id"])
    return s, breaks


def _day_or_404(day_str):
    try:
        return parse_date(day_str)
    except ValueError:
        abort(404)


def _day_row(day_str):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO days (user_id, date) VALUES (?, ?)", (g.user["id"], day_str))
    return db.execute("SELECT * FROM days WHERE user_id = ? AND date = ?",
                      (g.user["id"], day_str)).fetchone()


def _is_locked(day_str):
    return bool(_day_row(day_str)["locked_at"])


def _owned(table, row_id):
    row = get_db().execute(f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
                           (row_id, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    return row


def _back(day_str, anchor=None):
    return redirect(url_for("planner.day", day=day_str, _anchor=anchor))


def _require_draft(day_str):
    """Plan-shaping edits are only allowed until the plan is locked."""
    if _is_locked(day_str):
        flash("The plan for this day is locked. New tasks are recorded as unplanned work.", "error")
        return False
    return True


def _time_field(name):
    try:
        return hm_to_min(request.form.get(name, ""))
    except ValueError:
        return None


def _conflict(day_str, start, end, ignore_blocks=()):
    """Return a description of whatever [start, end) overlaps, or None."""
    s, breaks = _settings()
    if start < s["work_start"] or end > s["work_end"]:
        return f"outside working hours ({min_to_hm(s['work_start'])}–{min_to_hm(s['work_end'])})"
    for b in breaks:
        if start < b["end_min"] and b["start_min"] < end:
            return f"the break '{b['label']}'"
    db = get_db()
    for m in db.execute("SELECT * FROM meetings WHERE user_id = ? AND date = ?", (g.user["id"], day_str)):
        if start < m["end_min"] and m["start_min"] < end:
            return f"the meeting '{m['title']}'"
    rows = db.execute(
        """SELECT b.*, t.name FROM blocks b JOIN tasks t ON t.id = b.task_id
           WHERE b.user_id = ? AND b.date = ?""", (g.user["id"], day_str))
    for b in rows:
        if b["id"] in ignore_blocks:
            continue
        if start < b["end_min"] and b["start_min"] < end:
            return "a break after a task" if b["kind"] == "rest" else f"the task '{b['name']}'"
    return None


# ---------- pages ----------

@bp.route("/day")
@onboarded_required
def today():
    s, _ = _settings()
    return redirect(url_for("planner.day", day=today_in(s["timezone"]).isoformat()))


@bp.route("/day/<day>")
@onboarded_required
def day(day):
    the_day = _day_or_404(day)
    uid = g.user["id"]
    db = get_db()
    s, breaks = _settings()
    day_row = _day_row(day)
    db.commit()
    locked = bool(day_row["locked_at"])
    slot = s["slot_minutes"]

    tasks = db.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND date = ? ORDER BY priority, created_at, id",
        (uid, day)).fetchall()
    meetings = db.execute(
        "SELECT * FROM meetings WHERE user_id = ? AND date = ? ORDER BY start_min", (uid, day)).fetchall()
    blocks = db.execute(
        """SELECT b.*, t.name, t.priority, t.status FROM blocks b JOIN tasks t ON t.id = b.task_id
           WHERE b.user_id = ? AND b.date = ? ORDER BY b.start_min""", (uid, day)).fetchall()
    actuals = {a["slot_start"]: a for a in db.execute(
        "SELECT * FROM actuals WHERE user_id = ? AND date = ?", (uid, day))}

    # Number the parts of tasks split across several gaps.
    parts_total, part_no, parts_seen = {}, {}, {}
    for b in blocks:
        if b["kind"] == "task":
            parts_total[b["task_id"]] = parts_total.get(b["task_id"], 0) + 1
    for b in blocks:
        if b["kind"] == "task":
            parts_seen[b["task_id"]] = parts_seen.get(b["task_id"], 0) + 1
            part_no[b["id"]] = parts_seen[b["task_id"]]

    tz_today = today_in(s["timezone"])
    now_min = minute_of_day(s["timezone"]) if the_day == tz_today else None
    unplanned = [t for t in tasks if t["unplanned"]]

    slots = []
    for start in range(s["work_start"], s["work_end"], slot):
        end = min(start + slot, s["work_end"])
        plan = []
        for m in meetings:
            if start < m["end_min"] and m["start_min"] < end:
                plan.append({"kind": "meeting", "label": m["title"]})
        for b in breaks:
            if start < b["end_min"] and b["start_min"] < end:
                plan.append({"kind": "break", "label": b["label"]})
        for b in blocks:
            if start < b["end_min"] and b["start_min"] < end:
                if b["kind"] == "rest":
                    plan.append({"kind": "rest", "label": "Break"})
                else:
                    label = b["name"]
                    if parts_total[b["task_id"]] > 1:
                        label += f" (part {part_no[b['id']]}/{parts_total[b['task_id']]})"
                    plan.append({"kind": "task", "label": label, "priority": b["priority"],
                                 "dropped": b["status"] in ("cannot_do", "moved")})
        extra = [t for t in unplanned if t["start_min"] is not None
                 and start < t["start_min"] + t["duration"] and t["start_min"] < end]
        if the_day < tz_today:
            when = "past"
        elif the_day > tz_today or now_min is None:
            when = "future"
        else:
            when = "past" if end <= now_min else ("now" if start <= now_min else "future")
        slots.append({"start": start, "end": end, "plan": plan, "actual": actuals.get(start),
                      "unplanned": extra, "when": when})

    planned_slots = [x for x in slots if any(p["kind"] == "task" for p in x["plan"])]
    stats = {
        "planned": len(planned_slots),
        "as_planned": sum(1 for x in planned_slots if x["actual"] and x["actual"]["kind"] == "as_planned"),
        "reviewed": sum(1 for x in slots if x["actual"]),
        "unplanned_min": sum(t["duration"] for t in unplanned),
    }

    default_start = s["work_start"]
    if now_min is not None:
        default_start = max(s["work_start"], min(now_min - now_min % slot, s["work_end"] - slot))

    return render_template(
        "day.html", day=day, the_day=the_day, weekday=WEEKDAYS[the_day.weekday()],
        is_working_day=the_day.weekday() in work_days_of(s), is_today=the_day == tz_today,
        prev_day=date.fromordinal(the_day.toordinal() - 1).isoformat(),
        next_day=date.fromordinal(the_day.toordinal() + 1).isoformat(),
        s=s, slot=slot, locked=locked, locked_at=day_row["locked_at"], tasks=tasks, meetings=meetings,
        blocks=blocks, part_no=part_no, parts_total=parts_total, slots=slots, stats=stats,
        priorities=PRIORITIES, now_min=now_min, default_start=default_start,
        review_prompt=s["review_prompt"],
        unreviewed_past=[x["start"] for x in slots if x["when"] == "past" and not x["actual"]])


# ---------- tasks ----------

@bp.route("/day/<day>/tasks", methods=("POST",))
@onboarded_required
def add_task(day):
    _day_or_404(day)
    s, _ = _settings()
    name = request.form.get("name", "").strip()[:200]
    try:
        duration = int(request.form.get("duration", ""))
        priority = int(request.form.get("priority", "1"))
    except ValueError:
        duration, priority = 0, 1
    if not name or duration <= 0 or duration > 24 * 60 or priority not in range(4):
        flash("A task needs a name, a duration in minutes and a priority.", "error")
        return _back(day, "tasks")

    db = get_db()
    if _is_locked(day):
        start = _time_field("start")
        if start is None:
            flash("Unplanned work needs a start time.", "error")
            return _back(day, "tasks")
        db.execute("""INSERT INTO tasks (user_id, date, name, duration, priority, unplanned, start_min)
                      VALUES (?, ?, ?, ?, ?, 1, ?)""", (g.user["id"], day, name, duration, priority, start))
        flash(f"'{name}' recorded as unplanned work. Your plan is unchanged.", "info")
    else:
        db.execute("INSERT INTO tasks (user_id, date, name, duration, priority) VALUES (?, ?, ?, ?, ?)",
                   (g.user["id"], day, name, duration, priority))
    db.commit()
    return _back(day, "tasks")


@bp.route("/tasks/<int:task_id>/delete", methods=("POST",))
@onboarded_required
def delete_task(task_id):
    t = _owned("tasks", task_id)
    if not t["unplanned"] and not _require_draft(t["date"]):
        return _back(t["date"], "tasks")
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return _back(t["date"], "tasks")


@bp.route("/tasks/<int:task_id>/cannot", methods=("POST",))
@onboarded_required
def mark_cannot(task_id):
    t = _owned("tasks", task_id)
    db = get_db()
    db.execute("UPDATE tasks SET status = 'cannot_do', cannot_reason = 'manual' WHERE id = ?", (task_id,))
    # Before locking the slots go back to free time; after locking the plan
    # keeps them (shown struck through) so plan vs actual stays honest.
    if not _is_locked(t["date"]):
        db.execute("DELETE FROM blocks WHERE task_id = ?", (task_id,))
    db.commit()
    return _back(t["date"], "tasks")


@bp.route("/tasks/<int:task_id>/restore", methods=("POST",))
@onboarded_required
def restore_task(task_id):
    t = _owned("tasks", task_id)
    if not _require_draft(t["date"]):
        return _back(t["date"], "tasks")
    db = get_db()
    db.execute("UPDATE tasks SET status = 'pending', cannot_reason = NULL WHERE id = ?", (task_id,))
    db.commit()
    return _back(t["date"], "tasks")


@bp.route("/tasks/<int:task_id>/move", methods=("POST",))
@onboarded_required
def move_task(task_id):
    t = _owned("tasks", task_id)
    if t["status"] != "cannot_do":
        flash("Only tasks marked Cannot do can be moved to the next day.", "error")
        return _back(t["date"], "tasks")
    s, _ = _settings()
    target = next_working_day(parse_date(t["date"]), work_days_of(s)).isoformat()
    db = get_db()
    db.execute("INSERT INTO tasks (user_id, date, name, duration, priority) VALUES (?, ?, ?, ?, ?)",
               (g.user["id"], target, t["name"], t["duration"], t["priority"]))
    db.execute("UPDATE tasks SET status = 'moved', moved_to = ? WHERE id = ?", (target, task_id))
    if not _is_locked(t["date"]):
        db.execute("DELETE FROM blocks WHERE task_id = ?", (task_id,))
    db.commit()
    flash(f"'{t['name']}' moved to {target}.", "info")
    return _back(t["date"], "tasks")


@bp.route("/tasks/<int:task_id>/place", methods=("POST",))
@onboarded_required
def place_task(task_id):
    """Manually put an unscheduled or Cannot-do task into the plan."""
    t = _owned("tasks", task_id)
    if not _require_draft(t["date"]):
        return _back(t["date"], "schedule")
    s, _ = _settings()
    start = _time_field("start")
    if start is None:
        flash("Pick a start time.", "error")
        return _back(t["date"], "schedule")
    end = start + scheduler.round_up(t["duration"], s["slot_minutes"])
    clash = _conflict(t["date"], start, end)
    if clash:
        flash(f"Can't place '{t['name']}' at {min_to_hm(start)}: it overlaps {clash}.", "error")
        return _back(t["date"], "schedule")
    db = get_db()
    db.execute("INSERT INTO blocks (user_id, date, task_id, start_min, end_min) VALUES (?, ?, ?, ?, ?)",
               (g.user["id"], t["date"], task_id, start, end))
    db.execute("UPDATE tasks SET status = 'scheduled', cannot_reason = NULL WHERE id = ?", (task_id,))
    db.commit()
    return _back(t["date"], "schedule")


# ---------- meetings ----------

@bp.route("/day/<day>/meetings", methods=("POST",))
@onboarded_required
def add_meeting(day):
    _day_or_404(day)
    if not _require_draft(day):
        return _back(day, "meetings")
    title = request.form.get("title", "").strip()[:200] or "Meeting"
    start, end = _time_field("start"), _time_field("end")
    if start is None or end is None or end <= start:
        flash("A meeting needs a start and an end time.", "error")
        return _back(day, "meetings")
    db = get_db()
    db.execute("INSERT INTO meetings (user_id, date, title, start_min, end_min) VALUES (?, ?, ?, ?, ?)",
               (g.user["id"], day, title, start, end))
    db.commit()
    return _back(day, "meetings")


@bp.route("/meetings/<int:meeting_id>/delete", methods=("POST",))
@onboarded_required
def delete_meeting(meeting_id):
    m = _owned("meetings", meeting_id)
    if not _require_draft(m["date"]):
        return _back(m["date"], "meetings")
    db = get_db()
    db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    db.commit()
    return _back(m["date"], "meetings")


# ---------- schedule ----------

@bp.route("/day/<day>/generate", methods=("POST",))
@onboarded_required
def generate(day):
    _day_or_404(day)
    if not _require_draft(day):
        return _back(day, "schedule")
    uid = g.user["id"]
    db = get_db()
    s, breaks = _settings()
    meetings = db.execute("SELECT start_min, end_min FROM meetings WHERE user_id = ? AND date = ?",
                          (uid, day)).fetchall()
    # Tasks the user marked Cannot do themselves, or moved away, stay out.
    rows = db.execute(
        """SELECT * FROM tasks WHERE user_id = ? AND date = ? AND unplanned = 0
           AND status != 'moved' AND NOT (status = 'cannot_do' AND cannot_reason = 'manual')
           ORDER BY created_at, id""", (uid, day)).fetchall()
    blocked = [(b["start_min"], b["end_min"]) for b in breaks] + \
              [(m["start_min"], m["end_min"]) for m in meetings]
    result = scheduler.schedule(
        s["work_start"], s["work_end"], blocked,
        [scheduler.Task(r["id"], r["duration"], r["priority"], i) for i, r in enumerate(rows)],
        slot=s["slot_minutes"], rest_minutes=s["rest_minutes"], rest_min_task=s["rest_min_task"])

    db.execute("DELETE FROM blocks WHERE user_id = ? AND date = ?", (uid, day))
    db.executemany(
        "INSERT INTO blocks (user_id, date, task_id, kind, start_min, end_min) VALUES (?, ?, ?, ?, ?, ?)",
        [(uid, day, b.task_id, b.kind, b.start, b.end) for b in result.blocks])
    for r in rows:
        if r["id"] in result.cannot_do:
            db.execute("UPDATE tasks SET status = 'cannot_do', cannot_reason = 'auto' WHERE id = ?", (r["id"],))
        else:
            db.execute("UPDATE tasks SET status = 'scheduled', cannot_reason = NULL WHERE id = ?", (r["id"],))
    db.commit()
    if result.cannot_do:
        flash(f"{len(result.cannot_do)} task(s) didn't fit and are marked Cannot do. "
              "Drop them or move them to the next day.", "error")
    else:
        flash("Schedule generated. Adjust it if you like, then lock the plan.", "info")
    return _back(day, "schedule")


@bp.route("/day/<day>/lock", methods=("POST",))
@onboarded_required
def lock(day):
    _day_or_404(day)
    if not _require_draft(day):
        return _back(day)
    s, _ = _settings()
    db = get_db()
    _day_row(day)
    stamp = f"{today_in(s['timezone']).isoformat()} {min_to_hm(minute_of_day(s['timezone']))}"
    db.execute("UPDATE days SET locked_at = ? WHERE user_id = ? AND date = ?", (stamp, g.user["id"], day))
    db.commit()
    flash("Plan locked. Anything you add from now on is recorded as unplanned work.", "info")
    return _back(day, "review")


@bp.route("/blocks/<int:block_id>/edit", methods=("POST",))
@onboarded_required
def edit_block(block_id):
    b = _owned("blocks", block_id)
    if not _require_draft(b["date"]):
        return _back(b["date"], "schedule")
    start, end = _time_field("start"), _time_field("end")
    if start is None or end is None or end <= start:
        flash("A block needs a start time before its end time.", "error")
        return _back(b["date"], "schedule")
    clash = _conflict(b["date"], start, end, ignore_blocks={block_id})
    if clash:
        flash(f"Can't move it to {min_to_hm(start)}–{min_to_hm(end)}: it overlaps {clash}.", "error")
        return _back(b["date"], "schedule")
    db = get_db()
    db.execute("UPDATE blocks SET start_min = ?, end_min = ? WHERE id = ?", (start, end, block_id))
    db.commit()
    return _back(b["date"], "schedule")


@bp.route("/blocks/<int:block_id>/swap/<direction>", methods=("POST",))
@onboarded_required
def swap_block(block_id, direction):
    """Reorder: swap a task block with the previous or next task block."""
    b = _owned("blocks", block_id)
    if not _require_draft(b["date"]):
        return _back(b["date"], "schedule")
    db = get_db()
    if direction == "up":
        other = db.execute("""SELECT * FROM blocks WHERE user_id = ? AND date = ? AND kind = 'task'
                              AND start_min < ? ORDER BY start_min DESC LIMIT 1""",
                           (g.user["id"], b["date"], b["start_min"])).fetchone()
        first, second = other, b
    else:
        other = db.execute("""SELECT * FROM blocks WHERE user_id = ? AND date = ? AND kind = 'task'
                              AND start_min > ? ORDER BY start_min LIMIT 1""",
                           (g.user["id"], b["date"], b["start_min"])).fetchone()
        first, second = b, other
    if other is None:
        return _back(b["date"], "schedule")
    # The later block moves to where the earlier one started; the earlier one
    # moves to end where the later one ended.
    len1 = first["end_min"] - first["start_min"]
    len2 = second["end_min"] - second["start_min"]
    new_second = (first["start_min"], first["start_min"] + len2)
    new_first = (second["end_min"] - len1, second["end_min"])
    # A break that directly follows either block travels with it.
    rests = {}
    for blk in (first, second):
        rest = db.execute("""SELECT * FROM blocks WHERE user_id = ? AND task_id = ? AND kind = 'rest'
                             AND start_min = ?""", (g.user["id"], blk["task_id"], blk["end_min"])).fetchone()
        if rest:
            rests[blk["id"]] = rest
    ignore = {first["id"], second["id"]} | {r["id"] for r in rests.values()}
    clash = (_conflict(b["date"], *new_second, ignore_blocks=ignore)
             or _conflict(b["date"], *new_first, ignore_blocks=ignore))
    if not clash and new_second[1] > new_first[0]:
        clash = "each other"
    if clash:
        flash(f"Can't swap these two: the result would overlap {clash}. Edit the times instead.", "error")
        return _back(b["date"], "schedule")
    db.execute("UPDATE blocks SET start_min = ?, end_min = ? WHERE id = ?", (*new_second, second["id"]))
    db.execute("UPDATE blocks SET start_min = ?, end_min = ? WHERE id = ?", (*new_first, first["id"]))
    for blk_id, rest in rests.items():
        db.execute("DELETE FROM blocks WHERE id = ?", (rest["id"],))
    for blk_id, rest in rests.items():
        end = new_second[1] if blk_id == second["id"] else new_first[1]
        length = rest["end_min"] - rest["start_min"]
        # Keep as much of the break as fits before the next fixed thing.
        while length > 0 and _conflict(b["date"], end, end + length):
            length -= 5
        if length > 0:
            db.execute("""INSERT INTO blocks (user_id, date, task_id, kind, start_min, end_min)
                          VALUES (?, ?, ?, 'rest', ?, ?)""", (g.user["id"], b["date"], rest["task_id"], end, end + length))
    db.commit()
    return _back(b["date"], "schedule")


@bp.route("/blocks/<int:block_id>/delete", methods=("POST",))
@onboarded_required
def delete_block(block_id):
    b = _owned("blocks", block_id)
    if not _require_draft(b["date"]):
        return _back(b["date"], "schedule")
    db = get_db()
    db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
    if b["kind"] == "task":
        left = db.execute("SELECT COUNT(*) FROM blocks WHERE task_id = ? AND kind = 'task'",
                          (b["task_id"],)).fetchone()[0]
        if not left:
            db.execute("DELETE FROM blocks WHERE task_id = ?", (b["task_id"],))
            db.execute("UPDATE tasks SET status = 'pending' WHERE id = ?", (b["task_id"],))
    db.commit()
    return _back(b["date"], "schedule")


# ---------- plan vs actual ----------

@bp.route("/day/<day>/actual", methods=("POST",))
@onboarded_required
def record_actual(day):
    _day_or_404(day)
    try:
        slot_start = int(request.form["slot_start"])
    except (KeyError, ValueError):
        abort(400)
    kind = request.form.get("kind")
    note = request.form.get("note", "").strip()[:500]
    db = get_db()
    if kind == "clear":
        db.execute("DELETE FROM actuals WHERE user_id = ? AND date = ? AND slot_start = ?",
                   (g.user["id"], day, slot_start))
    elif kind == "as_planned" or (kind == "other" and note):
        db.execute("""INSERT INTO actuals (user_id, date, slot_start, kind, note) VALUES (?, ?, ?, ?, ?)
                      ON CONFLICT (user_id, date, slot_start) DO UPDATE SET kind = excluded.kind,
                      note = excluded.note""",
                   (g.user["id"], day, slot_start, kind, note if kind == "other" else None))
    else:
        flash("Write what you actually did, or choose Done as planned.", "error")
    db.commit()
    return _back(day, f"slot-{slot_start}")

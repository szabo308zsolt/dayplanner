from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .timeutil import WEEKDAYS, hm_to_min, timezone_names, valid_timezone

bp = Blueprint("settings", __name__)

SLOT_CHOICES = (15, 30, 60)
REST_CHOICES = (0, 5, 10, 15, 30)
REVIEW_CHOICES = {
    "slot": "After every slot",
    "eod": "At the end of the day",
    "off": "Off (I'll fill it in myself)",
}


def load_settings(user_id):
    db = get_db()
    s = db.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    breaks = db.execute("SELECT * FROM fixed_breaks WHERE user_id = ? ORDER BY start_min",
                        (user_id,)).fetchall()
    return s, breaks


def work_days_of(s):
    return {int(d) for d in s["work_days"].split(",") if d != ""}


@bp.route("/welcome", methods=("GET", "POST"))
@login_required
def onboarding():
    return _settings_page(onboarding=True)


@bp.route("/settings", methods=("GET", "POST"))
@login_required
def edit():
    return _settings_page(onboarding=False)


def _settings_page(onboarding):
    uid = g.user["id"]
    s, breaks = load_settings(uid)
    if request.method == "POST":
        data, new_breaks, errors = _parse(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db = get_db()
            db.execute(
                """UPDATE settings SET work_start=?, work_end=?, work_days=?, timezone=?,
                   slot_minutes=?, rest_minutes=?, rest_min_task=?, review_prompt=?, onboarded=1
                   WHERE user_id=?""",
                (data["work_start"], data["work_end"], data["work_days"], data["timezone"],
                 data["slot_minutes"], data["rest_minutes"], data["rest_min_task"],
                 data["review_prompt"], uid))
            db.execute("DELETE FROM fixed_breaks WHERE user_id = ?", (uid,))
            db.executemany("INSERT INTO fixed_breaks (user_id, label, start_min, end_min) VALUES (?,?,?,?)",
                           [(uid, *b) for b in new_breaks])
            db.commit()
            if onboarding:
                flash("All set. Add today's tasks and meetings, then generate your plan.", "info")
            else:
                flash("Settings saved.", "info")
            return redirect(url_for("planner.today"))
    return render_template(
        "settings.html", s=s, breaks=breaks, onboarding=onboarding, weekdays=WEEKDAYS,
        work_days=work_days_of(s), slot_choices=SLOT_CHOICES, rest_choices=REST_CHOICES,
        review_choices=REVIEW_CHOICES, timezones=timezone_names())


def _parse(form):
    errors = []
    data = {}
    try:
        data["work_start"] = hm_to_min(form["work_start"])
        data["work_end"] = hm_to_min(form["work_end"])
        if data["work_end"] <= data["work_start"]:
            errors.append("Working hours must end after they start.")
    except (KeyError, ValueError):
        errors.append("Enter working hours as start and end times.")

    days = sorted({int(d) for d in form.getlist("work_days") if d.isdigit() and int(d) < 7})
    if not days:
        errors.append("Pick at least one working day.")
    data["work_days"] = ",".join(map(str, days))

    tz = form.get("timezone", "").strip()
    if not valid_timezone(tz):
        errors.append("Pick a valid time zone.")
    data["timezone"] = tz

    data["slot_minutes"] = _choice(form.get("slot_minutes"), SLOT_CHOICES, 30)
    data["rest_minutes"] = _choice(form.get("rest_minutes"), REST_CHOICES, 0)
    data["rest_min_task"] = 0
    if form.get("rest_long_only"):
        try:
            data["rest_min_task"] = max(0, int(form.get("rest_min_task") or 0))
        except ValueError:
            errors.append("Enter the minimum task length for breaks in minutes.")
    review = form.get("review_prompt")
    data["review_prompt"] = review if review in REVIEW_CHOICES else "eod"

    new_breaks = []
    for label, start, end in zip(form.getlist("break_label"), form.getlist("break_start"),
                                 form.getlist("break_end")):
        if not (start or end):
            continue
        try:
            s, e = hm_to_min(start), hm_to_min(end)
        except ValueError:
            errors.append("Each break needs a start and end time.")
            continue
        if e <= s:
            errors.append(f"Break '{label or 'Break'}' must end after it starts.")
            continue
        new_breaks.append(((label or "Break").strip()[:60], s, e))
    return data, new_breaks, errors


def _choice(value, choices, default):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v if v in choices else default

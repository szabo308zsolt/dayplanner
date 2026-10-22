import re

import pytest

from dayplanner import create_app
from dayplanner.db import get_db

DAY = "2026-10-21"  # a Wednesday


@pytest.fixture
def app(tmp_path):
    return create_app({"DATABASE": str(tmp_path / "test.sqlite"), "SECRET_KEY": "test"})


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def post(client, path, data=None, page="/login"):
    data = dict(data or {})
    data["csrf_token"] = csrf(client, page)
    return client.post(path, data=data)


def signup_and_onboard(client, **overrides):
    post(client, "/signup", {"email": "a@example.com", "password": "secret123"}, page="/signup")
    form = {
        "work_start": "09:00", "work_end": "13:00", "work_days": ["0", "1", "2", "3", "4"],
        "timezone": "Europe/Budapest", "slot_minutes": "30", "rest_minutes": "0",
        "review_prompt": "eod", "break_label": ["Lunch"], "break_start": ["12:00"], "break_end": ["12:30"],
    }
    form.update(overrides)
    return post(client, "/welcome", form, page="/welcome")


def query(app, sql, *args):
    with app.app_context():
        return get_db().execute(sql, args).fetchall()


def test_csrf_is_required(client):
    assert client.post("/login", data={"email": "x", "password": "y"}).status_code == 400


def test_signup_goes_to_onboarding_then_planner(client):
    r = post(client, "/signup", {"email": "a@example.com", "password": "secret123"}, page="/signup")
    assert r.headers["Location"].endswith("/welcome")
    assert client.get(f"/day/{DAY}").headers["Location"].endswith("/welcome")
    r = post(client, "/welcome", {
        "work_start": "09:00", "work_end": "17:00", "work_days": ["0"], "timezone": "UTC",
        "slot_minutes": "15", "review_prompt": "off"}, page="/welcome")
    assert r.status_code == 302
    assert client.get(f"/day/{DAY}").status_code == 200


def test_login_logout_and_password_reset(client, capsys):
    signup_and_onboard(client)
    post(client, "/logout", page=f"/day/{DAY}")
    assert client.get(f"/day/{DAY}").status_code == 302

    r = post(client, "/login", {"email": "a@example.com", "password": "wrong"})
    assert "Incorrect" in r.get_data(as_text=True)

    post(client, "/forgot", {"email": "a@example.com"}, page="/forgot")
    link = re.search(r"(/reset/\S+)", capsys.readouterr().out).group(1)
    post(client, link, {"password": "newpass123"}, page=link)
    r = post(client, "/login", {"email": "a@example.com", "password": "newpass123"})
    assert r.status_code == 302
    # A used token no longer works.
    assert client.get(link).status_code == 302


def test_plan_lock_unplanned_and_review(app, client):
    signup_and_onboard(client)
    page = f"/day/{DAY}"
    post(client, f"{page}/meetings", {"title": "Standup", "start": "09:00", "end": "09:30"}, page=page)
    post(client, f"{page}/tasks", {"name": "Write report", "duration": "120", "priority": "0"}, page=page)
    post(client, f"{page}/tasks", {"name": "Email", "duration": "30", "priority": "2"}, page=page)
    post(client, f"{page}/tasks", {"name": "Big refactor", "duration": "120", "priority": "3"}, page=page)
    post(client, f"{page}/generate", page=page)

    tasks = {r["name"]: r for r in query(app, "SELECT * FROM tasks")}
    assert tasks["Write report"]["status"] == "scheduled"
    assert tasks["Email"]["status"] == "scheduled"
    assert tasks["Big refactor"]["status"] == "cannot_do"  # only 3h free, P3 loses
    blocks = query(app, "SELECT start_min, end_min FROM blocks WHERE task_id = ?", tasks["Write report"]["id"])
    assert [(b[0], b[1]) for b in blocks] == [(570, 690)]  # 09:30-11:30, the big gap

    # Move the Cannot-do task to Thursday.
    post(client, f"/tasks/{tasks['Big refactor']['id']}/move", page=page)
    moved = query(app, "SELECT date, status FROM tasks WHERE name = 'Big refactor' ORDER BY id")
    assert [tuple(r) for r in moved] == [(DAY, "moved"), ("2026-10-22", "pending")]

    post(client, f"{page}/lock", page=page)
    # After locking, regenerate is refused and new tasks are unplanned.
    post(client, f"{page}/generate", page=page)
    post(client, f"{page}/tasks", {"name": "Fire drill", "duration": "30", "priority": "0", "start": "11:30"}, page=page)
    drill = query(app, "SELECT unplanned, start_min FROM tasks WHERE name = 'Fire drill'")[0]
    assert tuple(drill) == (1, 690)
    assert len(query(app, "SELECT * FROM blocks")) == 2

    post(client, f"{page}/actual", {"slot_start": "570", "kind": "as_planned"}, page=page)
    post(client, f"{page}/actual", {"slot_start": "600", "kind": "other", "note": "Phone call"}, page=page)
    html = client.get(page).get_data(as_text=True)
    assert "Done as planned" in html and "Phone call" in html and "Fire drill" in html
    assert "<strong>1/5</strong> planned slots" in html


def test_manual_edit_rejects_overlaps(app, client):
    signup_and_onboard(client)
    page = f"/day/{DAY}"
    post(client, f"{page}/tasks", {"name": "A", "duration": "60", "priority": "0"}, page=page)
    post(client, f"{page}/generate", page=page)
    block = query(app, "SELECT id FROM blocks")[0]["id"]
    post(client, f"/blocks/{block}/edit", {"start": "11:30", "end": "12:30"}, page=page)
    assert "overlaps the break" in client.get(page).get_data(as_text=True)
    assert tuple(query(app, "SELECT start_min, end_min FROM blocks")[0]) == (540, 600)
    post(client, f"/blocks/{block}/edit", {"start": "10:00", "end": "11:30"}, page=page)
    assert tuple(query(app, "SELECT start_min, end_min FROM blocks")[0]) == (600, 690)


def test_users_cannot_touch_each_others_tasks(app, client):
    signup_and_onboard(client)
    page = f"/day/{DAY}"
    post(client, f"{page}/tasks", {"name": "Mine", "duration": "30", "priority": "0"}, page=page)
    task_id = query(app, "SELECT id FROM tasks")[0]["id"]
    post(client, "/logout", page=page)
    post(client, "/signup", {"email": "b@example.com", "password": "secret123"}, page="/signup")
    assert post(client, f"/tasks/{task_id}/delete", page="/welcome").status_code == 302  # onboarding first
    signup_form = {"work_start": "09:00", "work_end": "17:00", "work_days": ["2"], "timezone": "UTC",
                   "slot_minutes": "30", "review_prompt": "off"}
    post(client, "/welcome", signup_form, page="/welcome")
    assert post(client, f"/tasks/{task_id}/delete", page=page).status_code == 404
    assert len(query(app, "SELECT id FROM tasks")) == 1


def test_swap_moves_rest_with_its_task(app, client):
    signup_and_onboard(client, work_end="18:00", break_label=[], break_start=[], break_end=[],
                       rest_minutes="30")
    page = f"/day/{DAY}"
    post(client, f"{page}/tasks", {"name": "Long", "duration": "90", "priority": "0"}, page=page)
    post(client, f"{page}/tasks", {"name": "Short", "duration": "30", "priority": "1"}, page=page)
    post(client, f"{page}/generate", page=page)
    rows = lambda: [(r["name"], r["kind"], r["start_min"], r["end_min"]) for r in query(
        app, "SELECT t.name, b.kind, b.start_min, b.end_min FROM blocks b JOIN tasks t ON t.id = b.task_id "
             "ORDER BY b.start_min")]
    assert rows() == [("Long", "task", 540, 630), ("Long", "rest", 630, 660),
                      ("Short", "task", 660, 690), ("Short", "rest", 690, 720)]
    long_id = query(app, "SELECT id FROM blocks WHERE kind = 'task' ORDER BY start_min")[0]["id"]
    post(client, f"/blocks/{long_id}/swap/down", page=page)
    assert rows() == [("Short", "task", 540, 570), ("Short", "rest", 570, 600),
                      ("Long", "task", 600, 690), ("Long", "rest", 690, 720)]

# Day Planner

A minimalist day planner, built from [Day Planner Website - Initial Plan.md](Day%20Planner%20Website%20-%20Initial%20Plan.md).
Set up your working day once. Each morning, list your tasks with durations and priorities, and the app
fits them into your free time. Then compare the plan with what you actually did.

**Stack:** Python 3 + Flask, SQLite, server-rendered HTML with a little plain JavaScript. There is no build step.

## Run it

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/flask --app dayplanner run --port 5050
```

Then open http://localhost:5050. The database (`instance/dayplanner.sqlite`) and a secret key are
created automatically on first start.

Run the tests:

```bash
.venv/bin/python -m pytest -q
```

## What's in v1 (maps to the plan)

| Plan section | Where |
|---|---|
| 1. Accounts: sign up, log in/out, password reset | `dayplanner/auth.py` |
| 2. Onboarding: hours, days, time zone, slot size, fixed breaks, break after tasks, review prompt | `dayplanner/settings.py`, `/welcome`, later `/settings` |
| 3. Daily planning: tasks, meetings, generate, manual edits, Cannot do, move to next day, mid-day additions | `dayplanner/planner.py`, `/day/<date>` |
| 4. Scheduling rules | `dayplanner/scheduler.py` (pure functions, unit-tested) |
| 5. Plan vs actual | the "Plan vs actual" table on the day page, plus `static/day.js` for prompts |

### How the day works

1. **Draft:** add tasks and meetings, then press **Generate schedule**. You can edit the result:
   change start/end times (move or resize), use ↑ ↓ to swap the order of tasks (a task's break moves
   with it), remove blocks, or place a Cannot-do task yourself. Pressing **Regenerate** discards your edits.
2. **Lock plan:** this fixes the plan for comparison. From then on, new tasks are recorded as
   *unplanned work* at a start time you choose. They appear only in the Actual column, and the plan stays as it was.
3. **Review:** for each slot, choose **✓ As planned** or type what you did instead and press Enter.
   Depending on your setting, a banner asks after every slot or once your working day is over.

### Scheduling details

- Free time = working hours − fixed breaks − meetings − breaks after tasks.
- Priorities are allocated in order (all P0, then P1, …). Within a priority, the longest task goes first,
  each into the *tightest* gap it fits (best-fit). Long tasks land in big blocks and short ones fill the
  small gaps before lunch or a meeting.
- A task longer than every gap is split over the fewest gaps possible and shown as "part 1/2" and so on.
- Tasks that don't fit are flagged **Cannot do**. Nothing rolls over automatically: **Move to next day**
  copies the task to your next working day.
- Durations are rounded up to the slot size. A break after a task is cut short when a meeting, fixed
  break or the end of the day comes first.

## Production notes

- Set `SECRET_KEY` in the environment, and run behind a real WSGI server (for example `gunicorn "dayplanner:create_app()"`) with HTTPS.
- Password-reset emails go out over SMTP when `SMTP_HOST` is set (also `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASSWORD`, `MAIL_FROM`). Without SMTP, the reset link is printed to the server console, which is meant for development.
- Not built yet: login rate limiting, email verification, account deletion.

## Development

A local test account was created while building: `demo@example.test` / `plannerdemo2026`. It only
exists in your local `instance/` database. Delete that folder to start fresh.

Out of scope for v1 (from the plan): history and trends, calendar import.

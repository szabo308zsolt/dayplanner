# Day Planner Website – Initial Plan

Oct 21, 2026 · @Zsolt

## Overview

A minimalist website for a general audience. Users set up their working day once, then each morning list their tasks with durations and priorities. The app auto-schedules tasks into free time slots, and users can review plan versus actual to see what they achieved.

## 1. Accounts

- Sign up, log in, log out, password reset.
- Each user has their own settings, tasks, and history.

## 2. Onboarding

1. **Working hours** – start and end time (e.g. 09:00–18:00) and working days. Time zone captured.
2. **Slot size** – planning granularity: 15, 30 or 60 minutes.
3. **Fixed breaks** – recurring blocked time such as lunch.
4. **Break after tasks** – configurable rest after finishing a task (e.g. 15 or 30 min), optionally only after longer tasks.
5. **Review prompt preference** – after every slot, end of day, or off.

## 3. Daily planning (core feature)

- Each morning the user enters tasks: name, estimated duration, priority (P0 highest to P3 lowest).
- User adds **meetings** for the day as fixed time blocks (e.g. 14:00–15:00). No tasks are scheduled during meetings or breaks.
- The app generates the schedule automatically.
- **Manual editing:** the user can adjust the generated schedule by hand (move, resize or reorder tasks).
- **Mark as Cannot do:** besides the automatic flag, the user can manually mark any task as Cannot do.
- **Move to next day:** any Cannot do task can be moved to the next day with one click.
- **Mid-day additions:** tasks added after the day's plan is set do not change the plan; they are recorded in the Actual column as unplanned work.

## 4. Scheduling rules

1. Available time = working hours minus fixed breaks, meetings and post-task breaks.
2. Schedule by priority: all P0 first, then P1, P2, P3.
3. Within the same priority, pack gaps efficiently: longer tasks go into large gaps (e.g. morning block); shorter tasks fill small gaps (e.g. before lunch or a meeting) to avoid cut-offs.
4. If a task is longer than any free gap, split it across multiple gaps, minimising the number of splits.
5. Tasks that don't fit in the day are flagged **Cannot do**. The user decides what to drop or move; nothing rolls over automatically.

## 5. Plan vs actual (self-review)

- Day view shows two columns per time slot: **Plan** and **Actual**.
- Prompt setting: after every slot, at end of day, or off (manual entry anytime).
- For each slot the user confirms “done as planned” or enters what they actually did.
- Tasks added mid-day appear only in the Actual column, so unplanned work is visible against the original plan.
- Purpose is personal reflection only: how much was achieved and how focused the day was. Not for employers.

## 6. Later ideas (out of scope for v1)

- History and trends (completion rate, focus score over time).
- Calendar import for meetings.

## Open questions

- Platform and tech stack choice.

---
name: Calendar
description: Native Remind month, week, and event-duration timeline views.
---

# Calendar

Browse the canonical calendar in [Calendar](openlia://minions/calendar). The
source is `minions/calendar/data/reminders.rem`; companion notes are optional
Markdown documents under `minions/calendar/data/notes/`.

```openui
root = Calendar([views])
views = Tabs([
  TabItem("month", "Month", [CalendarMonth()]),
  TabItem("week", "Week", [CalendarWeek()]),
  TabItem("timeline", "Timeline", [GanttChart()])
])
```

The timeline shows event durations, not task dependencies. Native Remind must be
installed on the Workspace UI server. Notifications, invitations, and external
calendar changes remain disabled.

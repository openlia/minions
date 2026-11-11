---
$schema: ./event-note-template.schema.json
starts_at: null
location: null
video_link: null
attendees: []
---

# Calendar

## Purpose & Agenda

Browse local appointments in Month, Week, or Timeline. Choose **New appointment**
to review a draft before saving; cancelling writes nothing.

```openui
root = Calendar([views])
views = Tabs([
  TabItem("month", "Month", [CalendarMonth()]),
  TabItem("week", "Week", [CalendarWeek()]),
  TabItem("timeline", "Timeline", [GanttChart()])
])
```

## Discussion & Raw Notes

The schedule lives in [reminders.rem](./reminders.rem), not in this overview's
frontmatter. Event notes are optional companion documents. The timeline shows
event durations, not task dependencies. Native Remind must be installed on the
Workspace UI server.

## Follow-up Action Items

After saving an appointment, reopen it to verify its details. Notifications and
invitations remain off; attendee metadata does not authorize external delivery.

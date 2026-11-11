# Calendar

Open [Calendar](openlia://workspace/calendar/overview.md) for **Month**, **Week**, and
**Timeline** views. The timeline shows event durations, not task dependencies.
These views require a workspace-ui release with the `Calendar`, `CalendarMonth`,
`CalendarWeek`, and `GanttChart` OpenUI components and native Remind installed on
the workspace-ui server. The view is a fenced `openui` block in Markdown,
not a Mini-Project manifest or standalone UI file.

Calendar 0.3.0 requires the inline OpenUI runtime in `openlia/openlia#193`.
Deploy that runtime before updating this feature. No compatible released minimum
has been assigned yet; the unchanged development version is not a compatibility
guarantee. Preserve local files through the normal feature update/rebase flow;
do not delete old manifests, UI files, or appointments automatically.

## Create an appointment

Choose **New appointment**. Inspect and fill the title, start/end, explicit IANA
timezone, agenda, attendees, and location before choosing **Save appointment**.
Cancel writes nothing. Reopen the saved event from any view to verify its details.

Appointments are local Remind entries in `reminders.rem`. Notifications and
invitations are visibly off and unavailable; new entries use `NOQUEUE`. Attendees
are metadata only. The UI sends no messages, modifies no external calendar, and
creates no scheduled jobs. Existing entries keep their source-defined behavior.

The initial editor supports one-off timed appointments up to seven days long.
Use the Calendar skill/native source for recurrence or rescheduling. Ambiguous
or nonexistent DST wall times are rejected; choose an unambiguous time or UTC.

## Data and timezone

`reminders.rem` remains the calendar source of truth. Native Remind evaluates
recurrences and included calendars; event notes are optional companion Markdown,
not appointments. **New File** creates only a companion event note.

Legacy floating times use the server's calendar timezone (`OPENLIA_TIMEZONE`,
falling back to `TZ` and then UTC). Changing **Display timezone** changes only
presentation. New entries preserve their appointment timezone in INFO metadata
and use a native `tzconvert` expression for their absolute start instant.

The UI evaluator disables execution and queueing and reports native diagnostics
instead of showing an apparently empty calendar. It supports literal `.rem` or
`.remind` includes confined to this calendar folder, up to 32 files / 2 MiB total,
with bounded date ranges. Dynamic includes, `DO`, `SYSINCLUDE`, `INCLUDECMD`, paths
outside the calendar folder, and symlinks are rejected. These are UI safety limits,
not restrictions on what native Remind can do outside the UI.

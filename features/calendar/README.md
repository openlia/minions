# Calendar 0.4

Open [Calendar](openlia://minions/calendar) for **Month**, **Week**, and
**Timeline** views. The timeline shows event durations, not task dependencies.
These views require a Workspace UI release with the `Calendar`, `CalendarMonth`,
`CalendarWeek`, and `GanttChart` OpenUI components and native Remind installed.

Calendar 0.4 is a breaking migration to the Calendar Minion. Its canonical data
lives under `minions/calendar/data/`; no appointments are shipped in the catalog.
The old `calendar/` workspace location is not read or maintained.

## Create an appointment

Open the Calendar Minion input form. Inspect and fill the title, start/end,
explicit IANA timezone, agenda, attendees, and location before choosing
**Validate & Preview**. Inspect Dashboard and choose **Save appointment** only
after reviewing the exact Remind entry. Cancel writes nothing.

Appointments are local Remind entries in `reminders.rem`. Notifications and
invitations are visibly off and unavailable; new entries use `NOQUEUE`. Attendees
are metadata only. The UI sends no messages, modifies no external calendar, and
creates no scheduled jobs. Existing entries keep their source-defined behavior.

The initial editor supports one-off timed appointments up to seven days long.
Use the Calendar skill/native source for recurrence or rescheduling. Ambiguous
or nonexistent DST wall times are rejected; choose an unambiguous time or UTC.

## Data and timezone

`minions/calendar/data/reminders.rem` remains the calendar source of truth. Native
Remind evaluates recurrences and included calendars; event notes under
`minions/calendar/data/notes/` are optional companion Markdown, not appointments.
Supplying an agenda creates only a companion event note in addition to the
Remind entry.

Legacy floating times use the server's calendar timezone (`OPENLIA_TIMEZONE`,
falling back to `TZ` and then UTC). Changing **Display timezone** changes only
presentation. New entries preserve their appointment timezone with Remind's
native `TZ` clause and INFO metadata.

The Minion evaluator disables execution and queueing and reports native diagnostics
instead of showing an apparently empty calendar. It supports literal `.rem` or
`.remind` includes confined to the Calendar data folder, up to 32 files / 2 MiB total,
with bounded date ranges. Dynamic includes, `DO`, `SYSINCLUDE`, `INCLUDECMD`, paths
outside the calendar folder, and symlinks are rejected. These are UI safety limits,
not restrictions on what native Remind can do outside the UI.

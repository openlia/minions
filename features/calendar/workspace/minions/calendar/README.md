---
name: Calendar
description: Native Remind calendar with confirmed local appointment entry and agenda views.
icon: calendar
---

# Calendar

Open [Calendar](openlia://minions/calendar) for Month, Week, and Timeline views.
The canonical Remind calendar and companion event notes live in
`minions/calendar/data/`; no appointments are shipped with the app.

## Setup

Install native `remind`, save Configuration, and use Manual Refresh to load the
calendar. The default source is `data/reminders.rem`. Automatic triggers are off
by default. The app never contacts external calendars, sends invitations, queues
notifications, or creates scheduled jobs.

## Structured appointments

Submit an ISO-8601 start and end with an explicit offset and IANA timezone. The
first submission creates a pending proposal only. Inspect the exact Remind entry
on Dashboard and confirm it with `SAVE`; cancellation never changes the calendar.
The initial form supports one-off timed appointments up to seven days long.
Use the Calendar skill for recurring schedules, advanced Remind expressions, and
rescheduling existing entries.

An agenda creates an optional companion note under `data/notes/`. Remind remains
the source of truth; notes are supporting documents linked through `Event-Note:`.
Existing literal includes are preserved and validated with native Remind. Missing
or invalid native evidence is reported, not treated as an empty calendar.

## Briefing view

`briefing.view.json` exposes only bounded upcoming events from `data/reminders.rem`
through the native Remind reader. It does not expose notes, pending proposals,
configuration, code, tests, or caches. The briefing reader applies the declared
record, excerpt, file, and byte limits before adding source-linked events.

## Data and upgrades

Portable templates live under `templates/`; `data/`, `config.json`, pending
proposals, and local notes are runtime state and are not catalog source files.
Managed updates preserve the calendar data and configuration. This is a breaking
migration from the former `calendar/` workspace location; existing development
workspaces must move their records before using this app.

## Tests

Run `python3 -B -m unittest discover -s tests` from this directory. Tests mock the
native Remind executable and use temporary synthetic app data.

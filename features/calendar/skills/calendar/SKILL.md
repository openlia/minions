---
name: calendar
description: Manage calendar events, agendas, reminders, and recurring schedules by authoring Remind entries directly with the LLM.
version: 0.2.0
platforms: [macos, linux]
required_environment_variables: []
required_credential_files: []
workspace_domains:
  - calendar
metadata:
  hermes:
    tags: [personal-os, calendar, remind, agenda, scheduling, meetings]
    category: productivity
---

# Calendar

Calendar entries are authored directly in Remind syntax. Do not use a
calendar-specific formatter or parser: native Remind is the source of truth
for syntax, recurrence, includes, and agenda evaluation.

This rule applies to agent-side calendar operations. The workspace UI may parse
Remind files for visualization, but agent edits must remain native Remind
syntax.

## When to Use

- Use when viewing, querying, scheduling, rescheduling, or canceling calendar events, meetings, appointments, and reminders.
- Use when scheduling multi-day events, holidays, vacations, conferences, offsites, and date ranges.
- Use to check today's agenda, multi-day lookaheads, upcoming deadlines, and event conflicts.
- Use when events contain rich metadata such as attendees (names, emails, wiki links), physical locations (addresses, rooms, Google Maps links), video conferencing links (Zoom, Google Meet, Microsoft Teams), tags, and descriptions.
- Use to manage recurring schedules (daily standups, weekly 1:1s, monthly reviews, bi-weekly paydays, annual anniversaries).

## Data Model

Calendar entries are maintained in the workspace using [Remind](https://manpages.debian.org/testing/remind/remind.1.en.html) syntax.

- **Primary Calendar File**: `calendar/reminders.rem` in the runtime workspace (e.g. `/opt/data/workspace/calendar/reminders.rem`).
- **Modular Calendars**: Additional `.rem` files (e.g. `calendar/holidays.rem`, `calendar/work.rem`) can be included via Remind's `INCLUDE` directive:
  ```remind
  INCLUDE holidays.rem
  ```
- **Companion Event Notes**: Deep meeting agendas, minutes, and follow-up action items can be tracked in Markdown files using `calendar/event-note-template.md` (e.g. `calendar/2026-10-15-q4-sync.md`), linked via the `Event-Note:` INFO header.

### Remind Syntax & INFO Convention

Remind specifies events with the `REM` command:
```remind
REM <date_spec> [THROUGH <end_date>] [AT <time>] [DURATION <duration>] [TAG <tag>]... \
    [INFO "<Header>: <Value>"]... \
    MSG <Summary>
```

Per the Debian `remind(1)` specification, the `INFO` keyword transmits metadata to backends. Each `INFO` string has the form `"Header: Value"` (no whitespace before the colon; headers are case-insensitive and unique per reminder).

Standardized INFO headers supported by OpenLia:

| Header | Description | Example |
| :--- | :--- | :--- |
| `Attendees:` | Comma-separated list of attendees (names, emails, or workspace links) | `Alice <alice@example.com>, Bob, openlia://workspace/people/charlie.md` |
| `Location:` | Physical address, room, or venue name | `123 Market St, San Francisco, CA` |
| `Map-Url:` | Google Maps or web link to location (alias: `Map:`) | `https://maps.google.com/?q=123+Market+St` |
| `Video-Link:` | Video conferencing link: Zoom, Google Meet, Teams (alias: `Call:`) | `https://meet.google.com/abc-defg-hij` |
| `Description:` | Detailed agenda, topics, or notes | `Quarterly review and roadmap planning` |
| `Event-Note:` | Companion workspace event note Markdown file (alias: `Note:`) | `calendar/2026-10-15-roadmap-review.md` |

### Date & Time Specification Reference

- **Specific Date**: `2026-10-15` or `15 Oct 2026`
- **Multi-Day Range (Inclusive)**: `REM 15 Oct 2026 THROUGH 19 Oct 2026 TAG holiday MSG Autumn Break` or `REM 2026-10-15 THROUGH 2026-10-19 MSG School Holiday`
- **Range vs. Duration Principle**: Use `THROUGH` to express inclusive multi-day calendar spans. Do NOT use `DURATION` as a substitute for a date range; `DURATION` specifies the length of an occurrence on a single day (e.g. `DURATION 1:30`), not the calendar span of a holiday.
- **Time & Duration**: `AT 10:00 DURATION 1:00` (or `DURATION 60`)
- **Advance Warning**: `+3` (warn 3 days ahead) or `AT 14:00 +15` (warn 15 minutes ahead)
- **Weekly Recurrence**: `REM Mon AT 09:00 DURATION 0:30 MSG Team Standup`
- **Multiple Days**: `REM Mon Wed Fri AT 08:30 MSG Morning Gym`
- **Monthly Recurrence**: `REM 15 AT 14:00 MSG Monthly Billing`
- **Interval Recurrence**: `REM 2026-10-14 *14 AT 11:00 MSG Sprint Planning` (every 14 days)
- **Nth Weekday of Month**: `REM Mon 1 Oct MSG First Monday in October`
- **Last Weekday of Month**: `REM Mon 1 -7 Nov MSG Last Monday in November`
- **Annual**: `REM Oct 15 MSG Project Anniversary`

## Operating Procedures

### 1. Inspect the Existing Calendar

Before writing, read `calendar/reminders.rem` and any files named by its
`INCLUDE` directives. Preserve existing comments, source references, Unicode,
and unrelated entries. Calendar includes are resolved reliably when Remind is
run from the calendar directory, so use that directory as the working
directory for all checks.

```sh
cd /opt/data/workspace/calendar
```

There is no calendar-specific helper script. Do not invent a second parser or
rewrite a calendar through an encoding-normalization command.

### 2. View Agenda & Lookaheads (Read-Only)

Run native Remind directly:

```sh
# View today's agenda; -r disables RUN directives and -q disables queueing
remind -r -q -g reminders.rem

# View a specific date
remind -r -q -g reminders.rem YYYY-MM-DD

# View a one-week lookahead from a specific date
remind -r -q -s+1 reminders.rem YYYY-MM-DD
```

`-s+N` means N weeks, not N days. For a machine-readable monthly result, use
Remind's pure JSON calendar mode and filter the requested date from its
`entries`: `remind -r -q -ppp reminders.rem YYYY-MM-DD`. Do not assume that
the newer `--json` option is installed. Check stderr as well as the exit
status; Remind can report a parse error while still returning status 0.

Present the agenda in clean Markdown:
- Format each event with its start time, duration, and title.
- Render clickable video call links: `[Join Call](URL)`.
- Render physical location and clickable maps link: `📍 Location` (`[Map](URL)`).
- List attendees with formatting: `👥 Attendees: Alice, Bob`.
- Include description excerpts or linked companion notes when present.

### 3. Schedule New Events

Construct the `REM` block directly and append it to the appropriate calendar
file. Use a specific ISO date when the event is a one-off. Use Remind's
weekday/month/repeat syntax only when the recurrence is intentional.

```remind
REM 2026-10-15 AT 10:00 DURATION 1:00 TAG meeting TAG client \
    INFO "Location: 123 Market St, San Francisco, CA" \
    INFO "Map-Url: https://maps.google.com/?q=123+Market+St" \
    INFO "Attendees: Alice <alice@example.com>, openlia://workspace/people/bob.md" \
    INFO "Description: Quarterly client sync and roadmap review" \
    INFO "Event-Note: openlia://workspace/calendar/2026-10-15-client-review.md" \
    MSG Client Roadmap Review

# Multi-day holiday or date range (inclusive dates):
REM 15 Oct 2026 THROUGH 19 Oct 2026 \
    TAG holiday TAG school TAG lina \
    INFO "Description: Lina — Nghỉ giữa học kỳ I" \
    MSG Lina — Nghỉ giữa học kỳ I
```

Keep `MSG` last. Repeat `TAG` for each tag. Use at most one `INFO` clause for
each header, and keep header names free of whitespace before the colon.

**Multi-Day Scheduling Rule**: When scheduling multi-day events (school holidays,
family vacations, multi-day conferences, business trips), always use
`THROUGH <end_date>` to express the inclusive date range. Never create duplicate
single-day reminders for each consecutive day, and never misuse `DURATION` to
represent multi-day spans. This ensures logical event integrity across both native
Remind notifications and workspace calendar views.

Remind accepts UTF-8 event text. Preserve Vietnamese, Japanese, Korean, and
other Unicode text exactly as authored. Never transliterate, strip accents,
or replace titles with generic labels to work around an unrelated parse error.
Literal square brackets in `MSG` or other Remind expressions can be parsed as
Remind expressions; use parentheses for ordinary prose, or escape and test a
deliberate expression. In `MSG` text, write a literal percent sign as `%%`;
Remind's substitution filter renders it as `%`. Literal percent signs in
`INFO` values and URLs should still be tested with native Remind rather than
normalized.

### 4. Reschedule or Cancel Events

1. First inspect the existing reminders with native Remind and read the target file.
2. To reschedule, update only the target `REM` block and retain its metadata and source references.
3. To cancel, comment out or remove the `REM` block only after the user approves the destructive change.
4. Validate the complete calendar, including included files, with native Remind before reporting success.

### 5. Native Validation

Run the check from the calendar directory and inspect both output streams:

```sh
remind -r -q -s1 reminders.rem YYYY-MM-DD > /tmp/openlia-calendar.out \
  2> /tmp/openlia-calendar.err
status=$?
test "$status" -eq 0 && test ! -s /tmp/openlia-calendar.err
```

Use a date that exercises the changed entries. For a modular calendar, also
confirm that each included file is found and that its entries appear in the
native output. Do not call a file valid based only on a regular-expression
check or a zero exit code.

### 6. Safety & Policy Rules

- **Workspace UI appointments**: The inline view in `calendar/overview.md` composes reusable
  `CalendarMonth`, `CalendarWeek`, and `GanttChart` (event-duration timeline)
  components around native Remind data. Its **New appointment** flow creates
  one-off local entries with `NOQUEUE` and timezone INFO metadata. Preserve these
  fields and stable `openlia-ui-...` tags when editing. Do not enable queueing,
  notifications, or invitation delivery merely because attendees are listed.
  Markdown event notes remain companion documents, never the scheduling source.

- **Workspace File Mutations**: Adding or updating events in `calendar/reminders.rem` is a local workspace change. Always verify the proposed change with the user before committing destructive edits or deleting existing entries.
- **External Calendars**: Local `reminders.rem` management does NOT authorize modifying external calendar services (Google Calendar, Microsoft Outlook, CalDAV). Modifying external calendar integrations requires explicit authorization under `modify_external_calendar` policy.

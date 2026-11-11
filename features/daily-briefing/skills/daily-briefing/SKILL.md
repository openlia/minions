---
name: daily-briefing
description: Collect workspace sources and prepare an evidence-based daily briefing.
version: 0.2.1
platforms: [macos, linux]
required_environment_variables: []
required_credential_files: []
workspace_domains:
  - inbox/daily-briefing
metadata:
  hermes:
    tags: [personal-os, briefing, daily]
    category: productivity
---

# Daily Briefing

## When to Use

Use for a morning or on-demand briefing that synthesizes calendar events,
active tasks, monitors, recent changes, and personal priorities into an
actionable snapshot.

The bundled registry helper discovers collections from folders, local templates,
schemas, and Markdown records; `workspace.yaml` registration is not required.
Read `/opt/data/permissions.yaml` for scheduled-work and consequential-action
boundaries.

## Gather Sources

Run the bundled collector with the explicit workspace root and local briefing
date:

```sh
python scripts/build_briefing.py --collect \
  --workspace-root /opt/data/workspace \
  --date YYYY-MM-DD
```

The collector prints a compact, read-only source packet using discovered entries
whose `include_in_briefing` is true. It uses structured dates and statuses where available, includes active
records and recent open loops, and reports missing source directories separately
from directories with no matching records.
By default it includes calendar and due-date items through the next seven days,
recent decisions and inbox captures, and up to 40 source records within an
18,000-character packet.
Increase these limits only when the packet reports omitted records.

The collector also reads local Git history since the latest earlier daily
briefing, or since the previous day when there is no earlier report. Pass
`--since YYYY-MM-DD` to override that baseline. It performs no network access
and does not write to the workspace.

When the registry opts finance sources into briefings, include only those
registered finance records. Finance intake items are signals for blocked,
pending-review, or unreconciled work; finance reviews are signals for due,
recently changed, or attention-needed periodic reviews. A briefing does not
post journal entries, reconcile accounts, or make investment recommendations.

Use the packet to decide which full source records need reading. Read those
records directly before making a consequential claim; the packet excerpts are
discovery aids, not substitutes for evidence. Do not treat missing or
unrecognized metadata as proof that a record is irrelevant. Extension records
without task or calendar semantics are treated as recent signals, not as
commitments.

## Report Structure

Use `templates/briefing.md` as the report skeleton. For an interactive run,
write the completed report to `inbox/daily-briefing/YYYY-MM-DD.md` when report
writing is authorized. For a scheduled run, use the configured
`scheduled_work.report_destination` instead. Create the destination directory
when it does not exist. The template headings are the report contract. Replace
the starter prompts with report content while preserving the template's
heading structure:

1. **Today**: focus, evidenced calendar events, tasks, follow-ups, active
   monitors, and due finance work. If no calendar or task records are
   available, say so explicitly;
   do not imply that the day is empty.
2. **What Changed**: separate verified **Facts**, possible **Signal**, and
   **Missing evidence**. Keep inferences labeled and cite their supporting
   records.
3. **Important-Urgent Matrix**: rank up to six evidenced items under **Do
   first**, **Schedule**, **Delegate / Coordinate**, and **Defer / Drop**. Name
   a clear owner for delegated work. Preserve commitments; do not recommend
   dropping them without evidence.

When a proposed decision is important or blocks a project, surface it as a
choice that needs attention and link the decision record. Do not score options
or imply a chosen option in the briefing; use [Decision Analysis](openlia://skills/decision-analysis)
as a separate follow-up when the person is ready to compare the trade-offs. If
the choice is blocked by missing external evidence, use [Deep Research](openlia://skills/deep-research)
before scoring options.

Do not include every research brief in the daily source packet. Treat an active
task, project, or decision as the research anchor. When that record links to a
brief or identifies an evidence gap, read the relevant brief directly and
surface only the question, why it matters now, the freshness need, and a bounded
next research check. A briefing identifies the follow-up; it does not start
research or create a task merely because an evidence gap is mentioned.

Read the full source records needed to support the report, then fill the
template directly. Cite factual items with canonical workspace links such as
`[Task](openlia://workspace/tasks/write-outline.md)`. Do not invent dates,
status, progress, priority, owners, or external conditions. When a field is
absent, identify it as missing evidence. Do not use `build_briefing.py` to
render or write the report; it is a source collector only.

After writing the report, verify that the file exists at the nested dated path,
all template headings remain present, every factual item has a source citation,
and no starter prompt remains without either content or an explicit statement
that the corresponding evidence is unavailable.

## Delivery

- By default, save an interactive dated report to the registered
  `inbox/daily-briefing/YYYY-MM-DD.md` when the current request or
  `assistant-policy.yaml` authorizes `generate_reports`.
- If the caller explicitly requests read-only/no-write delivery, return the
  structured report in chat and do not write a workspace report. For scheduled
  runs, resolve `scheduled_work.report_destination` and write only to
  `<report_destination>/YYYY-MM-DD.md` when `scheduled_work.enabled` and
  `generate_reports` are both enabled. The destination must remain beneath a
  registered and policy-allowed workspace domain; never fall back to the
  interactive default when the configured destination is unavailable. Otherwise
  return the report in the job output.
- For a saved report, return 3–6 concise bullets in the user's configured
  output language and link to the actual saved path, for example
  `[Daily briefing YYYY-MM-DD](openlia://workspace/inbox/daily-briefing/YYYY-MM-DD.md)`.
- Send the full structured report in chat only when the caller requests
  no-write delivery or explicitly asks for the entire report. Do not link to a
  report file when no file was written.
- Do not embed environment-specific HTTP origins.

## Safety

A briefing is read-only with respect to source records unless a separate
delegated action is explicitly in scope: never create tasks, modify calendar
entries, send messages, or change source documents merely because a briefing
mentions them. A delegated report write is limited to the configured report
destination. Review the completed report for the template headings, explicit
citations, unsupported claims, and the authority used before delivery.

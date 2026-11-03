---
name: Personal Health
description: Person-scoped family health records, source-linked encounters, and measurements.
icon: heart
---

# Personal Health

Open [Personal Health](openlia://minions/personal-health). Canonical records are
Markdown with validated frontmatter in `data/`. Profiles, encounters, conditions,
treatments, and measurements remain documents, not a private JSON database.
The [Personal Health skill](openlia://skills/personal-health) uses these same files.

## Setup and input

Install Dependencies once, then save Configuration. Triggers default off and
there is no cron default. Create a profile with a stable `person_id` and explicit
relationship to the user. Select that exact person for every subsequent entry.
Never infer a person from a display name. Use Manual Refresh to read existing
records; submitting input also refreshes Dashboard without enabling triggers.

The structured form supports profiles, encounters, conditions, treatments, and
measurements. Measurements are history `test` records with structured `results`;
they do not need a second dataset. Dates retain year/month/day precision or an
explicitly zoned timestamp. User reports remain reported; missing information is
unknown, not negative evidence. Conditions expose verification and clinical status
separately; treatments distinguish reported use from prescribed intent and completion.
Retain supplied `openlia://source/…` references. Raw medical files stay in the Vault.

Dashboard separates records by stable person ID, provides record links, and shows
only recorded facts. It does not diagnose, interpret results, recommend treatment,
or present counts as an assessment of health. A clinician remains the decision-maker.

## Documents and upgrades

Browse `data/profiles`, `data/history/<person_id>`, `data/conditions/<person_id>`,
`data/treatments/<person_id>`, and `data/reviews/<person_id>` in Documents. App-owned
templates and schemas live in `templates/`. Keep corrections as amendments or
superseding records rather than silently rewriting history. The initial form
creates records, not destructive edits.

Managed upgrades preserve `data/` and `config.json`; neither is distributable app
source. No compatible released runtime minimum has yet been assigned; test the
exact runtime/catalog pair before release promotion.

## Verification

Run `python3 -B -m unittest discover -s tests` here. Run
`python3 audit_health.py --workspace-root /path/to/workspace --json` to check person
boundaries and cross-record references. App tests use temporary synthetic records.

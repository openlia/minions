---
name: weekly-review
description: Review goals, tasks, decisions, health records, and finance open loops without acting.
version: 0.2.0
platforms: [macos, linux]
required_environment_variables: []
required_credential_files: []
metadata:
  hermes:
    tags: [personal-os, review, weekly]
    category: productivity
---

# Weekly Review

## When to Use

Use at the end or start of a week to reduce open loops and choose a small set
of outcomes for the next period.

## Procedure

1. Gather current goal, task, and claim records—plus decision, health, and finance records when those collections exist—as read-only
   inputs. Read research briefs linked from active goals, open decisions, and
   unresolved tasks; research briefs are supporting records, not a replacement
   for those domain records.
2. Run `scripts/review_week.py INPUT.json`.
3. Check completed work, active goals, open tasks, unresolved decisions, health
   records needing review, finance intake or review blockers, unreconciled accounts, and
   claims requiring review. Include proposed decisions and decided decisions
   whose `review_date` has arrived in the decisions input with `revisit: true`,
   so the helper surfaces them for attention. Read claim records directly from
   `knowledge/claims/`; check their status, `valid_until`, and `review_after`
   against the current date when assembling the claim input.
4. Read `templates/weekly-review.md` and fill its headings from the helper's
   structured JSON output. The helper classifies records only; it does not
   render the report or invent next-week outcomes. Add a research follow-up only
   when a linked brief is stale, its next-check trigger has arrived, its budget
   ended before the question was resolved, or the open loop still lacks enough
   evidence.
5. Draft a short next-week list. Apply routine updates only when the current
    request authorizes them, respecting `/opt/data/permissions.yaml`; otherwise ask before
   changing workspace records.

The input object accepts `week`, `goals`, `tasks`, `decisions`, `claims`,
`health`, and `finance` lists. Health records are supplied directly as read-only
summaries; the helper surfaces records marked `needs_review` or `review_due`,
draft or unknown records, and unconfirmed or provisional conditions. Finance
records are supplied directly as read-only summaries; the helper surfaces
blocked, pending-review, attention-needed, unreconciled, or incompletely valued
records. Statuses are compared literally and the JSON output is deterministic.

The saved or chat report must preserve the template headings: completed work,
closed or cancelled work, active goals, open loops, research follow-ups,
decisions to revisit, claims to review, health records to review, and next-week
outcomes with first actions.

## Pitfalls

- Do not equate activity with progress or add tasks to fill space.
- Do not close a task or decision merely because it is old.
- Do not reopen research without a changed question, freshness trigger, new
  evidence gap, or meaningful change in the decision context.
- Use [Decision Analysis](openlia://skills/decision-analysis) when a proposed
  decision needs explicit comparison; do not resolve it by age or activity.
- Do not activate, retract, or supersede a claim during a review unless the
  current request or policy explicitly authorizes that memory action. Inferred
  claims remain candidates by default.
- A review does not authorize messages, purchases, or scheduling.

## Verification

Confirm all supplied open loops, health attention items, finance attention items,
and claim review items are represented, completed items are separated, and no
source file was changed.

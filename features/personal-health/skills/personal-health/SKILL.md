---
name: personal-health
description: Maintain structured family medical history, conditions, treatments, and clinician-ready summaries.
version: 0.1.0
platforms: [macos, linux]
required_environment_variables: []
required_credential_files: []
workspace_domains:
  - health
  - health/profiles
  - health/history
  - health/conditions
  - health/treatments
  - health/reviews
metadata:
  hermes:
    tags: [personal-os, health, medical-history, family]
    category: health
---

# Personal Health

## When to Use

Use for significant medical history and care records for the current user or a
family member. This includes consultations, diagnoses, allergies, tests,
procedures, immunizations, hospitalizations, medication courses, and summaries
for a clinician. Do not use this workflow for appointment scheduling; link a
health record to a calendar note when appointment context is useful.

This skill is deliberately not a daily symptom or dose-adherence tracker.
Create a history entry when an event is medically significant or changes the
person's record.

## Record Model

Read `workspace.yaml`, `assistant-policy.yaml`, and the relevant health template
and schema before writing. The registered health paths are:

- `health/profiles/`: one stable identity record per tracked individual.
- `health/history/`: significant symptoms, encounters, tests, procedures,
  immunizations, hospitalizations, and allergy reactions.
- `health/conditions/`: diagnoses, allergies, intolerances, risks, and family
  history with separate verification and clinical status.
- `health/treatments/`: medication and other care courses, without individual
  dose-adherence logging.
- `health/reviews/`: dated, source-linked medical summaries and clinician
  handoff reports.

Use person-scoped directories for records:

```text
health/profiles/person-001.md
health/history/person-001/<record>.md
health/conditions/person-001/<record>.md
health/treatments/person-001/<record>.md
health/reviews/person-001/<record>.md
```

Every health record must also contain `person_id`. The directory and metadata
are intentionally redundant: the directory makes separation visible and the
field supports validation, search, and future export.

## Person Boundary

Establish the subject before recording or summarizing anything. Use the stable
`person_id`, not a display name, as the identity key. The current user is a
normal profile with `relationship_to_user: self`; children, parents, and other
family members use separate profiles.

- Never infer that an unqualified symptom belongs to the current user when the
  conversation concerns another family member.
- If a pronoun or name could identify more than one person, keep the item in
  `inbox/` or ask one focused clarification.
- Link an existing `people/` record with `people_ref` when available, but do not
  copy relationship notes into the clinical record.
- Export and summarize one person at a time by default.

## Clinical Evidence Rules

Keep these distinctions explicit:

- A symptom or finding is not a diagnosis.
- A user hypothesis is not a clinician-confirmed condition.
- `verification_status` describes evidence for a condition; `clinical_status`
  describes whether it is currently active.
- A prescribed or recommended treatment is not proof that it was taken or
  completed.
- Unknown information remains unknown. Do not convert missing allergies,
  medication history, or test results into a negative claim.
- Preserve source type and stable source references (`openlia://source/{source_id}#{version_id}`). Raw medical documents and exports belong in the Ingestion Vault (`OPENLIA_INGESTION_ROOT`), not in the tracked workspace.
- Preserve corrections with `amended`, `entered-in-error`, superseding records, or explicit notes rather than silently replacing history. When a lab report or clinical document in the Ingestion Vault is replaced with a new version (`ver_002`), inspect the diff and update or supersede the corresponding `health/history/` or `health/conditions/` record with `amended` status and the new `#ver_002` citation. If an erroneously uploaded medical document is deleted from the Vault (`(deleted source: src_...)`), mark any clinical record derived solely from that upload as `entered-in-error` rather than leaving unverified clinical claims active.


Do not diagnose, choose treatment, interpret a result beyond the supplied
source, or present a workspace summary as medical advice. A clinician remains
the decision-maker.

## Workflow

1. **Resolve the person.** Find the matching health profile and confirm the
   `person_id`.
2. **Choose the record type.** Use history for what happened, condition for a
   diagnosis or ongoing issue, treatment for a care course, and review for a
   derived summary.
3. **Preserve event precision.** Store known year/month/day or timestamp without
   inventing missing precision. Timestamps must include a timezone offset.
4. **Capture structured facts.** Keep test values, units, reference ranges,
   clinical status, treatment dates, and optional supplied terminology coding in
   frontmatter. Keep narrative context in the Markdown body.
5. **Link only established relationships.** Use IDs for conditions, treatments,
   history entries, and calendar notes. Leave links empty when the relationship
   is not established.
6. **Validate.** Run the workspace template validator and the health integrity
   audit before treating the record set as consistent.
7. **Create follow-up context.** Use existing `tasks/` for concrete collection
   or follow-up actions and `calendar/` for appointments. Those writes remain
   separate from clinical facts and external actions.
8. **Summarize when useful.** Create a review with an `as_of` boundary and all
   source record IDs. Never let a generated review become the only copy of a
   clinical fact.

## Treatment History

Create a new treatment record when a medication or care regimen materially
changes. Link the replacement through `revision_of` and preserve the previous
record's end or superseded status when known. Use `intent` to distinguish
`prescribed`, `recommended`, `reported-use`, and other bases. Do not add a dose
log unless a future explicit workflow is introduced for that purpose.

## Clinician Summary

A clinician handoff should be one person's source-linked review, not a dump of
the entire workspace. Include scope and cutoff date, active and relevant past
conditions, allergies or intolerances, significant events, current or recent
treatments, important results, unresolved questions, and information gaps.
State when a section is incomplete. A future FHIR exporter can map profiles to
`Patient`, conditions to `Condition` or `AllergyIntolerance`, family-history
conditions to `FamilyMemberHistory`, history entries to `Observation`,
`Encounter`, `Procedure`, or `Immunization` (with test reports potentially
producing a `DiagnosticReport` plus `Observation` resources), and treatments to
`MedicationRequest` or `MedicationStatement` in FHIR R4. Keep terminology codes
supplied by source material; never invent codes merely to fill an export field.

## Handoffs

- **Input routing:** a separate intake workflow may provide resolved person
  identity and source candidates. This skill validates and records the health
  model; it does not decide how external inputs are ingested.
- **Calendar:** use calendar notes for appointment scheduling and health records
  for clinical results, linking them with `calendar_refs`.
- **Tasks:** create tasks for actions such as requesting records or asking a
  clinician a question; do not encode these as treatment status.
- **Inbox triage:** ambiguous identity, dates, medical interpretation, or source
  attribution stays in `inbox/` for review.
- **Weekly review:** include draft health reviews, unresolved conditions, and
  records whose `review_after` or `next_review_on` date has arrived.

For `family-history` condition records, `person_id` is the person whose history
is being documented. Use `family_member_relation` for the relative's relation
and `related_person_id` when that relative also has a tracked health profile.
This preserves the distinction needed for a future FHIR `FamilyMemberHistory`
export.

## Verification

Confirm that every record has a person, stable ID, source basis, and appropriate
date precision; person-scoped paths agree with `person_id`; referenced records
exist and belong to the same person; IDs are unique; condition and treatment
status distinctions are preserved; summaries have an explicit cutoff and source
list; and no raw medical export or credential entered the workspace.

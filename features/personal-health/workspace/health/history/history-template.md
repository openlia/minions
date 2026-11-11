---
$schema: ./history-template.schema.json
id: null # Stable identifier, e.g. history-20261009-001.
person_id: null # Must match one health/profiles/<person_id>.md record.
kind: other # symptom | encounter | test | procedure | immunization | hospitalization | allergy-reaction | other
status: reported # draft | reported | confirmed | amended | entered-in-error | archived
occurred_start: null # YYYY, YYYY-MM, YYYY-MM-DD, or ISO-8601 date-time with timezone.
occurred_end: null
recorded_at: null # ISO-8601 date-time with timezone.
source_type: user-report # user-report | clinician | lab-report | imaging-report | device | imported-record | other
source_ref: null # Stable reference to the private original or source record.
coding:
  system: null # Optional terminology URI, such as a supplied SNOMED CT or LOINC system.
  code: null
  display: null
condition_ids: []
treatment_ids: []
calendar_refs: [] # Optional references to calendar notes; the calendar remains authoritative for appointments.
results: [] # Structured test or measurement values; narrative interpretation belongs below.
---

# <Health History Entry>

## Event
- Person:
- What happened:
- Occurred:
- Source and provenance:

## Findings & Interpretation
- Reported findings:
- Clinician interpretation:
- Uncertainty or missing information:

## Links & Follow-up
- Conditions:
- Treatments:
- Calendar notes:
- Follow-up task or question:

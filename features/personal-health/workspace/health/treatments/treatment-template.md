---
$schema: ./treatment-template.schema.json
id: null # Stable identifier, e.g. treatment-001.
person_id: null
kind: medication # medication | therapy | procedure | lifestyle | other
name: null
status: unknown # planned | active | completed | stopped | on-hold | not-taken | unknown | entered-in-error
intent: unknown # prescribed | recommended | reported-use | self-directed | completed | unknown
started_on: null # YYYY, YYYY-MM, YYYY-MM-DD, or ISO-8601 date-time with timezone.
ended_on: null
source_type: user-report # user-report | clinician | prescription | discharge-summary | imported-record | other
source_ref: null
condition_ids: []
history_ids: []
calendar_refs: []
revision_of: null # Previous treatment ID when this record replaces a regimen.
medication:
  strength: null
  dose: null
  dose_unit: null
  route: null
  frequency: null
  prescriber: null
  coding:
    system: null
    code: null
    display: null
---

# <Treatment>

## Care
- Person:
- Treatment:
- Kind:
- Status:
- Intent or basis:
- Start and end:

## Medication Details
- Strength and dose:
- Route and frequency:
- Prescriber or source:
- Instructions:

## History & Links
- Conditions addressed:
- Related history entries:
- Calendar notes:
- Changes, outcome, or reason stopped:

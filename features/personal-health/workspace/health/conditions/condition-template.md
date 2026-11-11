---
$schema: ./condition-template.schema.json
id: null # Stable identifier, e.g. condition-001.
person_id: null
kind: diagnosis # diagnosis | allergy | intolerance | risk-factor | family-history | other
name: null
family_member_relation: null # Used for family-history entries, e.g. mother or maternal uncle.
related_person_id: null # Optional tracked health profile for the family member.
verification_status: unknown # unconfirmed | reported | provisional | confirmed | refuted | entered-in-error | unknown
clinical_status: unknown # active | recurrence | relapse | inactive | remission | resolved | unknown
onset: null # YYYY, YYYY-MM, YYYY-MM-DD, or ISO-8601 date-time with timezone.
abatement: null
coding:
  system: null
  code: null
  display: null
source_refs: []
history_ids: []
review_after: null # YYYY-MM-DD
---

# <Condition>

## Clinical Identity
- Person:
- Condition or substance:
- Kind:
- Verification status:
- Clinical status:
- Onset and resolution:

## Evidence
- Source:
- Supporting history entries:
- For allergy or intolerance: reaction, severity, and exposure context:

## Notes
- Distinguish clinician-confirmed diagnoses from reports or hypotheses.
- Record contradictions or later corrections without silently overwriting prior evidence.

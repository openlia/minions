---
$schema: ./profile-template.schema.json
id: null # Same stable value as person_id, e.g. person-001.
person_id: null # Stable identifier, e.g. person-001; do not use the display name as an ID.
display_name: null
relationship_to_user: null # self | child | spouse | partner | parent | sibling | grandparent | grandchild | other-family | caregiver | other
people_ref: null # Optional relative path or stable reference to a people/ record.
date_of_birth: null # YYYY, YYYY-MM, or YYYY-MM-DD; keep unknown precision.
identity_status: active # active | inactive | deceased | unknown
source_refs: [] # Stable references to source records; never store raw exports here.
---

# <Health Profile>

## Identity
- Display name:
- Relationship to user:
- General people record:
- Date of birth or known age:

## Current Overview
- Active conditions:
- Current or recent treatments:
- Important allergies or intolerances:
- Last reviewed:

## Notes
- Keep clinical facts in linked health records rather than duplicating the history here.

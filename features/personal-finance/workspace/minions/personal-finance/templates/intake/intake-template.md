---
$schema: ./intake-template.schema.json
id: null
status: received # received | extracting | pending-review | ready-to-post | posted | reconciled | blocked | archived
source_type: other # bank-statement | card-statement | wallet-statement | cash-note | payslip | receipt | manual-entry | other
source_ref: null # Stable reference to the private source; never put credentials or raw exports here.
received_date: null # YYYY-MM-DD
period_start: null # YYYY-MM-DD
period_end: null # YYYY-MM-DD
account_scope: [] # Non-secret ledger account names or account IDs.
review_date: null # YYYY-MM-DD
authority: pending # pending | direct-request | standing-delegation
reconciliation_status: not-started # not-started | pending | matched | discrepancy | not-applicable
---

# <Finance Intake Record>

## Source & Scope
- Source reference:
- Covered dates:
- Accounts:
- Private original location:

## Proposed Extraction
- Transactions or payroll components:
- Transfers to match:
- Possible duplicates:
- Unclear classifications:

## Posting & Reconciliation
- Proposed journal change:
- Validation result:
- Reconciliation result:
- Follow-up:

---
$schema: ./accounts-template.schema.json
id: null
status: active # active | closed | archived
account_type: other # bank | credit-card | cash | e-wallet | brokerage | exchange | loan | other
ledger_account: null # hledger account name; do not put an account number here.
institution_label: null # Non-secret display name only.
currencies: [] # ISO or user-defined currency symbols used by this account.
opening_balance_date: null # YYYY-MM-DD
reconciliation_frequency: null # weekly | monthly | quarterly | none
last_reconciled: null # YYYY-MM-DD
journal_path: null # Optional workspace-relative journal path for balances.
---

# <Finance Account>

## Mapping
- Ledger account:
- Account purpose:
- Related journal or rules:
- Opening balance evidence:

## Reconciliation
- Statement or source cadence:
- Last checked balance:
- Outstanding discrepancy:
- Next check:

## Safety
- Do not record full account numbers, credentials, tokens, or raw exports here.

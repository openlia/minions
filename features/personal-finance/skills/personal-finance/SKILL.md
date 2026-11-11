---
name: personal-finance
description: Use hledger and structured finance records to organize, validate, reconcile, and review personal finances.
version: 0.5.0
platforms: [macos, linux]
required_environment_variables: []
required_credential_files: []
workspace_domains:
  - finance
  - finance/intake
  - finance/accounts
  - finance/portfolios
  - finance/reviews
metadata:
  hermes:
    tags: [personal-os, finance, hledger, accounting, investing]
    category: finance
---

# Personal Finance

## When to Use

Use when personal finance information needs to be captured, imported, checked,
reconciled, valued, or analyzed with hledger and the registered finance records.
This includes spending, budgets, payslips, cash flow, debt, account balances,
portfolio holdings, net-worth snapshots, and investment research handoffs.

The normal loop is:

**intake -> extract -> authorize -> post -> validate -> reconcile -> review -> research or decision**

## Authority and Data Boundary

Read `workspace.yaml` and `assistant-policy.yaml` before writing. Resolve the
registered finance paths and their templates rather than inventing a destination.

- Reading, extraction, hledger reports, and proposed changes are read-only.
- A direct request or standing delegation may authorize local finance record
  writes when the target domain and action are allowed.
- The local `record_financial_data` action covers clear local journal postings,
  account mappings, intake status, and reconciliation metadata. It does not
  authorize an external transfer, purchase, trade, broker action, or account
  change.
- If policy is missing, malformed, or does not allow `record_financial_data`,
  ask before changing the journal. Ambiguous account, date, amount, currency,
  duplicate, or classification details remain pending even when delegation is
  available.
- Record the authority used (`direct-request` or `standing-delegation`) in the
  intake record or output. Never silently broaden the authorized batch.

Retained statements, payslips, receipts, screenshots, and exports captured by
durable ingestion live permanently in the Ingestion Vault (`openlia://source/...`) as verifiable evidence outside `/opt/data/workspace`.
Credentials, account numbers, private keys, and tokens remain prohibited.
When posting journal entries, cite the canonical source URI using an hledger comment tag:
```hledger
2026-10-14 * ACME Corp ; source: openlia://source/src_123#ver_001/p1
    expenses:consulting    $500.00
    assets:checking
```
Finance intake records and reviews in `finance/intake/` cite evidence using `[Document Title](openlia://source/{source_id}#{version_id}/p{page})`.
Use [Document Intelligence](openlia://skills/document-intelligence) when capturing new statements, payslips, or password-protected PDFs (`ingestion_capture(..., wait_seconds=15, auto_unlock=True)`) and when inspecting multi-page statements via `page_outline`.
To locate unposted or unreviewed receipts, query `ingestion_search(tags=["finance"], review_status="needs-review")` and inspect structured `custom_fields` (`total_amount`, `currency`, `due_date`, `invoice_number`, `account_hint`) via `ingestion_get_document(source_id=...)`.
Once transactions are posted and validated, mark the source reviewed via `ingestion_update_document(source_id=..., review={"status": "reviewed"})`.

### Amended & Deleted Source Reconciliation

- **Amended / Replaced Statements or Invoices (`new_version_uploaded`)**: When a source document is updated with a new version (`ver_002`) or flagged with `stale_backlinks` in `finance/`, compare the new version's extracted amounts, dates, and line items against existing postings in `finance/journal.hledger` (or yearly includes) citing `; source: openlia://source/{source_id}`. Never silently mutate historical transactions: propose either an explicit adjustment entry or an authorized update of the posting and its version pin (`#ver_002`), then validate with `hledger check` and mark the source `reviewed`.
- **Deleted Source Evidence (`; source-deleted: src_...`)**: When a Vault source is permanently deleted via `ingestion_delete_document`, any existing journal comments are rewritten to `; source-deleted: {source_id}`. If the source was deleted because the upload was a duplicate or error and the transaction itself should be removed or reversed, confirm with the user under `record_financial_data` authority and run `hledger check` after any journal edit.


## Data Model

Keep the hledger journal and any hledger rules files in the runtime workspace,
normally under `/opt/data/workspace/finance/`. Prefer one main journal with
included files only when the journal is large enough to benefit from that
organization. The journal is authoritative for transactions and holdings;
Markdown records are configuration, intake, review, and research context.

### Journal Organization

For a multi-year journal that benefits from smaller editing units, prefer one
main entry point with explicit yearly includes within the registered finance
path. For example:

```text
finance/
  journal.hledger
  2024.hledger
  2025.hledger
  2026.hledger
```

The main journal may contain shared directives followed by:

```hledger
include 2024.hledger
include 2025.hledger
include 2026.hledger
```

Resolve include paths relative to the file containing them. Keep `LEDGER_FILE`
and report commands pointed at the main entry point. Yearly files are parts of
one journal, not independent ledgers; validate and report through the main
journal so prior balances, prices, and shared directives remain available.
For authorized postings, use the appropriate transaction-year file and add its
include when needed within the same authorized scope.

Splitting is an organizational choice, not a token optimization by itself.
Respect existing layouts; do not split solely because a line threshold was
crossed. An approved organization proposal must be handled as a scoped finance
write under this skill's authority rules, not generic workspace cleanup:

- Record the original main entry point, include structure, and proposed paths.
  Do not overwrite existing yearly files or create unregistered folders.
- Establish a baseline with `hledger -f JOURNAL check`, transaction counts,
  and representative scoped balance and transaction reports. If hledger is
  unavailable or validation fails, defer restructuring.
- Move complete transaction blocks by their primary transaction date without
  changing postings, dates, or amounts. Preserve comments, secondary dates,
  prices, balance assertions, and non-transaction directives, including periodic
  and automated rules. Preserve effective directive scope and parsing order;
  defer splitting when year grouping would change either or same-date ordering.
- Do not add annual opening balances or reset accounts merely to split files.
  Keep historical includes available for reports and reconciliation.
- Validate the proposed complete include tree and compare transaction counts
  and the same reports against the baseline before completing the change.
  Inspect the concise diff for missing, duplicated, or unrelated changes. A
  passing `check` alone does not prove equivalence; resolve differences before
  treating the restructuring as complete.

### Accounts and Supporting Records

#### Workspace UI and ledger scopes

The inline view in `finance/overview.md` provides read-only native hledger reports and **New
account** mapping creation. Saving a mapping changes only `finance/accounts/`:
it never creates a journal, adds an `account` directive, posts an opening balance,
or changes an external account. Its template/schema and defaults are observable
before saving. An opening-balance date is evidence metadata, not a posting.

`journal_path` identifies the **main journal / ledger scope**, not a file that
owns the account. For example, `main.journal` can include both
`payslips-company-A.hledger` and `bank-B.hledger`, whose postings reference the
same `assets:bank:B` account. Use one mapping for that scope; identical names in
independent scopes are not automatically combined. Preserve include semantics.

The UI reports whole calendar months, regular actual postings, and one selected
commodity at a time without market/cost conversion. Its Sankey shows credits
through transaction groups to debits: it is accounting posting flow, not inferred
cash-spending allocation. Payroll and statement entries are not automatically
deduplicated. Source data must still follow the transaction/reconciliation rules
below. Unsupported report inputs fail visibly; never invent totals as a fallback.

Use conventional account groups when they fit the person's records:

- `assets:` for cash, banks, savings, brokerages, exchanges, and investments.
- `liabilities:` for credit cards, loans, and other obligations.
- `equity:` for opening balances and other equity entries.
- `income:` for salary, benefits, interest, dividends, and other inflows.
- `expenses:` for spending, fees, taxes, and other outflows.

Account names, currencies, categories, and instrument symbols are user choices.
Do not rename or reclassify existing accounts without explaining the proposal.
Use the registered records as follows:

- `finance/intake/`: one source batch or manual capture through extraction,
  posting, and reconciliation.
- `finance/accounts/`: non-secret account-to-ledger mappings, currencies, and
  reconciliation cadence.
- `finance/portfolios/`: valuation scope, quantities, prices, cost-basis gaps,
  allocation, and performance context.
- `finance/reviews/`: periodic reports with explicit scope and data quality.
- `finance/`: legacy or general finance plans and reviews.

## Procedure

1. **Resolve the workspace.** Read the registry, policy, relevant finance
   template and schema, and any existing records. Use `LEDGER_FILE` when set.
   Otherwise inspect `finance/` for one unambiguous journal. If multiple
   journals are plausible, inspect include directives to distinguish the main
   entry point from its included files; ask if the entry point remains ambiguous.
   Never expose the complete journal unless specifically requested.
2. **Create the journal only for an approved write.** If no journal exists, do
   not create one for a read-only request. When the person explicitly approves
   a specific journal change, create `finance/journal.hledger` in the runtime
   workspace as part of that approved change. Do not ask for a journal path just
   to perform this setup; tell the person which default path you used. Preserve
   any existing file at that path, and ask if it is present but cannot safely be
   identified as the journal.
3. **Establish scope.** Record the reporting currency, date range, included
   accounts, source type, and whether the question concerns transactions,
   balances, cash flow, net worth, or investments. Do not combine currencies
   without dated prices and an explicit conversion method.
4. **Create or update intake.** For a statement, receipt, payslip, screenshot,
   CSV, or conversational entry, use `finance/intake/` when the source needs
   extraction, review, posting, or reconciliation. Preserve the stable source
   reference and mark unknown fields instead of guessing.
5. **Extract and normalize.** Inspect columns or document fields, dates,
   payees, amounts, currencies, account scope, pending status, and source
   identifiers. Preview proposed postings before applying them. Keep a clear
   list of assumptions and unresolved classifications.
6. **Match transfers and duplicates.** Match by source identifier where
   available, otherwise use a reviewed date/payee/amount/account comparison.
   Check bank-to-wallet transfers, cash withdrawals, wallet top-ups, and
   credit-card repayments. Do not import a statement twice.
7. **Authorize the exact local change.** Use `record_financial_data` only for
   the proposed finance batch covered by the direct request or standing policy.
   If the source account, destination account, amount, currency, date, or
   classification is not established, ask a focused clarification. Do not run
   `hledger import`, `hledger add`, or edit a journal merely because a document
   was shared.
8. **Validate before analysis.** Run `hledger -f JOURNAL check`. If it fails,
   report the error and stop financial analysis until the journal is repaired.
   If hledger is unavailable, say that validation could not be performed rather
   than presenting unverified totals as authoritative.
9. **Post and verify.** After an authorized journal change, run `hledger check`
   again, inspect the concise diff or transaction summary, and confirm that no
   unrelated transactions changed. Update intake status and reconciliation
   metadata only within the same authorized scope.
10. **Reconcile.** Compare the relevant ledger account and date range with the
    source statement. Preserve balance assertions when available. Report
    uncleared items, missing periods, pending transactions, and discrepancies;
    do not mark a batch reconciled from a balanced transaction alone.
11. **Review or hand off.** Save a finance review when authorized and useful.
    Send an investment opportunity to Deep Research when external evidence is
    needed, then to Decision Analysis when options and constraints are clear.
    Research and a recommendation never authorize a trade or purchase.

## Transaction Rules

- A bank-to-wallet top-up, bank transfer, cash withdrawal, or brokerage deposit
  is a transfer between asset accounts, not income or spending.
- A credit-card purchase records the expense and the card liability. A later
  card repayment reduces the liability and is not another expense.
- A cash or wallet purchase records spending from that specific source account.
  Do not infer `assets:cash` just because the user says "I spent".
- A salary deposit is one income event. When a payslip is supplied, reconcile
  gross pay, deductions, reimbursements, and net pay to the bank deposit without
  recording the same salary twice.
- Keep payment date and payslip pay-period dates distinct. Unknown deductions
  remain unresolved until their account treatment is established.
- Investment purchases exchange cash for an instrument and fees; they are not
  ordinary consumption. Record instrument identity, units, price, currency,
  fees, account, and transaction date when supported.
- Sales separate proceeds, fees, and realized result when the cost basis is
  known. Dividends, interest, and distributions are investment income when
  supported by the source.
- Existing holdings may be recorded with known quantity and unknown cost basis.
  Do not invent historical cost. Mark the portfolio record as incomplete.

## Reports

Choose reports based on the question rather than presenting every available
number. Every figure must include the journal path, date range, account scope,
currencies, and source command.

### Efficient Journal Access

- Prefer scoped hledger queries over loading the full journal into model
  context. hledger may read the full include tree locally; return only the
  validation result or relevant report to the model.
- Use aggregate reports for broad questions. Bound detailed `register` or
  `print` output by date and account, and narrow or page large results rather
  than returning an unbounded transaction dump. State the scope and any omitted
  detail; do not derive totals from truncated output.
- For edits, duplicate checks, or error diagnosis, locate relevant transactions
  with hledger or local searches, then read complete matching blocks and nearby
  directives. Expand inspection only as necessary; do not repeatedly read the
  whole journal as a default discovery step.
- Run checks and reports against the main entry point, even when editing a
  yearly include. A date-filtered report can still need prior transactions;
  selecting a single yearly file is not equivalent to filtering the main journal.

### Report Selection

- **Spending:** query `expenses:` with `balance` or `register`, bounded by a
  requested period.
- **Income and savings:** use `incomestatement`; explain the sign convention
  before deriving a savings result.
- **Cash and debt:** use `balancesheet` or targeted `balance` queries for
  `assets:` and `liabilities:`.
- **Cash movement:** use `cashflow` and distinguish transfers from income or
  expenses.
- **Reconciliation:** compare the relevant account and date range with the
  source statement and preserve balance assertions.
- **Net worth:** report assets, liabilities, valuation date, prices, and
  currency conversion separately from transaction totals.
- **Portfolio:** separate contributions, historical cost, market value, fees,
  realized result, and unrealized change. Show missing prices or cost basis.

Do not use forecasts, periodic transactions, or budgets as actual historical
results. hledger output is accounting data, not tax, legal, or investment
advice; identify when professional advice or source documentation is needed.

## Investment Research Handoff

Use [Deep Research](openlia://skills/deep-research) for one bounded question,
such as comparing instruments or assessing a market opportunity. Include the
financial context that is already known without exposing the full journal:

- linked goal or decision;
- available amount or contribution constraint, if explicitly provided;
- time horizon, liquidity need, currency, and risk constraints;
- current portfolio exposure and allocation gaps from a dated review;
- fees, taxes, concentration, counterparty, custody, and loss risks to examine;
- freshness requirement, research budget, stopping condition, and what evidence
  would change the conclusion.

After evidence is sufficient, use [Decision Analysis](openlia://skills/decision-analysis)
to compare feasible options. Do not turn a research ranking into a personal
claim, a decision, or a trade. Record the proposed decision in `decisions/`
and keep the person as decision-maker. Record an eventual trade in the journal
only after it has actually happened and the local write is authorized.

## Workflow Handoffs

- **Inbox triage:** explicit financial source material routes to
  `finance/intake/`; investment questions remain research or decision candidates
  unless the source clearly requests finance intake.
- **Daily briefing:** registered finance reviews surface due or recently changed
  reviews; intake records surface blocked, pending-review, or reconciliation
  issues. The briefing does not post transactions.
- **Weekly review:** include finance intake blockers, unreconciled accounts,
  stale portfolio prices, and due finance reviews when assembling open loops.
  Run detailed hledger reports only when the review question needs them.
- **Deep research:** use the investment handoff above for external evidence;
  research never authorizes financial action.
- **Decision analysis:** use after research and current portfolio context are
  sufficient; keep the recommendation separate from the person's choice.

## Pitfalls

- A balanced transaction is not proof that its payee, account, date, or amount
  is correct.
- Do not treat transfers, card repayments, or investment purchases as ordinary
  spending or income.
- Do not hide pending, uncleared, asserted-balance, price, cost-basis, or
  reconciliation discrepancies.
- Do not combine currencies or value investments without explicit prices,
  valuation dates, and a stated conversion method.
- Do not claim a source was preserved if only an extracted reference was retained.
- Do not infer an account, deduction treatment, risk preference, affordability,
  or investment suitability from vague wording.
- Do not send money, place a trade, purchase an asset, or change an external
  financial account as part of this workflow.

## Verification

Confirm that the journal passes `hledger check` before analysis and after every
authorized change; every reported total has a source command and scope; dates,
currencies, and valuation boundaries are visible; source identifiers and
duplicates were checked; finance records conform to their registered schemas;
and no unrelated source files or transactions changed. For a review or
portfolio report, show data gaps, assumptions, and the authority used for any
local write.

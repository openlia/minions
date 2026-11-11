# Personal Finance 0.5

Open [Finance](openlia://workspace/finance/overview.md) for Overview, Flows, Spending, Trends,
and Accounts. Browse review documents in `finance/reviews/` through Documents;
the old manifest-backed Reviews table is removed. Deploy a workspace-ui release supporting `Finance`,
`FinanceOverview`, `FinanceChart`, `FinanceAccounts`, and `SankeyDiagram` before
updating this feature. Runtime hledger must also be installed.

Personal Finance 0.5.0 requires the inline OpenUI runtime in `openlia/openlia#193`.
The view lives in a fenced `openui` block in Markdown. Deploy the compatible
runtime first; no compatible released minimum has been assigned yet, and the
unchanged development version is not a compatibility guarantee. Preserve local
files through the normal feature update/rebase flow, never automatic deletion
of old manifests, UI files, records, or journals.

## Account mappings, not journal mutations

**New account** exposes the installed `finance/accounts/` template/schema before
any save. Fill the display name, ledger account, non-secret institution label,
currencies, status, journal scope, reconciliation fields, and notes. Cancelling
writes nothing. Saving creates one complete Markdown mapping record only.

It does **not** create a journal, declare an hledger account, record an opening
balance, send a payment, or change an external account. Opening-balance dates and
evidence are metadata. Do not put account numbers, credentials, tokens, or raw
statement exports in a mapping.

`journal_path` is the main journal/scope. A main journal can include payroll and
bank files that reference the same account name; these need one mapping, not one
per source file. Names in independent ledgers remain separate. Ledger link states
(linked, not yet present, unverified, or no journal configured) are distinct from
the mapping's active/closed/archived status. Missing ledger evidence is not zero.

No journal is shipped or silently initialized. Select an existing, unambiguous
main journal for reports, or save a mapping with no journal/an intended future
path. Existing files and user customizations must use the normal update/rebase
flow, never unconditional replacement.

## Reports and chart meaning

Reports validate the native journal and preserve its included files. Choose whole
calendar months (inclusive start, exclusive next-month end), an optional literal
account prefix, and exactly one currency/commodity. Values are unvalued quantities,
not market-valued portfolio returns. Exact decimals appear in data tables; chart
coordinates are approximate and may be unavailable for extremely large values.

- Bars compare net income and expenses or expense accounts.
- Lines show historical asset/liability balances, including prior history.
- Pie/donut charts require non-negative spending components; refunds that make a
  component negative require the bar/table view instead.
- Sankey diagrams show **credits → transaction groups → debits**, retaining split
  transactions without inventing payer-to-payee allocations. Transfers are not
  additional income or expenses. A payslip and bank statement are not deduplicated
  merely because both are included.

Transactions with the same directed account set share a posting group, preserving
exact aggregate amounts without implying which source funded each destination.

The initial safe reader supports literal `.journal`/`.hledger` includes within the
Finance folder, resolved relative to each containing file. External paths,
symlinks, globs, non-journal readers, and repeated/cyclic includes are rejected.
Snapshots are bounded to 32 files / 4 MiB, reports to 24 months, and native command
time/output limits. Flow graphs have tighter transaction/graph limits and are
withheld rather than partially displayed when those are exceeded. These are UI
safety limits, not a claim that native hledger lacks those advanced features.

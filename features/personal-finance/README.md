# Personal Finance 0.6

Open [Personal Finance](openlia://minions/personal-finance) for the standalone
app. Canonical journals and supporting documents live in
`minions/personal-finance/data/`; managed contracts live in its `templates/`.
The input form validates and previews a transaction; a separate confirmation
authorizes the exact local posting. Automatic triggers remain off by default.
See the [app documentation](workspace/minions/personal-finance/README.md) for
setup, structured entry, and configuration. The
[Finance document view](openlia://workspace/minions/personal-finance/overview.md)
also provides ledger reports and account mappings. Browse review documents in
`minions/personal-finance/data/reviews/` through Documents.

Runtime hledger and Finance `dataPath` support are required. No compatible
released runtime minimum has been assigned yet; the unchanged development
version is not a compatibility guarantee. Preserve records, configuration, and
local customizations through the normal managed update/rebase flow.

## Account mappings, not journal mutations

**New account** exposes the installed app's `templates/accounts/` contract before
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

---
name: Personal Finance
description: Native hledger reports and explicitly confirmed local transaction entry.
icon: wallet
---

# Personal Finance

Open [Personal Finance](openlia://minions/personal-finance). The authoritative
journal and supporting Markdown records live in `data/`. Reports never initialize
a journal. There is no external banking, payment, trading, or account access.

## Setup

Install Dependencies once (PyYAML and jsonschema), ensure native `hledger` is on
the server PATH, and save Configuration. `journal` is relative to `data/` and
identifies the main entry point, including its existing literal relative includes.
Structured posting supports portable ASCII journal paths (letters, digits,
underscores, dashes, dots, and directory separators); advanced include layouts
are left untouched and require the Finance skill rather than silent conversion.
Automatic triggers default off; there is no cron default. Manual Refresh reads
records only. Reports require the companion runtime's Finance `dataPath` support.
For early development, `requires.openlia` is intentionally unset: use a tested
runtime/catalog commit pair. This provides no minimum-version guard or compatibility
guarantee; no release bump or production catalog pin change is needed for a preview.

## Structured input

Submit a date, description, positive decimal amount, commodity, and explicit debit
and credit accounts. Transfers use two asset accounts; card repayments reduce
liabilities rather than creating another expense. Split transactions, investments,
and ambiguous classifications remain workflows for the Finance skill.

Submission creates a pending proposal only. Open Dashboard, find the review card
for that exact proposal ID, inspect its posting and main journal, explicitly choose
**Confirm posting**, and type `POST`. Review cards appear before ledger reports.
Each card has independent form state; its proposal ID is prefilled, never inferred
from another card. Choosing **Cancel proposal** with blank confirmation never posts.
Only that second submission authorizes a local ledger write. Native hledger checks
the baseline and proposed complete include tree. A changed journal requires a new
preview. Repeated confirmations cannot post twice. Cancelling never changes the
journal. A balanced posting is not proof of correct classification or reconciliation.

Amounts stay decimal strings. Each posting retains its proposal ID and supplied
source URI. No currencies are converted or combined. Unsupported/missing ledger
evidence is not presented as zero. Personal data appears only after user input.

## Records, skills, and upgrades

Browse `data/intake`, `data/accounts`, `data/portfolios`, and `data/reviews` in
Documents; use [Personal Finance](openlia://skills/personal-finance) for advanced
bookkeeping. Portable contracts live in `templates/`. Do not export `data/` or
`config.json` as app source. Managed code updates must preserve both, including
pending proposals.

## Tests

Run `python3 -B -m unittest discover -s tests` from this directory. Tests use
temporary synthetic workspaces; native accounting tests require `hledger`.

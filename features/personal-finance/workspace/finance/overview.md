---
$schema: ./finance-template.schema.json
period: null
review_date: null
journal_path: null
---

# Personal Finance

## Journal & Data Scope

Reports read an existing, unambiguous main journal and its supported includes.
No journal is shipped or silently initialized. Native hledger must be installed
on the Workspace UI server.

```openui
root = Finance([views])
views = Tabs([
  TabItem("overview", "Overview", [FinanceOverview(), FinanceChart("income-expenses", "bar")]),
  TabItem("flows", "Flows", [FinanceChart("flows", "sankey")]),
  TabItem("spending", "Spending", [FinanceChart("spending", "bar"), FinanceChart("spending", "pie")]),
  TabItem("trends", "Trends", [FinanceChart("balances", "line")]),
  TabItem("accounts", "Accounts", [FinanceAccounts()])
])
```

## Spending Summary & Targets

Select whole calendar months and one currency/commodity. Missing journal evidence
is not zero; reports fail visibly rather than inventing totals.

## Accounts & Net Assets (Non-Secret)

**New account** creates a Markdown mapping under `accounts/` only. It never
creates journals, posts opening balances, or modifies external accounts.

## Portfolio & Valuation Notes

Charts show unvalued ledger quantities, not market-valued portfolio returns.
Keep valuation scope and price evidence in the `portfolios/` records.

## Active Financial Goals

Record goals in the relevant workspace documents; this overview does not infer
targets from ledger balances.

## Recurring Subscriptions & Audits

Keep periodic review documents in `reviews/`, using the
[review template](./reviews/reviews-template.md). Browse them in Documents;
the former manifest-backed Reviews table is no longer supported.

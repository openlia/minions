# Shopping

Install `shopping` to add purchase candidates, budgets, observed prices, and
comparisons under `shopping/`. Keep source URLs, observation dates, and currencies
explicit; never treat missing prices as zero or combine currencies silently.

Use inline OpenUI in comparison reports when useful. A price-watch Minion can
add executable tracking, but purchases remain separately approval-gated. This
package no longer ships the unsupported Mini-Project board. See the
[migration guide](../../docs/minions.md).

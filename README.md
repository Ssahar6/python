# Python

| Script | What it does | Run on | Result |
|---|---|---|---|
| `prepare_ads.py` | Cleans the two raw Meta Ads exports: maps Hebrew columns to snake_case, tags the account, converts numbers and reports any failure, derives `leads` only for lead objectives, removes line breaks inside ad names that broke the BigQuery load | the private raw exports | 92,028 rows · 595 active · ₪39,486.56 · 1,923 leads — all asserted |
| `retrospective_audit.py` | Standard-library aggregation of the cleaned file: spend by objective, month and lead mechanism, weighted funnel rates, and the exact log decomposition of month-to-month CPL changes | the cleaned export | baseline assertions pass; its figures were later reproduced in BigQuery (`sql/validation/`) |
| `check_aggregate_consistency.py` | Cross-checks the earlier summaries against each other before trusting them: totals add up, rates equal sum ÷ sum, decompositions reconcile | earlier aggregate outputs | 283 of 284 checks pass; one ₪0.01 rounding difference, resolved by BigQuery |

The raw exports and intermediate files are not included: they are the private source data.
All three scripts use only aggregate business data — no customer information.

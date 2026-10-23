# Methodology — How the Project Was Built, Step by Step

[← Back to project overview](README.md)

Each step lists what was done, why, and how it was checked. Code was written with AI tools; I
supplied the business context and data, defined the questions, ran the queries in BigQuery and
interpreted the results.

| # | Step | What was done | Check | Output |
|---|---|---|---|---|
| 1 | **Questions** | Defined three business questions from my own experience: why leads got more expensive, why few leads became customers, and whether problems could be seen earlier | — | [README](README.md) |
| 2 | **Export** | Downloaded daily, ad-level reports from two Meta Ads accounts | — | private raw files |
| 3 | **Clean** | Mapped Hebrew column names to English, converted numbers, removed line breaks in ad names, kept leads only for lead objectives | totals asserted: 92,028 rows · ₪39,486.56 · 1,923 leads | `prepare_ads.py` |
| 4 | **Load** | Loaded the cleaned file to BigQuery (`ads_daily_raw`) and built one clean VIEW (`v_ads_daily`) used by every query | VIEW returns exactly the raw table's totals | SQL section 1 |
| 5 | **Validate** | Reproduced the earlier Python figures in BigQuery before any analysis. Found that 99% of rows were zero-spend padding, so only days with spend count as activity | reconciliation queries all pass · 283 of 284 Python cross-checks pass (one ₪0.01 rounding gap) | SQL section 2 · `check_aggregate_consistency.py` |
| 6 | **Context** | Wrote down what I remembered doing, separately from the data; classified each campaign's purpose; assigned ₪2,006 of spend with no recorded objective using the same ad's objective on other days | month rules match ad-level evidence for all but ₪84 | SQL query A5 |
| 7 | **Analyse ads** | Marketing metrics by lead type, CPL decomposition, same-day comparison of lead types, monthly tracking share, alert backtest | every rate = sum ÷ sum | SQL queries M1, D1, A1–A4 · [Case Studies 1 and 3](case-studies/) |
| 8 | **Add payments** | Replaced customer names with anonymous IDs, removed notes, removed credit notes together with the receipts they cancelled | 50 payments · 38 customers · ₪142,234 · none outside the periods | `prepare_payments.py` · `check_payments.py` · SQL R0–R2 · [Case Study 2](case-studies/02-the-missing-link-between-leads-and-sales.md) |
| 9 | **Dashboard** | Built a Looker Studio dashboard on SQL data sources, so the business logic lives in SQL | uses the same VIEW as every query | [dashboard](https://datastudio.google.com/reporting/517f4b3d-41fb-49b6-b738-0b5f93a7f9a8) · SQL section 5 |
| 10 | **Communicate** | Presentation for a business reader, a short story document, three case studies with charts | charts recomputed from the data and checked against BigQuery before drawing | [presentation](The_Data_I_Had.pdf) · `make_case_study_charts.py` |
| 11 | **Review** | An external review was applied: wording made non-causal, a hypothetical "break-even" reframed as gross payments vs ad spend, customer count reconciled | changes logged below | this page |

## Key decisions

| Decision | Reason |
|---|---|
| Count only days with spend | 99% of exported rows were empty padding |
| Never average daily rates | weighted rates (sum ÷ sum) avoid giving small days too much weight |
| Never add results of different campaign objectives | leads, clicks and views are not the same outcome |
| Use 38 customers, not 46 | an earlier business record of 46 students could not be reconciled with the payment data |
| No CAC, ROAS or profit | no payment is linked to the ad or channel that brought the customer |
| Describe the CPL split as arithmetic | an exact identity shows where a change sits, not why it happened |
| Call the alert a retrospective backtest | it was tested only on past data, with one chosen threshold |

## How to reproduce

1. Run `prepare_ads.py` on the two Meta exports; load the output to BigQuery as `ads_daily_raw`.
2. Run the SQL file top to bottom: the VIEW, the baseline check, then the analyses.
3. Run `prepare_payments.py` and `check_payments.py`; load the output as `student_payments`; run R0–R2.
4. Run `make_case_study_charts.py` to redraw the charts; it stops if any figure differs from the
   verified results.

The raw exports are private, so steps 1 and 3 need the original files.

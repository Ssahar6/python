# The Data I Had, But Didn't Know How to Use

**A Data Analyst portfolio project on my own business's real data** · Sun Sahar

I ran a small trading-education business. Meta ads brought plenty of leads, but costs rose and
too few leads became paying customers. At the time I judged everything by lead count and cost per
lead. In this project I went back to the data to find out what it could have told me, and what
it never could.

| | |
|---|---|
| 📊 Presentation | [`The_Data_I_Had.pdf`](The_Data_I_Had.pdf): 9 slides plus a 2-slide appendix |
| 📈 Live dashboard | [Looker Studio](https://datastudio.google.com/reporting/517f4b3d-41fb-49b6-b738-0b5f93a7f9a8) (Meta Ads analysis) |
| 🧮 SQL | [`The_Data_I_Had_SQL.sql`](The_Data_I_Had_SQL.sql): every query, each with question, method and result |
| 🐍 Python | cleaning, anonymisation and check scripts in this repository |

## Data and tools

- **Meta Ads daily exports**, 2 ad accounts, Jun 2024 – Jan 2026: ₪39,487 spend, 1,923 Meta-attributed leads.
  The export held 92,028 rows, but 99% were zero-spend padding; only the 595 ad-days with spend are activity.
- **Student payments**: 50 payments by 38 customers, ₪142,234 excl. VAT. Names were replaced by anonymous IDs.
- **CRM snapshot**: 130 leads, used as aggregate counts only.
- **Tools**: Python (cleaning and checks) → BigQuery SQL (CTEs, window functions) → Looker Studio → slide deck.

## Three findings

1. **Most of the cost-per-lead rise happened before the click.** From February to June 2025 the
   cost per lead doubled (₪8.78 → ₪17.74). Impressions cost 65% more and the click rate fell 29%,
   while the share of clicks becoming leads rose 14%. This is an exact arithmetic split, not proof of cause.
2. **The journey after the lead was barely measured.** In a 130-lead CRM snapshot only 3 leads (2.3%)
   had a meeting scheduled. It is a single snapshot, but leads were counted precisely while calls,
   meetings and sales were not.
3. **Payments were 2.5× higher per month while the lead campaigns ran.** The comparison is ₪11,996 a month
   against ₪4,795 before. But sales were already coming in before the ads, and no payment is linked to
   the channel that brought the customer. The timing fits; the cause is unproven.

## Decisions they support

- Tag every lead and customer with its source, and record each step: called, meeting scheduled,
  held, sale. This makes cost per sale measurable.
- Steer by **cost per scheduled meeting**, not cost per lead. In the what-if plan, the meeting rate
  moves the result more than ad prices do.
- Give every creative a unique name, and use a daily cost-per-lead check. A back-tested rule would
  have flagged the March 2025 rise about a month before the monthly report.

## Limitations

- No payment is linked to an ad, so there is **no CAC, ROAS or profit** figure. Payments are gross,
  counted when received.
- The meeting rate comes from one CRM snapshot. The what-if plan is a scenario, not a forecast.
- The alert rule was tested only on past data, and its 30% threshold was chosen, not optimised.
- Many creatives ran under one ad name, so individual creatives cannot be compared.

## Files in this repository

| File | What it does |
|---|---|
| `The_Data_I_Had.pdf` | the presentation |
| `The_Data_I_Had_SQL.sql` | all BigQuery queries, in story order |
| `prepare_ads.py` | cleans the two Meta Ads exports and checks the totals (92,028 rows, ₪39,486.56, 1,923 leads) |
| `retrospective_audit.py` | sums spend and leads by objective, month and lead type; splits cost-per-lead changes |
| `check_aggregate_consistency.py` | cross-checks the earlier summaries: 283 of 284 checks pass, one ₪0.01 rounding gap |
| `prepare_payments.py` | turns the receipts export into an anonymous payments file: names become IDs, notes removed |
| `check_payments.py` | checks the payments file: 50 payments, 38 customers, ₪142,234, none outside the analysed periods |

## How it was built

This project was built with **AI-assisted development**. AI tools wrote the SQL and Python. I
supplied the business context and the data, defined and refined the questions, ran the queries in
BigQuery, built the dashboard, challenged results that did not match the business, and interpreted
the findings.

## Privacy

No customer names, contact details or identifiable payment records are in this repository. The raw
exports are private. The SQL runs against the private BigQuery dataset `bqproj26.meta_ads`.

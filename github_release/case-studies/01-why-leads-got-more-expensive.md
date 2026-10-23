# Case Study 1 — Why Did My Leads Get More Expensive?

[← Back to project overview](../README.md)

> **In one sentence:** between February and June 2025 my cost per lead doubled, and most of that
> increase sat *before* the click — showing the ads got more expensive and fewer people clicked —
> while the share of clickers who signed up actually rose.

## 1. Business problem

In 2025 I ran a free-course lead campaign on Meta (Instagram and Facebook) using Meta's built-in
sign-up form ("Instant Form"). Cost per lead went from **₪8.78 in February to ₪17.74 in June**.
At the time I suspected the form and the offer. The question: **which step of the funnel actually
changed?**

## 2. Relevant data and KPIs

Meta Ads daily export, Instant Form campaign only, days with spend only.

| KPI | Definition | Feb 2025 | Jun 2025 | Actual change |
|---|---|---:|---:|---:|
| CPM | spend ÷ impressions × 1,000 (price of showing the ad) | ₪36.68 | ₪60.49 | **+65%** |
| CTR | link clicks ÷ impressions (share of viewers who clicked) | 0.99% | 0.71% | **−28%** |
| Click-to-lead rate (CVR) | leads ÷ link clicks (share of clickers who signed up) | 42.1% | 48.1% | **+14%** |
| CPL | spend ÷ Meta-attributed leads | ₪8.78 | ₪17.74 | **+102%** |

All rates are weighted: totals divided by totals, never an average of daily rates.

## 3. Analytical approach

Cost per lead can be written as a product of the three funnel steps:

```
CPL = (CPM ÷ 1,000) ÷ CTR ÷ CVR
```

Taking logarithms turns this product into a sum, so the change in CPL splits **exactly** into three
parts that add up to 100%:

```
ln(CPL Jun / CPL Feb) = ln(CPM ratio) − ln(CTR ratio) − ln(CVR ratio)
        0.704         =     0.500     +     0.335     −     0.132
```

Each part divided by the total gives its **share of the increase**.

## 4. Key findings

| Funnel step | Actual change in the metric | Share of the CPL increase |
|---|---:|---:|
| Ads cost more to show (CPM) | +65% | **71%** |
| Fewer people clicked (CTR) | −28% | **48%** |
| More clickers signed up (CVR) | +14% | **−19%** (pulled cost *down*) |
| **Total** | CPL +102% | **100%** |

- **Most of the increase happened before the click.** The price of showing the ad and the click rate
  together account for more than the whole increase.
- **The sign-up step was not the problem.** A larger share of clickers became leads in June than in
  February, which partly offset the rise.
- The two columns measure different things: the first is how much each metric moved; the second is
  how much of the CPL increase that movement explains.

## 5. Supporting visualization

![Share of the cost-per-lead increase by funnel step](../images/cs1_cpl_decomposition.svg)

## 6. Business implications and proposed decisions

This analysis shows **where to investigate**, not why it happened. Creative fatigue, audience
saturation and higher auction competition could each raise CPM and lower CTR; this data cannot
separate them.

- Investigate the steps before the click first: creative refresh and audience tests, rather than
  rebuilding the form.
- Track CPM and CTR weekly alongside CPL, so a rise can be traced to its step as it happens.
- Give every creative a unique name, so future tests can show which creative drove a change.

## 7. Limitations

- **Arithmetic, not causation.** The split is an exact identity; it does not prove what caused each
  metric to move.
- **Two endpoints.** February and June were compared directly. CPL did not rise in a straight line
  (Feb ₪8.78, Mar ₪17.76, Apr ₪12.72, May ₪16.51, Jun ₪17.74).
- **One ad name.** The whole campaign was recorded under a single ad name although several creatives
  ran, so individual creatives cannot be compared.
- **Meta-attributed leads.** Leads are counted by Meta's attribution, not as verified unique people.

## 8. Relevant SQL

**Query D1** in [`The_Data_I_Had_SQL.sql`](../The_Data_I_Had_SQL.sql#L116-L159) — BigQuery.

*What it does in plain English:* sums spend, impressions, clicks and leads for the Instant Form
campaign in February and in June 2025, turns them into CPM, CTR, CVR and CPL, and splits the CPL
change into the three shares using logarithms.

```sql
WITH months AS (
  SELECT
    month,
    SAFE_DIVIDE(SUM(spend_ils) * 1000, SUM(impressions)) AS cpm,
    SAFE_DIVIDE(SUM(link_clicks), SUM(impressions))      AS ctr,
    SAFE_DIVIDE(SUM(leads), SUM(link_clicks))            AS cvr,
    SAFE_DIVIDE(SUM(spend_ils), SUM(leads))              AS cpl
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
    AND objective = 'actions:leadgen.other'          -- Instant Form campaign
    AND month IN (DATE '2025-02-01', DATE '2025-06-01')
  GROUP BY month
),
feb AS (SELECT * FROM months WHERE month = DATE '2025-02-01'),
jun AS (SELECT * FROM months WHERE month = DATE '2025-06-01')
SELECT
  ROUND(feb.cpl, 2) AS feb_cpl_ils,
  ROUND(jun.cpl, 2) AS jun_cpl_ils,
  ROUND(100 *  LN(jun.cpm / feb.cpm) / LN(jun.cpl / feb.cpl)) AS share_from_cpm_pct,
  ROUND(100 * -LN(jun.ctr / feb.ctr) / LN(jun.cpl / feb.cpl)) AS share_from_ctr_pct,
  ROUND(100 * -LN(jun.cvr / feb.cvr) / LN(jun.cpl / feb.cpl)) AS share_from_cvr_pct
FROM feb
CROSS JOIN jun;
```

The chart is drawn by [`make_case_study_charts.py`](../make_case_study_charts.py), which recomputes
these figures from the same export and checks them against the BigQuery results before drawing.

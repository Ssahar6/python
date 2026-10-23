-- =====================================================================================
-- The Data I Had, But Didn't Know How to Use — SQL
-- Sun Sahar · Data Analyst portfolio project · BigQuery (GoogleSQL)
-- =====================================================================================
-- A retrospective analysis of my own business's Meta Ads data (Jun 2024 – Jan 2026),
-- together with the students' payments (Jun 2024 – Mar 2026).
-- Dashboard: https://datastudio.google.com/reporting/517f4b3d-41fb-49b6-b738-0b5f93a7f9a8
-- Python:    https://github.com/Ssahar6/python (cleaning and checks)
--
-- Tables (dataset bqproj26.meta_ads)
--   ads_daily_raw     Meta daily export after Python cleaning, one row per ad per day
--                     (92,028 rows). The export is a full ad × day grid, so 99% of rows
--                     are zero-spend padding; only spend > 0 (is_active) marks activity.
--   v_ads_daily       the clean VIEW used by every ads query below
--   student_payments  one row per payment received for the training and mentorship
--                     programme (50 payments by 38 customers, ₪142,234 excl. VAT), dated
--                     when paid (cash basis). Anonymous: customer IDs only. Credit notes
--                     were removed together with the receipts they cancelled.
--
-- Built with AI-assisted coding: I supplied the business context, defined and refined the
-- questions, ran every query in BigQuery and interpreted the results; AI tools wrote the code.
--
-- Rules: every rate is weighted — SUM(numerator) ÷ SUM(denominator), never an average of
-- daily rates. Results of different campaign objectives are never added together.
--
-- CONTENTS
--   1. Data layer      v_ads_daily
--   2. Baseline        the totals every analysis starts from
--   3. Ads
--      M1  Marketing metrics by lead mechanism
--      D1  Why cost per lead doubled (Feb → Jun 2025)
--      A1  Instant Form vs landing page on the same days
--      A4  Monthly share of spend that tracked leads
--      A5  Spend with no recorded objective
--      A3  Can creatives be compared?
--      A2  Back-test of a daily cost-per-lead alert
--   4. Money
--      R0  Reconciliation of the payments table
--      R1  Payments and ad spend before, during and after the lead campaigns
--      R2  Media-spend coverage: how many average customers' payments equal ad spend?
--   5. Dashboard       DS1 data source for Looker Studio
-- =====================================================================================


-- =====================================================================================
-- 1. DATA LAYER · v_ads_daily (the VIEW, shown as its SELECT)
-- One row per ad per day. leads is filled only for the two lead objectives, so SUM(leads)
-- never mixes result types. Meta's per-row ratio columns are dropped on purpose.
-- =====================================================================================
SELECT
  account,
  ad_name,
  CONCAT(account, ' | ', ad_name)         AS ad_key,
  date_start                              AS day,
  DATE_TRUNC(date_start, MONTH)           AS month,
  spend_ils > 0                           AS is_active,
  COALESCE(result_indicator, '(unknown)') AS objective,
  CASE
    WHEN result_indicator IN ('actions:leadgen.other',
                              'actions:offsite_conversion.fb_pixel_lead') THEN 'lead'
  END                                     AS objective_family,
  CASE
    WHEN result_indicator IN ('actions:leadgen.other',
                              'actions:offsite_conversion.fb_pixel_lead') THEN results
  END                                     AS leads,
  spend_ils, impressions, reach, link_clicks, clicks_all, landing_page_views, results
FROM `bqproj26.meta_ads.ads_daily_raw`;


-- =====================================================================================
-- 2. BASELINE · The totals every analysis starts from
-- These matched the earlier Python figures exactly before any analysis began.
-- Result: 92,028 rows · 595 active ad-days · ₪39,486.56 · 1,923 leads · 259 days with
--         spend · 15 months with spend · 3 Jun 2024 – 24 Jan 2026.
-- =====================================================================================
SELECT
  COUNT(*)                                    AS all_rows,
  COUNTIF(is_active)                          AS active_ad_days,
  ROUND(SUM(spend_ils), 2)                    AS spend_ils,
  SUM(leads)                                  AS leads,
  COUNT(DISTINCT IF(is_active, day, NULL))    AS days_with_spend,
  COUNT(DISTINCT IF(is_active, month, NULL))  AS months_with_spend,
  MIN(IF(is_active, day, NULL))               AS first_day,
  MAX(IF(is_active, day, NULL))               AS last_day
FROM `bqproj26.meta_ads.v_ads_daily`;


-- =====================================================================================
-- 3a. M1 · Marketing metrics by lead mechanism
-- Result: Instant Form CPM 48.84 · CTR 0.80% · CPC 6.08 · click→lead 43.2% · CPL 14.07
--         Landing page CPM 69.46 · CTR 0.94% · CPC 7.39 · 714 page views of 755 clicks ·
--         CPL 24.16. (The Instant Form has no landing page, so its page views are empty.)
-- =====================================================================================
SELECT
  CASE objective
    WHEN 'actions:leadgen.other' THEN 'Instant Form'
    ELSE 'Landing page'
  END                                                 AS mechanism,
  ROUND(SUM(spend_ils), 2)                            AS spend_ils,
  SUM(impressions)                                    AS impressions,
  SUM(link_clicks)                                    AS link_clicks,
  SUM(landing_page_views)                             AS landing_page_views,
  SUM(leads)                                          AS leads,
  ROUND(SAFE_DIVIDE(SUM(spend_ils) * 1000, SUM(impressions)), 2)  AS cpm_ils,
  ROUND(SAFE_DIVIDE(SUM(link_clicks) * 100, SUM(impressions)), 2) AS ctr_pct,
  ROUND(SAFE_DIVIDE(SUM(spend_ils), SUM(link_clicks)), 2)         AS cpc_ils,
  ROUND(SAFE_DIVIDE(SUM(leads) * 100, SUM(link_clicks)), 1)       AS click_to_lead_pct,
  ROUND(SAFE_DIVIDE(SUM(spend_ils), SUM(leads)), 2)               AS cpl_ils
FROM `bqproj26.meta_ads.v_ads_daily`
WHERE is_active
  AND objective_family = 'lead'   -- only the two lead objectives; others are never mixed in
GROUP BY mechanism
ORDER BY mechanism;


-- =====================================================================================
-- 3b. D1 · Which part of the funnel moved when cost per lead doubled? (Instant Form,
--     February vs June 2025)
-- Cost per lead = (CPM / 1000) ÷ CTR ÷ click-to-lead rate. Taking logarithms turns this
-- product into a sum, so the log change in CPL splits exactly into three shares that add
-- up to 100%. The shares are contributions to the LOG change, not the % change of each
-- metric (those are the *_change_pct columns). Arithmetic only: it shows where the change
-- sits, not why it happened.
-- Result: CPL ₪8.78 → ₪17.74. CPM +65%, CTR −28%, click-to-lead +14%.
--         Shares of the log change: CPM 71%, CTR 48%, click-to-lead −19%.
-- =====================================================================================
WITH months AS (
  SELECT
    month,
    SAFE_DIVIDE(SUM(spend_ils) * 1000, SUM(impressions)) AS cpm,
    SAFE_DIVIDE(SUM(link_clicks), SUM(impressions))      AS ctr,
    SAFE_DIVIDE(SUM(leads), SUM(link_clicks))            AS cvr,
    SAFE_DIVIDE(SUM(spend_ils), SUM(leads))              AS cpl
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
    AND objective = 'actions:leadgen.other'
    AND month IN (DATE '2025-02-01', DATE '2025-06-01')
  GROUP BY month
),
feb AS (SELECT * FROM months WHERE month = DATE '2025-02-01'),
jun AS (SELECT * FROM months WHERE month = DATE '2025-06-01')
SELECT
  ROUND(feb.cpl, 2)                                           AS feb_cpl_ils,
  ROUND(jun.cpl, 2)                                           AS jun_cpl_ils,
  ROUND(feb.cpm, 2)                                           AS feb_cpm_ils,
  ROUND(jun.cpm, 2)                                           AS jun_cpm_ils,
  ROUND(100 * feb.ctr, 2)                                     AS feb_ctr_pct,
  ROUND(100 * jun.ctr, 2)                                     AS jun_ctr_pct,
  ROUND(100 * feb.cvr, 1)                                     AS feb_click_to_lead_pct,
  ROUND(100 * jun.cvr, 1)                                     AS jun_click_to_lead_pct,
  ROUND(100 * (jun.cpm / feb.cpm - 1))                        AS cpm_change_pct,
  ROUND(100 * (jun.ctr / feb.ctr - 1))                        AS ctr_change_pct,
  ROUND(100 * (jun.cvr / feb.cvr - 1))                        AS click_to_lead_change_pct,
  ROUND(100 *  LN(jun.cpm / feb.cpm) / LN(jun.cpl / feb.cpl)) AS share_from_cpm_pct,
  ROUND(100 * -LN(jun.ctr / feb.ctr) / LN(jun.cpl / feb.cpl)) AS share_from_ctr_pct,
  ROUND(100 * -LN(jun.cvr / feb.cvr) / LN(jun.cpl / feb.cpl)) AS share_from_cvr_pct
FROM feb
CROSS JOIN jun;


-- =====================================================================================
-- 3c. A1 · Instant Form vs landing page on the days both ran
-- Step 1: one row per mechanism per day. Step 2: keep only the days on which both ran.
-- Result: 22–30 Jul 2025 — CPL ₪10.25 vs ₪24.54 (2.4×).
-- Not an A/B test: different accounts, audiences and offers (free-course signup vs a
-- request for a personal fit meeting).
-- =====================================================================================
WITH lead_days AS (
  SELECT
    day,
    CASE objective
      WHEN 'actions:leadgen.other' THEN 'Instant Form'
      ELSE 'Landing page'
    END              AS mechanism,
    SUM(spend_ils)   AS spend_ils,
    SUM(impressions) AS impressions,
    SUM(link_clicks) AS link_clicks,
    SUM(leads)       AS leads
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
    AND objective_family = 'lead'
  GROUP BY day, mechanism
),
both_days AS (
  SELECT day
  FROM lead_days
  GROUP BY day
  HAVING COUNT(*) = 2
)
SELECT
  mechanism,
  MIN(day)                                            AS first_day,
  MAX(day)                                            AS last_day,
  COUNT(*)                                            AS days,
  ROUND(SUM(spend_ils), 2)                            AS spend_ils,
  SUM(leads)                                          AS leads,
  ROUND(SUM(link_clicks) * 100 / SUM(impressions), 2) AS ctr_pct,
  ROUND(SUM(leads) * 100 / SUM(link_clicks), 1)       AS click_to_lead_pct,
  ROUND(SUM(spend_ils) / SUM(leads), 2)               AS cpl_ils
FROM lead_days
JOIN both_days USING (day)
GROUP BY mechanism
ORDER BY mechanism;


-- =====================================================================================
-- 3d. A4 · How much of each month's spend ran on an objective that tracked leads?
-- Result: lead tracking only Feb–Aug 2025; 0% in every other month; 74.4% overall.
-- =====================================================================================
SELECT
  FORMAT_DATE('%Y-%m', month)                                AS year_month,
  ROUND(SUM(spend_ils), 2)                                   AS total_spend_ils,
  ROUND(SUM(IF(objective_family = 'lead', spend_ils, 0)), 2) AS lead_objective_ils,
  ROUND(SUM(IF(objective = '(unknown)', spend_ils, 0)), 2)   AS no_objective_ils,
  ROUND(100 * SUM(IF(objective_family = 'lead', spend_ils, 0))
            / SUM(spend_ils), 1)                             AS pct_lead_tracked,
  COALESCE(SUM(leads), 0)                                    AS leads
FROM `bqproj26.meta_ads.v_ads_daily`
WHERE is_active
GROUP BY month
ORDER BY month;


-- =====================================================================================
-- 3e. A5 · Which ads make up the ₪2,006 with no objective recorded?
-- Each such ad is matched with the objective the same ad had on its other days.
-- Result: 25 ads; `results` is empty on every row — Meta leaves the objective blank on
-- days an ad records no result. The other-day objective shows each ad's purpose.
-- Used to check the DS1 classification: the ad-level evidence agrees with DS1's rules for
-- all but ₪84 of the ₪2,006: ₪81.82 of a 2025 lead ad re-used in January 2026 (DS1 calls
-- it Exposure, following the owner's account of that month) and ₪2.24 of profile-visit
-- ads in Oct–Dec 2025 that DS1 files under Messages / Webinar funnel. Both are immaterial.
-- =====================================================================================
WITH no_objective AS (
  SELECT ad_key, account, ad_name, day, spend_ils
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
    AND objective = '(unknown)'
),
other_days AS (
  SELECT ad_key, STRING_AGG(DISTINCT objective, ', ') AS objective_on_other_days
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
    AND objective != '(unknown)'
  GROUP BY ad_key
)
SELECT
  n.account,
  n.ad_name,
  MIN(n.day)                 AS first_day,
  MAX(n.day)                 AS last_day,
  COUNT(*)                   AS days,
  ROUND(SUM(n.spend_ils), 2) AS spend_ils,
  o.objective_on_other_days
FROM no_objective AS n
LEFT JOIN other_days AS o USING (ad_key)
GROUP BY n.account, n.ad_name, o.objective_on_other_days
ORDER BY first_day;


-- =====================================================================================
-- 3f. A3 · Can the Instant Form creatives be compared?
-- Result: one row — the whole campaign (111 days, ₪23,801.05, 1,692 leads) is recorded
-- under one ad name, although many different creatives ran. The data cannot separate
-- them: a naming and tracking finding, not a performance one.
-- =====================================================================================
SELECT
  account,
  ad_name,
  MIN(day)                              AS first_day,
  MAX(day)                              AS last_day,
  COUNT(DISTINCT day)                   AS days,
  ROUND(SUM(spend_ils), 2)              AS spend_ils,
  SUM(leads)                            AS leads,
  ROUND(SUM(spend_ils) / SUM(leads), 2) AS cpl_ils
FROM `bqproj26.meta_ads.v_ads_daily`
WHERE is_active
  AND objective = 'actions:leadgen.other'
GROUP BY account, ad_name
ORDER BY spend_ils DESC;


-- =====================================================================================
-- 3g. A2 · Back-test of a daily cost-per-lead alert (Instant Form)
-- A retrospective test on past data. Rule: alert when the cost per lead of the last 7
-- active days is more than 30% above the cost per lead of all EARLIER active days (only
-- once there are 7 days in the window and at least 100 earlier leads). Each day is
-- compared only with data that existed before it. The 30% threshold is a chosen rule, not
-- an optimised or proven one; an alert means "investigate", not "pause the campaign".
-- How it would perform on future data has not been tested.
-- Result (33 rows): an alert on every active day from 1 Mar to 4 Apr 2025 (27 days,
-- ₪8,873.80 spent, 512 leads at ₪17.33), starting about a month before a monthly report
-- for March could show the rise. After that, four short episodes of 1–2 active days in
-- late May / early June (6 rows).
-- =====================================================================================
WITH daily AS (
  SELECT day, SUM(spend_ils) AS spend, SUM(leads) AS leads
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
    AND objective = 'actions:leadgen.other'
  GROUP BY day
),
rolling AS (
  SELECT
    day,
    spend,
    leads,
    COUNT(*)   OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)         AS days_in_window,
    SUM(spend) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)         AS spend_7,
    SUM(leads) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)         AS leads_7,
    SUM(spend) OVER (ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND 7 PRECEDING) AS spend_before,
    SUM(leads) OVER (ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND 7 PRECEDING) AS leads_before
  FROM daily
)
SELECT
  day,
  ROUND(SAFE_DIVIDE(spend_7, leads_7), 2)           AS cpl_last_7_days,
  ROUND(SAFE_DIVIDE(spend_before, leads_before), 2) AS cpl_before,
  ROUND(spend, 2)                                   AS spend_that_day,
  leads                                             AS leads_that_day
FROM rolling
WHERE days_in_window = 7
  AND leads_before >= 100
  AND SAFE_DIVIDE(spend_7, leads_7) > 1.3 * SAFE_DIVIDE(spend_before, leads_before)
ORDER BY day;


-- =====================================================================================
-- 4a. R0 · Reconciliation of the payments table
-- Answers "what population is this?" before any payment figure is used.
-- Result: 50 payments · 38 distinct customers · ₪142,234 · 25 Jun 2024 – 26 Mar 2026 ·
-- no missing dates or amounts · no amount ≤ 0 · every payment falls inside one of the R1
-- periods · no customer appears in more than one period (10 + 25 + 3 = 38) · one customer
-- has three ₪1,800 payments on the same day (instalments, confirmed by the owner).
-- The 46 "paid-mentorship students" quoted earlier come from the owner's memory, not from
-- this table; 8 of them cannot be found here, and the reason is not documented. Every
-- payment figure therefore uses the 38 customers in the table.
-- =====================================================================================
SELECT
  COUNT(*)                                       AS payments,
  COUNT(DISTINCT customer_id)                    AS customers,
  SUM(amount_ils)                                AS total_ils,
  MIN(payment_date)                              AS first_payment,
  MAX(payment_date)                              AS last_payment,
  COUNTIF(payment_date IS NULL OR amount_ils IS NULL OR customer_id IS NULL) AS rows_with_missing_values,
  COUNTIF(amount_ils <= 0)                       AS non_positive_amounts,
  COUNTIF(payment_date < DATE '2024-06-01' OR payment_date > DATE '2026-03-31') AS outside_periods,
  COUNT(DISTINCT IF(payment_date <= DATE '2025-01-31', customer_id, NULL))  AS customers_before,
  COUNT(DISTINCT IF(payment_date BETWEEN DATE '2025-02-01' AND DATE '2025-08-31',
                    customer_id, NULL))          AS customers_during,
  COUNT(DISTINCT IF(payment_date >= DATE '2025-09-01', customer_id, NULL))  AS customers_after
FROM `bqproj26.meta_ads.student_payments`;


-- =====================================================================================
-- 4b. R1 · Payments and ad spend before, during and after the lead campaigns
-- Period boundaries: the lead campaigns are the only months with lead-objective spend
-- (Feb – Aug 2025, query A4). "Before" starts with the first ad month; "After" ends with
-- the last payment. Months are calendar months, including months with no ads (5 of 8
-- before, 2 of 7 after) or no payments. Payments are counted when received (cash), so an
-- instalment plan appears in the month of each instalment.
-- This is a historical comparison of periods. Payments are not linked to ads, so it is not
-- attribution and not proof that the ads caused the sales (in the same months we also tried to call
-- every lead).
-- Result: ≈ ₪4,795 a month before the lead campaigns, ≈ ₪11,996 during them (2.5×) and
-- ≈ ₪2,843 after. Ad spend ₪2,560 / ₪30,248 / ₪6,679 (total ₪39,487).
-- =====================================================================================
WITH periods AS (
  SELECT '1. Before lead campaigns' AS period, DATE '2024-06-01' AS start_date, DATE '2025-01-31' AS end_date
  UNION ALL
  SELECT '2. Lead campaigns',                  DATE '2025-02-01',               DATE '2025-08-31'
  UNION ALL
  SELECT '3. After lead campaigns',            DATE '2025-09-01',               DATE '2026-03-31'
),
revenue AS (
  SELECT
    p.period,
    SUM(pay.amount_ils)             AS revenue_ils,
    COUNT(DISTINCT pay.customer_id) AS paying_customers
  FROM periods AS p
  JOIN `bqproj26.meta_ads.student_payments` AS pay
    ON pay.payment_date BETWEEN p.start_date AND p.end_date
  GROUP BY p.period
),
ad_spend AS (
  SELECT
    p.period,
    SUM(ads.spend_ils) AS ad_spend_ils,
    SUM(ads.leads)     AS leads
  FROM periods AS p
  JOIN `bqproj26.meta_ads.v_ads_daily` AS ads
    ON ads.day BETWEEN p.start_date AND p.end_date
  WHERE ads.is_active
  GROUP BY p.period
)
SELECT
  p.period,
  DATE_DIFF(p.end_date, p.start_date, MONTH) + 1 AS months,
  r.revenue_ils,
  ROUND(SAFE_DIVIDE(r.revenue_ils, DATE_DIFF(p.end_date, p.start_date, MONTH) + 1)) AS revenue_per_month_ils,
  r.paying_customers,
  ROUND(a.ad_spend_ils)                          AS ad_spend_ils,
  ROUND(SAFE_DIVIDE(a.ad_spend_ils, DATE_DIFF(p.end_date, p.start_date, MONTH) + 1)) AS ad_spend_per_month_ils,
  a.leads
FROM periods AS p
JOIN revenue AS r USING (period)
LEFT JOIN ad_spend AS a USING (period)
ORDER BY p.period;


-- =====================================================================================
-- 4c. R2 · Media-spend coverage: how many average customers' payments equal ad spend?
-- A transparent hypothetical, NOT a business break-even:
--   • gross payments only — course delivery, mentorship, sales and other costs are excluded,
--     so this says nothing about profit;
--   • no customer is linked to an ad, so this is not CAC or ROAS and does not show that the
--     ads brought these customers.
-- Average payments per paying customer = total payments ÷ distinct customers (from the
-- table, not a typed-in number). Total Meta spend ÷ that average = how many average
-- customers' payments would equal the media spend.
-- Result: ₪142,234 ÷ 38 = ₪3,743 per paying customer; ₪39,487 of Meta spend equals the
-- payments of about 11 average customers (10.5 rounded up).
-- =====================================================================================
WITH payments AS (
  SELECT
    SUM(amount_ils)             AS payments_ils,
    COUNT(DISTINCT customer_id) AS paying_customers
  FROM `bqproj26.meta_ads.student_payments`
),
ads AS (
  SELECT SUM(spend_ils) AS ad_spend_ils
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
)
SELECT
  payments_ils,
  paying_customers,
  ROUND(SAFE_DIVIDE(payments_ils, paying_customers))  AS avg_payments_per_customer_ils,
  ROUND(ad_spend_ils)                                 AS ad_spend_ils,
  ROUND(SAFE_DIVIDE(ad_spend_ils, SAFE_DIVIDE(payments_ils, paying_customers)), 1)
                                                      AS customers_whose_payments_equal_ad_spend
FROM payments
CROSS JOIN ads;


-- =====================================================================================
-- 5. DASHBOARD DATA SOURCE · DS1 ads_active_days (Looker Studio custom query)
-- The business logic lives here; Looker Studio adds only ratio fields
-- (cpl = SUM(spend)/SUM(leads), cpm, ctr, click_to_lead, share of spend tied to a lead).
-- spend_purpose follows the owner's classification of each campaign objective. For the
-- ₪2,006 with no recorded objective, the month rules below were checked against the
-- ad-level evidence in A5 and agree for all but ₪84 (see A5). The dashboard shows total
-- Meta spend; cost per lead uses lead_spend_ils (lead objectives only, ₪29,383).
-- =====================================================================================
WITH base AS (
  SELECT
    day,
    month,
    account,
    objective,
    CASE
      WHEN objective = 'actions:leadgen.other' THEN 'Instant Form'
      WHEN objective = 'actions:offsite_conversion.fb_pixel_lead' THEN 'Landing page'
      ELSE 'Not a lead objective'
    END AS mechanism,
    CASE
      WHEN objective_family = 'lead' THEN 'Lead campaigns'
      WHEN objective = '(unknown)' AND EXTRACT(YEAR FROM day) = 2024 THEN 'Exposure'
      WHEN objective = '(unknown)' AND month = DATE '2025-03-01' THEN 'Lead campaigns'
      WHEN objective = '(unknown)' AND month IN (DATE '2025-10-01', DATE '2025-11-01') THEN 'Messages'
      WHEN objective = '(unknown)' AND month = DATE '2025-12-01' THEN 'Webinar funnel'
      WHEN objective IN ('video_thruplay_watched_actions', 'actions:omni_landing_page_view') THEN 'Webinar funnel'
      WHEN objective = 'actions:link_click' AND EXTRACT(YEAR FROM day) = 2025 THEN '₪97 mini-course'
      WHEN objective = 'actions:onsite_conversion.messaging_conversation_started_7d'
           AND EXTRACT(YEAR FROM day) = 2025 THEN 'Messages'
      ELSE 'Exposure'
    END AS spend_purpose,
    spend_ils,
    impressions,
    link_clicks,
    COALESCE(leads, 0) AS leads,
    IF(objective_family = 'lead', spend_ils, 0) AS lead_spend_ils
  FROM `bqproj26.meta_ads.v_ads_daily`
  WHERE is_active
)
SELECT
  *,
  IF(spend_purpose IN ('₪97 mini-course', 'Webinar funnel', 'Messages'), spend_ils, 0)
    AS conversion_test_spend_ils
FROM base;

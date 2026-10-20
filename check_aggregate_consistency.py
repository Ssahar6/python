#!/usr/bin/env python3
"""Checkpoint 00: do the previously supplied aggregate outputs agree with each other?

WHAT THIS PROVES
    That the Sprint 01 outputs, the Sprint 02 outputs and the numbers quoted in
    SESSION_LOG_2026-10-13.md are arithmetically consistent with one another.

WHAT THIS DOES NOT PROVE
    That any of them is correct. The raw Meta exports and the BigQuery table are
    not read here. Agreement between three summaries of the same cleaned file is
    weaker evidence than a re-run from source, and is reported as such.

Inputs are the aggregate outputs of the earlier project sprints (not included in this
repository). No customer data is involved; every input is an aggregate. Standard
library only. Result when run: 283 of 284 checks pass; the one failure is a ₪0.01
rounding difference (20.52 vs 20.53), later resolved by BigQuery.

Usage:
    python check_aggregate_consistency.py --archive <earlier sprint outputs> --outdir <results>
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path

LEAD_OBJECTIVES = {
    'actions:leadgen.other': 'instant_form',
    'actions:offsite_conversion.fb_pixel_lead': 'landing_page',
}
# Sprint 02 phase -> calendar months it covers (from PHASES in audit_strategy_changes.py).
PHASE_MONTHS = {
    'P1 Early non-lead advertising': ['2024-06', '2024-07', '2024-10'],
    'P2 Instant Form focus': ['2025-02', '2025-03', '2025-04', '2025-05', '2025-06'],
    'P3 Form and website': ['2025-07', '2025-08'],
    'P4 September click objective': ['2025-09'],
    'P5 Mixed non-lead objectives': ['2025-10', '2025-11', '2025-12', '2026-01'],
}

# ---------------------------------------------------------------------------
# Figures transcribed from SESSION_LOG_2026-10-13.md (section numbers in keys).
# They are claims under audit, not trusted inputs.
# ---------------------------------------------------------------------------
LOG_ACCOUNTS = {  # section 4: rows, active rows, spend, first/last active date, "months", active days
    'account_A': (4122, 50, '6017.15', date(2025, 7, 14), date(2025, 12, 3), 5, 25),
    'account_B': (87906, 545, '33469.41', date(2024, 6, 3), date(2026, 1, 24), 19, 243),
}
LOG_TOTAL_MONTHS, LOG_TOTAL_ACTIVE_DAYS = 19, 259
LOG_OBJECTIVES = {  # section 5: rounded spend, % of budget
    'actions:leadgen.other': (23801, 60.3),
    'actions:offsite_conversion.fb_pixel_lead': (5582, 14.1),
    'profile_visit_view': (3262, 8.3),
    'actions:link_click': (2098, 5.3),
    'unknown': (2006, 5.1),
    'actions:onsite_conversion.messaging_conversation_started_7d': (1719, 4.4),
    'actions:omni_landing_page_view': (434, 1.1),
    'reach': (350, 0.9),
    'video_thruplay_watched_actions': (234, 0.6),
}
LOG_FUNNEL = {  # section 6: "days" column, spend, impressions, clicks, leads, CTR%, click->lead%, CPL
    'actions:leadgen.other': (205, 23801, 487349, 3917, 1692, 0.80, 43.2, 14.07),
    'actions:offsite_conversion.fb_pixel_lead': (29, 5582, 80362, 755, 231, 0.94, 30.6, 24.16),
}
LOG_TREND = {  # section 7, instant form: days, ads in parallel, spend, leads, CPM, CTR%, click->lead%, CPL
    '2025-02': (9, 4.0, 3037, 346, 36.68, 0.99, 42.1, 8.78),
    '2025-03': (25, 3.6, 8668, 488, 48.05, 0.70, 38.6, 17.76),
    '2025-04': (28, 1.0, 4121, 324, 47.43, 0.81, 46.0, 12.72),
    '2025-05': (31, 1.0, 4623, 280, 58.89, 0.79, 45.1, 16.51),
    '2025-06': (9, 1.0, 1774, 100, 60.49, 0.71, 48.1, 17.74),
    '2025-07': (9, 1.0, 1578, 154, 53.58, 1.02, 51.5, 10.25),
}
LOG_FEB_JUN_PCT = {'cpm': 65, 'ctr': -28, 'cvr': 14, 'cpl': 102}  # section 7
LOG_CREATIVES = [  # section 8: ads in parallel, days, spend, leads
    (4, 29, 10590, 787), (3, 2, 670, 27), (2, 3, 523, 29), (1, 77, 12018, 849),
]
LOG_JULY = {  # section 6, "both ran in parallel in July": spend, leads, CPL
    'instant_form': (1578, 154, 10.25),
    'landing_page': (5295, 217, 24.40),
}
LOG_LEAD_SHEET = {  # section 10
    'big_file_rows': 1803, 'detailed_rows': 130,
    'status': {'unreachable': 36, 'disqualified': 43, 'in_process': 34, 'meeting_set': 3, 'other_or_blank': 14},
    'claimed_dead_pct': 61, 'claimed_workable_cpl': 36, 'overall_cpl': 15.28,
}


class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, cid: str, what: str, actual, expected, tol=0) -> None:
        if isinstance(actual, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
            ok = abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal(str(tol))
        else:
            ok = actual == expected
        self.rows.append({'id': cid, 'status': 'PASS' if ok else 'FAIL', 'check': what,
                          'actual': str(actual), 'expected': str(expected)})

    def note(self, cid: str, what: str, detail: str) -> None:
        self.rows.append({'id': cid, 'status': 'NOTE', 'check': what, 'actual': detail, 'expected': ''})

    def count(self, status: str) -> int:
        return sum(r['status'] == status for r in self.rows)


def read_csv(path: Path) -> list[dict]:
    with path.open('r', newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def dec(x) -> Decimal:
    return Decimal(str(x)) if str(x).strip() else Decimal('0')


def total(rows: list[dict], col: str) -> Decimal:
    return sum((dec(r[col]) for r in rows), Decimal('0'))


def month_span(first: date, last: date) -> tuple[int, int]:
    """(month-boundary difference, calendar months touched) between two dates."""
    diff = (last.year - first.year) * 12 + (last.month - first.month)
    return diff, diff + 1


def calendar_months(first: date, last: date) -> list[str]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(f'{y}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def ratios(spend, impressions, clicks, leads) -> dict:
    spend, impressions, clicks, leads = map(float, (spend, impressions, clicks, leads))
    return {'cpm': 1000 * spend / impressions, 'ctr': clicks / impressions,
            'cvr': leads / clicks, 'cpl': spend / leads}


def sprint01_internal(r: Report, v: dict, objectives, months, mech, decomp) -> None:
    lead_rows = [o for o in objectives if o['result_indicator'] in LEAD_OBJECTIVES]
    r.check('A01', 'S1 objective spend sums to total spend', total(objectives, 'spend_ils'), dec(v['total_spend_ils']))
    r.check('A02', 'S1 objective active rows sum to active ad-day rows', total(objectives, 'active_ad_day_rows'), v['active_ad_day_rows'])
    r.check('A03', 'S1 objective leads sum to Meta-attributed leads', total(objectives, 'meta_attributed_leads'), v['meta_attributed_leads'])
    r.check('A04', 'S1 two lead objectives sum to lead-generation spend', total(lead_rows, 'spend_ils'), dec(v['lead_generation_spend_ils']))
    unknown = [o for o in objectives if o['result_indicator'] == 'unknown']
    r.check('A05', 'S1 unknown-objective spend matches verification JSON', total(unknown, 'spend_ils'), dec(v['unknown_objective_spend_ils']))
    r.check('A06', 'S1 monthly spend sums to total spend', total(months, 'spend_ils'), dec(v['total_spend_ils']))
    r.check('A07', 'S1 monthly active rows sum to active ad-day rows', total(months, 'active_ad_day_rows'), v['active_ad_day_rows'])
    r.check('A08', 'S1 monthly leads sum to Meta-attributed leads', total(months, 'meta_attributed_leads'), v['meta_attributed_leads'])
    r.check('A09', 'S1 month list equals months in 02_spend_by_month.csv', [m['month'] for m in months], v['months_list'])
    r.check('A10', 'S1 months_with_positive_spend equals length of month list', len(v['months_list']), v['months_with_positive_spend'])

    acc = v['per_account'].values()
    r.check('A11', 'S1 per-account rows sum to source rows', sum(a['rows'] for a in acc), v['source_rows'])
    r.check('A12', 'S1 per-account spend sums to total spend', sum((dec(a['spend_ils']) for a in acc), Decimal('0')), dec(v['total_spend_ils']))
    r.check('A13', 'S1 per-account active rows sum to active ad-day rows', sum(a['active_ad_day_rows'] for a in acc), v['active_ad_day_rows'])
    r.check('A14', 'S1 per-account leads sum to Meta-attributed leads', sum(a['meta_attributed_leads'] for a in acc), v['meta_attributed_leads'])
    # Per-account totals include zero-spend rows; objective totals do not. Equality
    # therefore supports the log's claim that no zero-spend row carries impressions/clicks.
    r.check('A15', 'S1 impressions: all rows (per account) == active rows (per objective)', sum(a['impressions'] for a in acc), total(objectives, 'impressions'))
    r.check('A16', 'S1 link clicks: all rows (per account) == active rows (per objective)', sum(a['link_clicks'] for a in acc), total(objectives, 'link_clicks'))

    for obj, name in LEAD_OBJECTIVES.items():
        o = next(x for x in objectives if x['result_indicator'] == obj)
        m = [x for x in mech if x['mechanism'] == name]
        for col in ('spend_ils', 'impressions', 'link_clicks', 'meta_attributed_leads', 'active_ad_day_rows'):
            r.check('A17', f'S1 monthly {name} {col} sums to objective total', total(m, col), dec(o[col]))

    # Reported rate columns must equal SUM(numerator)/SUM(denominator) from the same row.
    for row in lead_rows + mech:
        label = row.get('month', 'all') + ' ' + row.get('mechanism', row.get('result_indicator', ''))
        x = ratios(row['spend_ils'], row['impressions'], row['link_clicks'], row['meta_attributed_leads'])
        r.check('A18', f'S1 CPL recomputed from counts ({label})', round(x['cpl'], 4), dec(row['cpl_ils']), tol='0.0051')
        r.check('A18', f'S1 CPM recomputed from counts ({label})', round(x['cpm'], 4), dec(row['cpm_ils']), tol='0.0051')
        r.check('A18', f'S1 CTR% recomputed from counts ({label})', round(100 * x['ctr'], 5), dec(row['ctr_pct']), tol='0.00051')
        r.check('A18', f'S1 click-to-lead% recomputed from counts ({label})', round(100 * x['cvr'], 4), dec(row['click_to_lead_pct']), tol='0.0051')

    by_key = {(m['month'], m['mechanism']): m for m in mech}
    for d in decomp:
        a, b = by_key[(d['from_month'], d['mechanism'])], by_key[(d['to_month'], d['mechanism'])]
        x0 = ratios(a['spend_ils'], a['impressions'], a['link_clicks'], a['meta_attributed_leads'])
        x1 = ratios(b['spend_ils'], b['impressions'], b['link_clicks'], b['meta_attributed_leads'])
        label = f"{d['mechanism']} {d['from_month']}->{d['to_month']}"
        parts = {'cpm_log_contribution': math.log(x1['cpm'] / x0['cpm']),
                 'ctr_log_contribution': -math.log(x1['ctr'] / x0['ctr']),
                 'cvr_log_contribution': -math.log(x1['cvr'] / x0['cvr']),
                 'total_log_cpl_change': math.log(x1['cpl'] / x0['cpl'])}
        for col, val in parts.items():
            r.check('A19', f'S1 {col} recomputed ({label})', round(val, 6), dec(d[col]), tol='0.00006')
        identity = parts['cpm_log_contribution'] + parts['ctr_log_contribution'] + parts['cvr_log_contribution']
        r.check('A20', f'S1 log identity CPM+CTR+CVR == CPL ({label})', round(identity - parts['total_log_cpl_change'], 9), 0, tol='0.000000001')
        r.check('A21', f'S1 decomposition CPL end equals monthly file CPL ({label})', dec(d['cpl_end_ils']), dec(b['cpl_ils']))

    fj = v['feb_2025_to_jun_2025_instant_form_decomposition']
    a, b = by_key[('2025-02', 'instant_form')], by_key[('2025-06', 'instant_form')]
    x0 = ratios(a['spend_ils'], a['impressions'], a['link_clicks'], a['meta_attributed_leads'])
    x1 = ratios(b['spend_ils'], b['impressions'], b['link_clicks'], b['meta_attributed_leads'])
    r.check('A22', 'S1 Feb->Jun CPM log contribution recomputed', round(math.log(x1['cpm'] / x0['cpm']), 6), fj['cpm_log_contribution'], tol='0.00006')
    r.check('A22', 'S1 Feb->Jun CTR log contribution recomputed', round(-math.log(x1['ctr'] / x0['ctr']), 6), fj['ctr_log_contribution'], tol='0.00006')
    r.check('A22', 'S1 Feb->Jun CVR log contribution recomputed', round(-math.log(x1['cvr'] / x0['cvr']), 6), fj['cvr_log_contribution'], tol='0.00006')
    r.check('A22', 'S1 Feb->Jun CPL change % recomputed', round(100 * (x1['cpl'] / x0['cpl'] - 1), 4), fj['cpl_change_pct'], tol='0.0051')


def month_count_discrepancy(r: Report, v: dict) -> None:
    first, last = date.fromisoformat(v['first_active_date']), date.fromisoformat(v['last_active_date'])
    diff, touched = month_span(first, last)
    cal = calendar_months(first, last)
    idle = [m for m in cal if m not in v['months_list']]
    r.check('B01', 'Month-boundary difference first->last active date equals the log\'s "19 months"', diff, LOG_TOTAL_MONTHS)
    r.check('B02', 'Months with positive spend equals Sprint 01\'s 15', len(v['months_list']), 15)
    r.check('B03', 'Calendar months touched = months with spend + months without', touched, len(v['months_list']) + len(idle))
    for name, (_, _, _, a_first, a_last, months_claim, _) in LOG_ACCOUNTS.items():
        r.check('B04', f'Log "months" for {name} equals month-boundary difference of its own dates', month_span(a_first, a_last)[0], months_claim)
    r.note('B05', '19 vs 15 months: three different metrics, none wrong on these inputs',
           f'month-boundary difference = {diff}; calendar months touched = {touched}; months with spend = {len(v["months_list"])}; '
           f'months with zero spend = {idle}; calendar days in span = {(last - first).days + 1}; dates with spend = {v["active_calendar_dates"]}. '
           'The log\'s per-account "months" match a month-difference in both accounts (B04), so 19 is most likely DATE_DIFF(last, first, MONTH). '
           'Still to confirm on raw data / BigQuery.')
    per_account_days = sum(a[6] for a in LOG_ACCOUNTS.values())
    r.note('B06', 'Active days per account vs total',
           f'log: A {LOG_ACCOUNTS["account_A"][6]} + B {LOG_ACCOUNTS["account_B"][6]} = {per_account_days}, total distinct = {LOG_TOTAL_ACTIVE_DAYS}; '
           f'so both accounts spent on the same {per_account_days - LOG_TOTAL_ACTIVE_DAYS} dates.')


def sprint02_vs_sprint01(r: Report, v, objectives, months, mech, phases, phase_obj, july, key) -> None:
    r.check('C01', 'S2 phase spend sums to total spend', total(phases, 'spend_ils'), dec(v['total_spend_ils']))
    r.check('C02', 'S2 phase leads sum to Meta-attributed leads', total(phases, 'meta_attributed_leads'), v['meta_attributed_leads'])
    r.check('C03', 'S2 phase active rows sum to active ad-day rows', total(phases, 'active_ad_day_rows'), v['active_ad_day_rows'])
    r.check('C04', 'S2 phase distinct active days sum to S1 active calendar dates', total(phases, 'distinct_active_days'), v['active_calendar_dates'])
    r.check('C05', 'S2 phase link clicks sum to S1 link clicks', total(phases, 'link_clicks'), total(objectives, 'link_clicks'))
    by_month = {m['month']: m for m in months}
    for p in phases:
        inside = [by_month[m] for m in PHASE_MONTHS[p['phase']]]
        r.check('C06', f"S2 spend of '{p['phase']}' equals S1 monthly spend in the same months", dec(p['spend_ils']), total(inside, 'spend_ils'))
        r.check('C07', f"S2 first/last active month of '{p['phase']}' matches S1 months", [p['first_active_date'][:7], p['last_active_date'][:7]], [PHASE_MONTHS[p['phase']][0], PHASE_MONTHS[p['phase']][-1]])
        rows = [x for x in phase_obj if x['phase'] == p['phase']]
        for col in ('spend_ils', 'meta_attributed_leads', 'link_clicks', 'active_ad_day_rows'):
            r.check('C08', f"S2 phase x objective {col} sums to phase total ('{p['phase']}')", total(rows, col), dec(p[col]))
    for o in objectives:
        rows = [x for x in phase_obj if x['objective'] == o['result_indicator']]
        for col in ('spend_ils', 'meta_attributed_leads', 'link_clicks', 'active_ad_day_rows'):
            r.check('C09', f"S2 phase x objective {col} sums to S1 objective total ({o['result_indicator']})", total(rows, col), dec(o[col]))

    late = [m for m in months if m['month'] >= '2025-09']
    r.check('C10', 'S2 Sep 2025-Jan 2026 spend equals S1 monthly spend for those months', dec(key['sep_2025_to_jan_2026_spend_ils']), total(late, 'spend_ils'))
    r.check('C11', 'S2 Sep 2025-Jan 2026 lead results equal S1 monthly leads for those months', key['sep_2025_to_jan_2026_meta_attributed_lead_results'], total(late, 'meta_attributed_leads'))
    r.check('C12', 'S2 Sep 2025 link clicks equal S1 Sep 2025 link clicks', key['sep_2025_link_clicks'], dec(by_month['2025-09']['link_clicks']))

    by_key = {(m['month'], m['mechanism']): m for m in mech}
    for row in july:
        name = LEAD_OBJECTIVES[row['objective']]
        r.check('C13', f'S2 July overlap CPL recomputed ({name})', round(float(row['spend_ils']) / float(row['meta_attributed_leads']), 4), dec(row['cpl_ils']), tol='0.0051')
        full = by_key[('2025-07', name)]
        same = all(dec(row[c]) == dec(full[c]) for c in ('spend_ils', 'meta_attributed_leads', 'link_clicks', 'impressions'))
        r.note('C14', f'July 22-30 overlap vs full July ({name})',
               f"overlap: ILS {row['spend_ils']} / {int(float(row['meta_attributed_leads']))} leads; full July: ILS {full['spend_ils']} / {full['meta_attributed_leads']} leads -> "
               + ('identical: every July row of this mechanism lies inside the overlap window.' if same
                  else 'different: this mechanism also ran in July outside the overlap window.'))


def session_log_vs_outputs(r: Report, v, objectives, mech, phases) -> None:
    for name, (rows, active, spend, *_rest) in LOG_ACCOUNTS.items():
        a = v['per_account'][name]
        r.check('D01', f'Log rows for {name} equal S1', rows, a['rows'])
        r.check('D01', f'Log active rows for {name} equal S1', active, a['active_ad_day_rows'])
        r.check('D01', f'Log spend for {name} equals S1', dec(spend), dec(a['spend_ils']))
    r.check('D02', 'Log total active days equal S1 active calendar dates', LOG_TOTAL_ACTIVE_DAYS, v['active_calendar_dates'])

    by_obj = {o['result_indicator']: o for o in objectives}
    grand = dec(v['total_spend_ils'])
    for obj, (spend, pct) in LOG_OBJECTIVES.items():
        r.check('D03', f'Log objective spend (rounded) equals S1 ({obj})', spend, dec(by_obj[obj]['spend_ils']), tol='0.5')
        r.check('D04', f'Log objective share % equals S1 spend share ({obj})', pct, round(float(100 * dec(by_obj[obj]['spend_ils']) / grand), 3), tol='0.051')

    for obj, (days, spend, imps, clicks, leads, ctr, cvr, cpl) in LOG_FUNNEL.items():
        o, name = by_obj[obj], LEAD_OBJECTIVES[obj]
        r.check('D05', f'Log funnel spend equals S1 ({name})', spend, dec(o['spend_ils']), tol='0.5')
        r.check('D05', f'Log funnel impressions equal S1 ({name})', imps, dec(o['impressions']))
        r.check('D05', f'Log funnel clicks equal S1 ({name})', clicks, dec(o['link_clicks']))
        r.check('D05', f'Log funnel leads equal S1 ({name})', leads, dec(o['meta_attributed_leads']))
        r.check('D05', f'Log funnel CTR% equals S1 ({name})', ctr, dec(o['ctr_pct']), tol='0.0051')
        r.check('D05', f'Log funnel click-to-lead% equals S1 ({name})', cvr, dec(o['click_to_lead_pct']), tol='0.051')
        r.check('D05', f'Log funnel CPL equals S1 ({name})', cpl, dec(o['cpl_ils']))
        r.check('D06', f'Log funnel "days" column equals S1 active ad-day ROWS ({name})', days, dec(o['active_ad_day_rows']))

    by_key = {(m['month'], m['mechanism']): m for m in mech}
    for month, (days, ads, spend, leads, cpm, ctr, cvr, cpl) in LOG_TREND.items():
        m = by_key[(month, 'instant_form')]
        r.check('D07', f'Log trend spend equals S1 ({month})', spend, dec(m['spend_ils']), tol='0.5')
        r.check('D07', f'Log trend leads equal S1 ({month})', leads, dec(m['meta_attributed_leads']))
        r.check('D07', f'Log trend CPM equals S1 ({month})', cpm, dec(m['cpm_ils']))
        r.check('D07', f'Log trend CTR% equals S1 ({month})', ctr, dec(m['ctr_pct']), tol='0.0051')
        r.check('D07', f'Log trend click-to-lead% equals S1 ({month})', cvr, dec(m['click_to_lead_pct']), tol='0.051')
        r.check('D07', f'Log trend CPL equals S1 ({month})', cpl, dec(m['cpl_ils']))
        r.check('D08', f'Log "ads in parallel" equals S1 active rows / log days ({month})', ads, round(int(m['active_ad_day_rows']) / days, 3), tol='0.051')
    trend_days = sum(t[0] for t in LOG_TREND.values())
    r.check('D09', 'Log trend days sum to the log\'s "111 active days"', trend_days, 111)
    p2 = next(p for p in phases if p['phase'].startswith('P2'))
    r.check('D10', 'Log trend days Feb-Jun equal S2 distinct active days of P2', sum(LOG_TREND[m][0] for m in PHASE_MONTHS['P2 Instant Form focus']), dec(p2['distinct_active_days']))

    a, b = by_key[('2025-02', 'instant_form')], by_key[('2025-06', 'instant_form')]
    x0 = ratios(a['spend_ils'], a['impressions'], a['link_clicks'], a['meta_attributed_leads'])
    x1 = ratios(b['spend_ils'], b['impressions'], b['link_clicks'], b['meta_attributed_leads'])
    for k, claim in LOG_FEB_JUN_PCT.items():
        r.check('D11', f'Log Feb->Jun {k.upper()} change % equals value recomputed from S1 counts', claim, round(100 * (x1[k] / x0[k] - 1), 2), tol='0.6')

    instant = by_obj['actions:leadgen.other']
    r.check('D12', 'Log creative table days sum to 111', sum(c[1] for c in LOG_CREATIVES), 111)
    r.check('D12', 'Log creative table ads x days equals S1 instant-form active rows', sum(c[0] * c[1] for c in LOG_CREATIVES), dec(instant['active_ad_day_rows']))
    r.check('D12', 'Log creative table spend (rounded) sums to S1 instant-form spend', sum(c[2] for c in LOG_CREATIVES), dec(instant['spend_ils']), tol='2')
    r.check('D12', 'Log creative table leads sum to S1 instant-form leads', sum(c[3] for c in LOG_CREATIVES), dec(instant['meta_attributed_leads']))

    r.note('D13', 'Log section 6 labels 205 and 29 as "days"',
           'They equal active ad-day ROWS (D06). Distinct instant-form days are 111 (D09). The column header in the log is mislabeled; no number changes.')
    for name, (spend, leads, cpl) in LOG_JULY.items():
        m = by_key[('2025-07', name)]
        r.check('D14', f'Log July comparison uses S1 full-July figures ({name})', [spend, leads, cpl], [round(float(m['spend_ils'])), int(m['meta_attributed_leads']), float(m['cpl_ils'])])
    r.note('D15', 'Log says the July comparison "neutralizes time"',
           'It compares full-July landing page (from 14 Jul, ILS 5,294.68 / 217, CPL 24.40) with instant form that ran only 22-30 Jul. '
           'Sprint 02 restricts both to 22-30 Jul (CPL 10.25 vs 24.54). Use the Sprint 02 version; the log wording overstates the control.')

    s = LOG_LEAD_SHEET
    r.check('D16', 'Lead-sheet status categories sum to 130', sum(s['status'].values()), s['detailed_rows'])
    dead = (s['status']['unreachable'] + s['status']['disqualified']) / s['detailed_rows']
    r.check('D17', 'Lead-sheet "61% dead on arrival" recomputed', s['claimed_dead_pct'], round(100 * dead, 1), tol='0.5')
    instant_cpl = float(instant['cpl_ils'])
    r.note('D18', 'Lead-sheet "workable lead costs ~ILS 36"',
           f'CPL / (1 - dead share): overall CPL {s["overall_cpl"]} -> {s["overall_cpl"] / (1 - dead):.2f}; instant-form CPL {instant_cpl} -> {instant_cpl / (1 - dead):.2f}. '
           'The claim reproduces only with the instant-form CPL, and rests on n=130 over 19 days with unknown ad source. Illustrative, not verified.')
    r.note('D19', 'Log says 1,923 is cross-validated by the lead sheet',
           f'Lead files hold {s["big_file_rows"]} and {s["detailed_rows"]} rows ({s["big_file_rows"] + s["detailed_rows"]} combined, overlap unknown); neither equals {v["meta_attributed_leads"]}. '
           'No supplied evidence shows an independent source for 1,923. Treat as unverified.')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', required=True, help='folder produced by tools/extract_archive.py')
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()
    s1 = Path(args.archive) / 'business_retrospective_sprint01' / 'outputs' / 'aggregates'
    s2 = Path(args.archive) / 'business_retrospective_sprint02' / 'outputs'
    v = json.loads((s1 / '00_verification.json').read_text(encoding='utf-8'))
    objectives = read_csv(s1 / '01_objective_summary.csv')
    months = read_csv(s1 / '02_spend_by_month.csv')
    mech = read_csv(s1 / '03_leads_by_month_mechanism.csv')
    decomp = read_csv(s1 / '04_cpl_decomposition.csv')
    phases = read_csv(s2 / '01_observed_periods.csv')
    phase_obj = read_csv(s2 / '02_period_objective_spend.csv')
    july = read_csv(s2 / '03_july_2025_overlap.csv')
    key = json.loads((s2 / '04_key_checks.json').read_text(encoding='utf-8'))

    r = Report()
    sprint01_internal(r, v, objectives, months, mech, decomp)
    month_count_discrepancy(r, v)
    sprint02_vs_sprint01(r, v, objectives, months, mech, phases, phase_obj, july, key)
    session_log_vs_outputs(r, v, objectives, mech, phases)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {'scope': 'Internal consistency of previously supplied aggregates only; raw exports and BigQuery not read.',
               'pass': r.count('PASS'), 'fail': r.count('FAIL'), 'notes': r.count('NOTE'), 'results': r.rows}
    (out / 'C00_aggregate_consistency.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out / 'C00_aggregate_consistency.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'status', 'check', 'actual', 'expected'])
        writer.writeheader()
        writer.writerows(r.rows)

    for row in r.rows:
        if row['status'] != 'PASS':
            print(f"[{row['status']}] {row['id']} {row['check']}\n        actual: {row['actual']}"
                  + (f"\n        expected: {row['expected']}" if row['expected'] else ''))
    print(f"PASS {summary['pass']}  FAIL {summary['fail']}  NOTE {summary['notes']}  -> {out}")


if __name__ == '__main__':
    main()

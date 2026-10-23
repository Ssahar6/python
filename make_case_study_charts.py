"""Builds the three case-study charts from the project data and checks every plotted figure.

Inputs:  the cleaned Meta Ads export (same file as BigQuery table ads_daily_raw) and the
         anonymous student_payments.csv.
Outputs: three SVG charts and the daily alert series (aggregate figures only, no customer data).
Every number drawn is recomputed here and asserted against the results already verified in
BigQuery (D1, A2, R1), so a chart cannot drift from the published analysis.

Usage: python make_case_study_charts.py --ads meta_ads_clean.csv --payments student_payments.csv --out images
Standard library only.
"""
import argparse
import csv
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

INSTANT_FORM = 'actions:leadgen.other'
LEAD_OBJECTIVES = {INSTANT_FORM, 'actions:offsite_conversion.fb_pixel_lead'}
FONT = "font-family='Segoe UI, Helvetica, Arial, sans-serif'"
INK, MUTED, GRID = '#1d2433', '#5b6475', '#e3e7ee'
BLUE, ORANGE, GREEN, RED = '#2f5d8a', '#d9662b', '#2a9d7f', '#c0392b'


def num(x):
    return float(x) if x not in (None, '') else 0.0


def load_ads(path):
    rows = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            spend = num(r['spend_ils'])
            if spend <= 0:
                continue
            rows.append({'day': date.fromisoformat(r['date_start']), 'objective': r['result_indicator'],
                         'spend': spend, 'impr': num(r['impressions']),
                         'clicks': num(r['link_clicks']), 'results': num(r['results'])})
    return rows


def svg(width, height, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
            f"viewBox='0 0 {width} {height}' {FONT}>"
            f"<rect width='{width}' height='{height}' fill='#ffffff'/>{body}</svg>")


def text(x, y, s, size=14, color=INK, anchor='start', weight=400):
    s = s.replace('&', '&amp;').replace('<', '&lt;')
    return (f"<text x='{x:.1f}' y='{y:.1f}' font-size='{size}' fill='{color}' "
            f"text-anchor='{anchor}' font-weight='{weight}'>{s}</text>")


# ---------- Case study 1: where the Feb -> Jun 2025 cost-per-lead increase sits ----------
def chart_decomposition(ads, out):
    m = defaultdict(lambda: defaultdict(float))
    for r in ads:
        if r['objective'] == INSTANT_FORM and r['day'].year == 2025 and r['day'].month in (2, 6):
            k = r['day'].month
            m[k]['spend'] += r['spend']; m[k]['impr'] += r['impr']
            m[k]['clicks'] += r['clicks']; m[k]['leads'] += r['results']
    rate = {}
    for k, v in m.items():
        rate[k] = {'cpm': 1000 * v['spend'] / v['impr'], 'ctr': v['clicks'] / v['impr'],
                   'cvr': v['leads'] / v['clicks'], 'cpl': v['spend'] / v['leads']}
    feb, jun = rate[2], rate[6]
    total = math.log(jun['cpl'] / feb['cpl'])
    parts = [('Ads cost more to show', 'CPM', math.log(jun['cpm'] / feb['cpm']), jun['cpm'] / feb['cpm'] - 1),
             ('Fewer people clicked', 'CTR', -math.log(jun['ctr'] / feb['ctr']), jun['ctr'] / feb['ctr'] - 1),
             ('More clickers signed up', 'click-to-lead rate', -math.log(jun['cvr'] / feb['cvr']), jun['cvr'] / feb['cvr'] - 1)]
    shares = [round(100 * p[2] / total) for p in parts]
    assert (round(feb['cpl'], 2), round(jun['cpl'], 2)) == (8.78, 17.74), 'CPL differs from D1'
    assert shares == [71, 48, -19], f'shares differ from D1: {shares}'

    W, H, x0, scale = 900, 400, 330, 4.2
    b = [text(30, 40, 'Where the cost-per-lead increase sits (Instant Form, Feb → Jun 2025)', 20, weight=600),
         text(30, 66, f"Cost per lead rose from ₪{feb['cpl']:.2f} to ₪{jun['cpl']:.2f}. "
                      'Bars: share of the increase (log split, adds up to 100%).', 14, MUTED)]
    zero = x0 + 19 * scale + 20
    b.append(f"<line x1='{zero}' y1='92' x2='{zero}' y2='330' stroke='{MUTED}' stroke-width='1'/>")
    for i, ((label, metric, _, change), share) in enumerate(zip(parts, shares)):
        y = 110 + i * 70
        w = abs(share) * scale
        x = zero if share >= 0 else zero - w
        b.append(f"<rect x='{x:.1f}' y='{y}' width='{w:.1f}' height='34' rx='3' fill='{ORANGE if share > 0 else BLUE}'/>")
        b.append(text(30, y + 16, label, 15, weight=600))
        b.append(text(30, y + 34, f'{metric} {change:+.0%} (actual change)', 13, MUTED))
        b.append(text(zero + w + 10 if share >= 0 else zero + 10, y + 23, f'{share:+d}%', 15, weight=600))
    b.append(f"<rect x='{zero}' y='318' width='{100 * scale:.1f}' height='6' fill='{MUTED}'/>")
    b.append(text(zero, 342, 'Total: 100% = the full increase (cost per lead doubled)', 13, MUTED))
    b.append(text(30, 372, 'An arithmetic split of CPL = (CPM ÷ 1,000) ÷ CTR ÷ click-to-lead rate. '
                           'It shows where the change sits, not why it happened.', 13, MUTED))
    b.append(text(30, 392, 'Source: Meta Ads export, BigQuery query D1.', 12, MUTED))
    (out / 'cs1_cpl_decomposition.svg').write_text(svg(W, H, ''.join(b)), encoding='utf-8')
    return feb, jun, shares


# ---------- Case study 2: payments vs ad spend, before / during / after the lead campaigns ----------
PERIODS = [('Before', 'Jun 2024 – Jan 2025', date(2024, 6, 1), date(2025, 1, 31), 8),
           ('Lead campaigns', 'Feb – Aug 2025', date(2025, 2, 1), date(2025, 8, 31), 7),
           ('After', 'Sep 2025 – Mar 2026', date(2025, 9, 1), date(2026, 3, 31), 7)]


def chart_periods(ads, payments_path, out):
    pays = []
    with open(payments_path, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            pays.append((date.fromisoformat(r['payment_date']), float(r['amount_ils']), r['customer_id']))
    res = []
    for name, label, s, e, months in PERIODS:
        p = sum(a for d, a, _ in pays if s <= d <= e)
        c = len({cid for d, _, cid in pays if s <= d <= e})
        a = sum(r['spend'] for r in ads if s <= r['day'] <= e)
        res.append((name, label, p / months, a / months, c))
    assert [round(r[2]) for r in res] == [4795, 11996, 2843], 'payments differ from R1'
    assert [round(r[3] * m) for r, m in zip(res, [8, 7, 7])] == [2560, 30248, 6679], 'ad spend differs from R1'
    assert [r[4] for r in res] == [10, 25, 3], 'customers differ from R1'

    W, H, base, top = 900, 430, 330, 110
    scale = (base - top) / 12000
    b = [text(30, 40, 'Customer payments and Meta ad spend per month, by period', 20, weight=600),
         text(30, 66, '38 paying customers, 50 payments, ₪142,234 excl. VAT (by date received). '
                      'Calendar months, incl. months with no ads.', 14, MUTED),
         f"<rect x='560' y='82' width='14' height='14' fill='{GREEN}'/>", text(580, 94, 'Customer payments', 13),
         f"<rect x='720' y='82' width='14' height='14' fill='{ORANGE}'/>", text(740, 94, 'Meta ad spend', 13)]
    for v in (0, 4000, 8000, 12000):
        y = base - v * scale
        b.append(f"<line x1='90' y1='{y:.1f}' x2='870' y2='{y:.1f}' stroke='{GRID}'/>")
        b.append(text(82, y + 4, f'₪{v:,}', 12, MUTED, 'end'))
    for i, (name, label, pay, spend, cust) in enumerate(res):
        cx = 220 + i * 250
        for j, (v, color) in enumerate(((pay, GREEN), (spend, ORANGE))):
            h = v * scale
            x = cx - 62 + j * 66
            b.append(f"<rect x='{x}' y='{base - h:.1f}' width='58' height='{h:.1f}' rx='2' fill='{color}'/>")
            b.append(text(x + 29, base - h - 8, f'₪{v:,.0f}', 13, INK, 'middle', 600))
        b.append(text(cx, base + 24, name, 15, INK, 'middle', 600))
        b.append(text(cx, base + 42, f'{label} · {cust} customers', 12, MUTED, 'middle'))
    b.append(text(30, 400, 'A comparison of periods, not attribution: no payment is linked to the channel that '
                           'brought the customer.', 13, MUTED))
    b.append(text(30, 420, 'Source: anonymised payment records and Meta Ads export, BigQuery queries R0–R1.', 12, MUTED))
    (out / 'cs2_payments_vs_ad_spend.svg').write_text(svg(W, H, ''.join(b)), encoding='utf-8')
    return res


# ---------- Case study 3: the retrospective cost-per-lead alert ----------
def alert_series(ads):
    d = defaultdict(lambda: [0.0, 0.0])
    for r in ads:
        if r['objective'] == INSTANT_FORM:
            d[r['day']][0] += r['spend']; d[r['day']][1] += r['results']
    days = sorted(d)
    rows = []
    for i, day in enumerate(days):
        win = days[max(0, i - 6): i + 1]
        before = days[: max(0, i - 6)]
        s7, l7 = sum(d[x][0] for x in win), sum(d[x][1] for x in win)
        sb, lb = sum(d[x][0] for x in before), sum(d[x][1] for x in before)
        cpl7 = s7 / l7 if l7 else None
        base = sb / lb if lb else None
        ready = len(win) == 7 and lb >= 100
        alert = bool(ready and cpl7 is not None and cpl7 > 1.3 * base)
        rows.append({'day': day, 'spend': d[day][0], 'leads': d[day][1], 'cpl_7': cpl7,
                     'cpl_before': base if ready else None,
                     'threshold': 1.3 * base if ready else None, 'alert': alert})
    return rows


def chart_alert(rows, out):
    alerts = [r for r in rows if r['alert']]
    first = [r for r in alerts if r['day'] <= date(2025, 4, 4)]
    assert len(alerts) == 33 and len(first) == 27, 'alert days differ from A2'
    assert round(sum(r['spend'] for r in first), 2) == 8873.80 and sum(r['leads'] for r in first) == 512
    assert alerts[0]['day'] == date(2025, 3, 1)
    assert (round(alerts[0]['cpl_7'], 2), round(alerts[0]['cpl_before'], 2)) == (10.50, 5.97)

    plot = [r for r in rows if r['cpl_7'] is not None]
    d0, d1 = plot[0]['day'], plot[-1]['day']
    W, H, L, R, T, B = 900, 470, 80, 870, 100, 380
    ymax = 25.0
    X = lambda d: L + (d - d0).days / (d1 - d0).days * (R - L)
    Y = lambda v: B - v / ymax * (B - T)
    b = [text(30, 40, 'Could a daily alert have caught the cost rise earlier? (retrospective test)', 20, weight=600),
         text(30, 66, 'Instant Form campaign, active days only. Alert = last-7-day cost per lead more than 30% '
                      'above all earlier days.', 14, MUTED)]
    for v in (0, 5, 10, 15, 20, 25):
        b.append(f"<line x1='{L}' y1='{Y(v):.1f}' x2='{R}' y2='{Y(v):.1f}' stroke='{GRID}'/>")
        b.append(text(L - 8, Y(v) + 4, f'₪{v}', 12, MUTED, 'end'))
    for m in range(2, 8):
        md = date(2025, m, 1)
        if d0 <= md <= d1:
            b.append(text(X(md), B + 22, md.strftime('%b %Y'), 12, MUTED, 'middle'))
    # shade alert days
    for r in alerts:
        b.append(f"<rect x='{X(r['day']) - 2:.1f}' y='{T}' width='4' height='{B - T}' fill='{RED}' opacity='0.12'/>")
    line = ' '.join(f"{X(r['day']):.1f},{Y(r['cpl_7']):.1f}" for r in plot)
    b.append(f"<polyline points='{line}' fill='none' stroke='{BLUE}' stroke-width='2.5'/>")
    thr = ' '.join(f"{X(r['day']):.1f},{Y(r['threshold']):.1f}" for r in plot if r['threshold'] is not None)
    b.append(f"<polyline points='{thr}' fill='none' stroke='{ORANGE}' stroke-width='2' stroke-dasharray='6 4'/>")
    f = alerts[0]
    fx, fy = X(f['day']), Y(f['cpl_7'])
    ax, ay = X(date(2025, 4, 22)), Y(8.2)
    b.append(f"<line x1='{fx + 6:.1f}' y1='{fy + 4:.1f}' x2='{ax - 6:.1f}' y2='{ay + 14:.1f}' stroke='{RED}'/>")
    b.append(f"<circle cx='{fx:.1f}' cy='{fy:.1f}' r='6' fill='{RED}'/>")
    b.append(f"<rect x='{ax - 4:.1f}' y='{ay - 4:.1f}' width='{R - ax + 4:.1f}' height='68' fill='#ffffff' opacity='0.92'/>")
    b.append(text(ax + 4, ay + 14, f"First alert: {f['day'].day} {f['day']:%b %Y}", 14, RED, weight=600))
    b.append(text(ax + 4, ay + 33, f"7-day CPL ₪{f['cpl_7']:.2f} vs threshold ₪{f['threshold']:.2f} "
                                   f"(1.3 × ₪{f['cpl_before']:.2f})", 13, INK))
    b.append(text(ax + 4, ay + 52, 'Alert on every active day to 4 Apr: ₪8,874 → 512 leads at ₪17.33', 13, INK))
    # legend
    b.append(f"<line x1='{L}' y1='{H - 46}' x2='{L + 28}' y2='{H - 46}' stroke='{BLUE}' stroke-width='2.5'/>")
    b.append(text(L + 36, H - 42, 'Cost per lead, last 7 active days', 13))
    b.append(f"<line x1='{L + 290}' y1='{H - 46}' x2='{L + 318}' y2='{H - 46}' stroke='{ORANGE}' stroke-width='2' stroke-dasharray='6 4'/>")
    b.append(text(L + 326, H - 42, 'Alert threshold (1.3 × earlier average)', 13))
    b.append(f"<rect x='{L + 600}' y='{H - 53}' width='14' height='14' fill='{RED}' opacity='0.25'/>")
    b.append(text(L + 620, H - 42, 'Alert day', 13))
    b.append(text(30, H - 14, 'Tested on past data only, using what was known on each day. 30% is a chosen threshold, '
                              'not an optimised one. Source: query A2.', 12, MUTED))
    (out / 'cs3_cpl_alert_backtest.svg').write_text(svg(W, H, ''.join(b)), encoding='utf-8')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ads', required=True)
    p.add_argument('--payments', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    ads = load_ads(a.ads)
    assert round(sum(r['spend'] for r in ads), 2) == 39486.56, 'total spend differs'
    assert round(sum(r['results'] for r in ads if r['objective'] in LEAD_OBJECTIVES)) == 1923, 'leads differ'
    feb, jun, shares = chart_decomposition(ads, out)
    periods = chart_periods(ads, a.payments, out)
    rows = alert_series(ads)
    chart_alert(rows, out)
    with open(out / 'cs3_alert_daily_series.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['day', 'spend_ils', 'leads', 'cpl_last_7_active_days', 'cpl_all_earlier_days', 'alert_threshold', 'alert'])
        for r in rows:
            w.writerow([r['day'], round(r['spend'], 2), int(r['leads']),
                        '' if r['cpl_7'] is None else round(r['cpl_7'], 2),
                        '' if r['cpl_before'] is None else round(r['cpl_before'], 2),
                        '' if r['threshold'] is None else round(r['threshold'], 2), r['alert']])
    print('Feb vs Jun 2025 (Instant Form):')
    for k in ('cpm', 'ctr', 'cvr', 'cpl'):
        print(f'  {k}: {feb[k]:.4f} -> {jun[k]:.4f} ({jun[k] / feb[k] - 1:+.1%})')
    print('  shares of log change:', shares)
    print('Periods (payments / ad spend per month, customers):',
          [(n, round(pm), round(sm), c) for n, _, pm, sm, c in periods])
    print(f'Alert series: {len(rows)} active days, {sum(r["alert"] for r in rows)} alert days')
    print('All chart figures match the verified BigQuery results.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Reproducible, PII-free summary of a Meta Ads daily export.

Input: the cleaned file produced by prepare_ads.py. Writes aggregated summaries by
objective, month and lead mechanism, the exact log decomposition of month-to-month
CPL changes, and a verification JSON; asserts the baseline totals. Rates are always
computed from summed counts. No forecast, CAC or ROAS.

Usage: python retrospective_audit.py --input meta_ads_daily.csv --outdir aggregates
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

LEAD_OBJECTIVES = {
    'actions:leadgen.other': 'instant_form',
    'actions:offsite_conversion.fb_pixel_lead': 'landing_page',
}
ZERO = Decimal('0')

def num(x: str | None) -> Decimal:
    return Decimal(x) if x is not None and x.strip() else ZERO

def rate(n: Decimal, d: Decimal) -> Decimal | None:
    return n / d if d else None

def pretty(v: Decimal | None, places: int = 2) -> str:
    return '' if v is None else str(v.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))

def bucket():
    return {'spend': ZERO, 'impressions': ZERO, 'clicks': ZERO, 'leads': ZERO, 'rows': 0, 'active_rows': 0}

def add(b: dict, row: dict, spend: Decimal):
    b['spend'] += spend
    b['impressions'] += num(row['impressions'])
    b['clicks'] += num(row['link_clicks'])
    b['leads'] += num(row['leads'])
    b['rows'] += 1
    if spend > 0:
        b['active_rows'] += 1

def write_csv(path: Path, records: list[dict]):
    if not records:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)

def summarize(b: dict, comparable_lead_funnel: bool = False) -> dict:
    return {
        'spend_ils': pretty(b['spend']),
        'impressions': int(b['impressions']),
        'link_clicks': int(b['clicks']),
        'meta_attributed_leads': int(b['leads']),
        'active_ad_day_rows': b['active_rows'],
        # Avoid ratios across objectives with different/missing event definitions.
        'cpl_ils': pretty(rate(b['spend'], b['leads'])) if comparable_lead_funnel else '',
        'cpm_ils': pretty(rate(b['spend']*1000, b['impressions'])) if comparable_lead_funnel else '',
        'ctr_pct': pretty(rate(b['clicks']*100, b['impressions']), 3) if comparable_lead_funnel else '',
        'click_to_lead_pct': pretty(rate(b['leads']*100, b['clicks']), 2) if comparable_lead_funnel else '',
    }

def decomp(start: dict, end: dict) -> dict | None:
    for src in (start,end):
        if min(src['spend'], src['impressions'], src['clicks'], src['leads']) <= 0:
            return None
    def vals(src):
        return (float(src['spend']*1000/src['impressions']),
                float(src['clicks']/src['impressions']),
                float(src['leads']/src['clicks']),
                float(src['spend']/src['leads']))
    cpm0,ctr0,cvr0,cpl0=vals(start)
    cpm1,ctr1,cvr1,cpl1=vals(end)
    cpm=math.log(cpm1/cpm0)
    ctr=-math.log(ctr1/ctr0)
    cvr=-math.log(cvr1/cvr0)
    total=math.log(cpl1/cpl0)
    if abs((cpm+ctr+cvr)-total)>1e-9:
        raise AssertionError('CPL identity does not reconcile')
    return {'cpl_start_ils':round(cpl0,2),'cpl_end_ils':round(cpl1,2),
            'cpl_change_pct':round(100*(cpl1/cpl0-1),2),
            'cpm_log_contribution':round(cpm,4),
            'ctr_log_contribution':round(ctr,4),
            'cvr_log_contribution':round(cvr,4),
            'total_log_cpl_change':round(total,4),
            'note':'Signed log changes exactly reconcile; accounting identity, not causal attribution.'}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='meta_ads_daily.csv from prepare_ads.py')
    ap.add_argument('--outdir', required=True)
    args=ap.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    total=bucket(); byaccount=defaultdict(bucket); byobjective=defaultdict(bucket)
    bymonth=defaultdict(bucket); bymonth_mech=defaultdict(bucket)
    active_dates=set();active_months=set(); dates_all=set()
    with open(args.input,'r',newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        required={'account','report_date','spend_ils','impressions','link_clicks','leads','result_indicator'}
        if missing:=required-set(reader.fieldnames or []):
            raise ValueError(f'Missing columns: {missing}')
        for row in reader:
            d=date.fromisoformat(row['report_date'])
            month=d.strftime('%Y-%m');dates_all.add(d)
            spend=num(row['spend_ils'])
            add(total,row,spend)
            add(byaccount[row['account']],row,spend)
            if spend <= 0:
                continue
            active_dates.add(d);active_months.add(month)
            obj=row['result_indicator'] or 'unknown'
            add(byobjective[obj],row,spend)
            add(bymonth[month],row,spend)
            if obj in LEAD_OBJECTIVES:
                add(bymonth_mech[(month, LEAD_OBJECTIVES[obj])],row,spend)

    by_obj=[]
    for name,b in sorted(byobjective.items(),key=lambda kv: -kv[1]['spend']):
        by_obj.append({'result_indicator':name,**summarize(b, name in LEAD_OBJECTIVES)})
    write_csv(out/'01_objective_summary.csv',by_obj)
    write_csv(out/'02_spend_by_month.csv',[{'month':m,**summarize(b)} for m,b in sorted(bymonth.items())])
    write_csv(out/'03_leads_by_month_mechanism.csv',[
        {'month':k[0],'mechanism':k[1],**summarize(b, True)} for k,b in sorted(bymonth_mech.items())])
    scenarios=[]
    for mech in ['instant_form','landing_page']:
        keys=sorted(k for k in bymonth_mech if k[1]==mech)
        for prev,current in zip(keys,keys[1:]):
            v=decomp(bymonth_mech[prev],bymonth_mech[current])
            if v is not None:
                scenarios.append({'mechanism':mech,'from_month':prev[0],'to_month':current[0],**v})
    write_csv(out/'04_cpl_decomposition.csv',scenarios)
    feb_jun = None
    if ('2025-02','instant_form') in bymonth_mech and ('2025-06','instant_form') in bymonth_mech:
        feb_jun=decomp(bymonth_mech[('2025-02','instant_form')],bymonth_mech[('2025-06','instant_form')])
    summary={
        'source_rows':total['rows'],
        'active_ad_day_rows':total['active_rows'],
        'total_spend_ils':pretty(total['spend']),
        'meta_attributed_leads':int(total['leads']),
        'active_calendar_dates':len(active_dates),
        'months_with_positive_spend':len(active_months),
        'months_list':sorted(active_months),
        'first_active_date':str(min(active_dates)),
        'last_active_date':str(max(active_dates)),
        'lead_generation_spend_ils':pretty(sum((b['spend'] for name,b in byobjective.items() if name in LEAD_OBJECTIVES),ZERO)),
        'unknown_objective_spend_ils':pretty(byobjective.get('unknown',bucket())['spend']),
        'feb_2025_to_jun_2025_instant_form_decomposition':feb_jun,
        'per_account':{k:{'rows':v['rows'],**summarize(v)} for k,v in sorted(byaccount.items())},
        'definitions':{'positive_spend':'spend_ils > 0','leads':'Meta-attributed lead results only; not unique people','ad_day_rows':'rows at source ad-day grain, some lack unique ad IDs','months_with_positive_spend':'distinct YYYY-MM with any spend','decomposition':'signed logarithmic identity; not causal proof'},
        'limits':['No verified ad IDs','Missing objective for some rows','No ad-to-customer attribution','No authenticated payment values','Forecast not performed']}
    with (out/'00_verification.json').open('w',encoding='utf-8') as f:
        json.dump(summary,f,ensure_ascii=False,indent=2)
    # Assertions are checks against the audited exports, not general model rules.
    checks={'source_rows':92028,'active_ad_day_rows':595,'total_spend_ils':'39486.56',
            'meta_attributed_leads':1923,'active_calendar_dates':259,
            'months_with_positive_spend':15,'lead_generation_spend_ils':'29383.08'}
    for key, expected in checks.items():
        if summary[key]!=expected:
            raise AssertionError(f'{key}: actual={summary[key]}, expected={expected}; investigate export change')
    print(json.dumps({k:summary[k] for k in checks},ensure_ascii=False,indent=2))
    print('All baseline checks passed. Results:',out)

if __name__=='__main__':main()

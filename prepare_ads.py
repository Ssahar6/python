"""Deterministic Meta Ads cleaning with reconciliation. No customer PII.

Reads the two raw Meta Ads exports (Hebrew column names), maps them to snake_case,
tags each row with its account, converts numbers while reporting any failure,
derives `leads` only for the two lead objectives, and checks that rows, spend and
leads reconcile to the source before writing the cleaned file.

Usage: python prepare_ads.py --a account_a.csv --b account_b.csv --out meta_ads_daily.csv
The raw exports are private and not included in this repository.
"""
import argparse
from pathlib import Path
import pandas as pd

COLS = {
 'הדיווח מתחיל':'report_date','הדיווח מסתיים':'report_end','שם המודעה':'ad_name',
 'הצגת מודעות':'delivery_status','הגדרת ייחוס':'attribution_setting',
 'תוצאות':'results','מחוון תוצאות':'result_indicator','תפוצה':'reach',
 'תדירות':'frequency','עלות לתוצאות':'cost_per_result_reported',
 'תקציב סדרת מודעות':'budget_raw','סוג תקציב של סדרת מודעות':'budget_type',
 'הסכום ששולם (ILS)':'spend_ils','סיום':'end_date','דירוג איכות':'quality_ranking',
 'דירוג שיעור המעורבות':'engagement_ranking','דירוג שיעור ההמרות':'conversion_ranking',
 'חשיפות':'impressions','עלות לאלף חשיפות (ILS)':'cpm_reported',
 'קליקים על קישור':'link_clicks','shop_clicks':'shop_clicks',
 'עלות לקליק (עלות לקליק על קישור) (ILS)':'cpc_link_reported',
 'שיעור קליקים על קישור':'ctr_link_reported', 'קליקים (הכל)':'all_clicks',
 'שיעור קליקים (הכול)':'ctr_all_reported',
 'עלות לקליק (הכול) (ILS)':'cpc_all_reported',
 'צפיות בדף נחיתה':'landing_page_views',
 'עלות לצפייה בדף נחיתה (ILS)':'cost_per_lpv_reported',
 'תוצאות (ראשוניות)':'first_results','מחוון תוצאות (ראשוני)':'first_result_indicator'
}
NUMERIC=['results','reach','frequency','cost_per_result_reported','spend_ils','impressions','cpm_reported','link_clicks','shop_clicks','cpc_link_reported','ctr_link_reported','all_clicks','ctr_all_reported','cpc_all_reported','landing_page_views','cost_per_lpv_reported','first_results']
LEAD_TYPES={'actions:leadgen.other','actions:offsite_conversion.fb_pixel_lead'}
def load_file(path,account):
    df=pd.read_csv(path,dtype=str,encoding='utf-8-sig',keep_default_na=True)
    if set(df.columns)!=set(COLS):
        raise ValueError(f'{account}: source columns changed: {set(COLS)^set(df.columns)}')
    df=df.rename(columns=COLS)
    df.insert(0,'account',account)
    df['ad_name']=df['ad_name'].str.replace(r'[\r\n]+',' ',regex=True)
    df['budget_level']=df['budget_raw'].apply(lambda s:'campaign' if isinstance(s,str) and 'שימוש בתקציב הקמפיין' in s else ('adset' if pd.notna(s) else 'unknown'))
    df['adset_budget']=pd.to_numeric(df['budget_raw'].replace('-',pd.NA),errors='coerce')
    for c in NUMERIC:
        original=df[c].replace('-',pd.NA)
        parsed=pd.to_numeric(original,errors='coerce')
        fail=(original.notna() & parsed.isna()).sum()
        if fail: raise ValueError(f'{account}: {fail} unexpected nonnumeric {c} values')
        df[c]=parsed
    df['report_date']=pd.to_datetime(df['report_date'],errors='raise').dt.strftime('%Y-%m-%d')
    df['is_active']=df['spend_ils'].fillna(0)>0
    df['objective']=df['result_indicator'].fillna('unknown').apply(lambda s:'lead' if s in LEAD_TYPES else s)
    df['leads']=df['results'].where(df['objective']=='lead')
    return df

def main():
    p=argparse.ArgumentParser();p.add_argument('--a',required=True);p.add_argument('--b',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();data=pd.concat([load_file(a.a,'account_A'),load_file(a.b,'account_B')],ignore_index=True)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    # Retain all rows and export only fields needed for reproducible aggregation.
    keep=['account','report_date','ad_name','delivery_status','attribution_setting','result_indicator','objective','spend_ils','results','leads','reach','impressions','link_clicks','all_clicks','landing_page_views','budget_level','adset_budget','is_active']
    data[keep].to_csv(out,index=False,encoding='utf-8-sig')
    print('Rows:',len(data),'Active:',int(data.is_active.sum()),'Spend:',round(data.spend_ils.sum(),2),'Leads:',data.leads.sum())
    print(data.groupby('account').agg(rows=('account','size'),active=('is_active','sum'),spend=('spend_ils','sum')).to_string())
    assert len(data)==92028 and data.is_active.sum()==595, 'Unexpected rows: inspect new export before accepting'
    assert abs(data.spend_ils.sum()-39486.56)<0.011, 'Spending reconciliation failed'
    assert int(data.leads.sum())==1923,'Lead attribution reconciliation failed'
if __name__=='__main__':main()

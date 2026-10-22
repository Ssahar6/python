"""Builds an anonymous file of student payments from the accounting export. No customer PII.

Reads the receipts export (Hebrew columns, Windows-1255), keeps only the training and
mentorship receipts, removes each credit note together with the receipt it cancels
(they were technical corrections), replaces customer names with anonymous IDs and drops
the free-text notes. Amounts exclude VAT.

Usage: python prepare_payments.py --input receipts_export.csv --out student_payments.csv
The raw export is private and not included in this repository.
"""
import argparse
import csv
from datetime import datetime

METHODS = {'העברה בנקאית': 'bank_transfer', 'סליקת אשראי': 'credit_card',
           'מזומן': 'cash', 'כללי': 'other'}


def doc_number(text):
    # "חשבון/קבלה / 40081" -> "40081"
    return text.split('/')[-1].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()

    with open(a.input, encoding='cp1255', newline='') as f:
        rows = list(csv.DictReader(f))

    credits = [r for r in rows if 'זיכוי' in r['שם הכרטיס']]
    cancelled = {doc_number(r['מסמכים מקושרים']) for r in credits}
    receipts = [r for r in rows if 'זיכוי' not in r['שם הכרטיס'] and r['מספר'] not in cancelled]

    receipts.sort(key=lambda r: datetime.strptime(r['תאריך'], '%d/%m/%Y'))
    ids = {}
    out = []
    for r in receipts:
        name = r['לקוח/ה'].strip()
        ids.setdefault(name, f'C{len(ids) + 1:02d}')
        out.append({
            'payment_date': datetime.strptime(r['תאריך'], '%d/%m/%Y').strftime('%Y-%m-%d'),
            'amount_ils': float(r['סכום'].replace(',', '')),
            'payment_method': METHODS[r['סוג תשלום']],
            'customer_id': ids[name],
        })

    gross = sum(float(r['סכום'].replace(',', '')) for r in rows)
    net = sum(r['amount_ils'] for r in out)
    assert len(credits) == len(cancelled) == 4, 'every credit must cancel exactly one receipt'
    assert abs(gross - net) < 0.01, 'removing credits and their receipts must not change the net total'

    with open(a.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f'{len(out)} payments · {len(ids)} customers · net ₪{net:,.2f}')


if __name__ == '__main__':
    main()

"""Reconciles the anonymous student payments file before it is used in any finding.

Checks: row and customer counts, date range, missing or non-positive values, repeated
payments, payments per analysis period, customers who appear in more than one period,
and payments outside the analysed periods. Prints every result; asserts the totals.

Usage: python check_payments.py --input student_payments.csv
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import date

PERIODS = [
    ('1. Before lead campaigns', date(2024, 6, 1), date(2025, 1, 31)),
    ('2. Lead campaigns', date(2025, 2, 1), date(2025, 8, 31)),
    ('3. After lead campaigns', date(2025, 9, 1), date(2026, 3, 31)),
]


def period_of(d):
    for name, start, end in PERIODS:
        if start <= d <= end:
            return name
    return 'outside periods'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    a = p.parse_args()

    with open(a.input, encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))

    missing = [r for r in rows if not r['payment_date'] or not r['amount_ils'] or not r['customer_id']]
    for r in rows:
        r['d'] = date.fromisoformat(r['payment_date'])
        r['amt'] = float(r['amount_ils'])
        r['period'] = period_of(r['d'])
    non_positive = [r for r in rows if r['amt'] <= 0]
    repeats = Counter((r['customer_id'], r['payment_date'], r['amt']) for r in rows)
    repeats = {k: n for k, n in repeats.items() if n > 1}

    total = sum(r['amt'] for r in rows)
    customers = {r['customer_id'] for r in rows}
    print(f'payments: {len(rows)}')
    print(f'distinct customers: {len(customers)}')
    print(f'total ILS: {total:,.2f}')
    print(f'average per paying customer: {total / len(customers):,.2f}')
    print(f'date range: {min(r["d"] for r in rows)} to {max(r["d"] for r in rows)}')
    print(f'rows with a missing value: {len(missing)}')
    print(f'rows with amount <= 0: {len(non_positive)}')
    print(f'same customer, date and amount more than once: {repeats or "none"}')

    by_period = defaultdict(list)
    for r in rows:
        by_period[r['period']].append(r)
    periods_per_customer = defaultdict(set)
    for r in rows:
        periods_per_customer[r['customer_id']].add(r['period'])
    for name in [p[0] for p in PERIODS] + ['outside periods']:
        g = by_period.get(name, [])
        print(f'{name}: {len(g)} payments, {len({r["customer_id"] for r in g})} customers, '
              f'ILS {sum(r["amt"] for r in g):,.2f}')
    multi = {c: sorted(ps) for c, ps in periods_per_customer.items() if len(ps) > 1}
    print(f'customers in more than one period: {multi or "none"}')

    assert len(rows) == 50 and len(customers) == 38, 'unexpected counts: inspect the file'
    assert abs(total - 142234) < 0.01, 'unexpected total'
    assert not missing and not non_positive and not by_period.get('outside periods'), 'invalid rows'
    print('All payment checks passed.')


if __name__ == '__main__':
    main()

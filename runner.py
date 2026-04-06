import csv
import json
import sys
from pathlib import Path

from matcher.matcher import match_invoices


def run(json_path: str = '20250901.json') -> dict:
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)['data']

    result = match_invoices(data['deliveries'], data['vat_invoices'])

    # Print stats
    print('=== STATS ===')
    for k, v in result['stats'].items():
        print(f'  {k}: {v}')

    print('\n=== MATCHES (delivery_id -> invoice_ids) ===')
    for did, inv_ids in sorted(result['matches'].items()):
        print(f'  delivery {did}: {inv_ids}')

    print(f'\n=== UNMATCHED INVOICE IDs (first 10) ===')
    print(f'  {result["unmatched_invoice_ids"][:10]} ...')

    # Save JSON
    out_json = Path(json_path).parent / 'output.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'\nSaved → {out_json}')

    # Save CSV
    out_csv = Path(json_path).parent / 'output.csv'
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['delivery_id', 'invoice_id'])
        for did, inv_ids in sorted(result['matches'].items()):
            for inv_id in inv_ids:
                writer.writerow([did, inv_id])
    print(f'Saved → {out_csv}')

    return result


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '20250901.json'
    run(path)

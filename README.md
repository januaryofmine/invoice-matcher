# invoice-matcher

Match VAT invoices to delivery records using deterministic logic.

## Problem

Given a list of **deliveries** (ERP records) and a large list of **VAT invoices**, find which invoices belong to which delivery. Most invoices won't match any delivery.

## Matching Logic

Four steps, in order:

1. **Plate lookup** — normalize truck plate (strip `-`, `.`, spaces, uppercase) and index deliveries by plate. ~97% of invoices are dropped here.
2. **Date filter** — invoice date must fall within `[pickup_date - 1, dropoff_date + 1]`.
3. **Location tiebreak** — when two deliveries share the same plate, match invoice `(Delivery address)` against delivery `dropoff_location` using keyword overlap. This is the primary tiebreak signal.
4. **Weight tiebreak** — fallback when location gives no signal. Assign to whichever delivery's weight (tons) is closest to the invoice's net weight (kg ÷ 1000).

## Project Structure

```
invoice-matcher/
├── matcher/
│   ├── normalizer.py   # normalize_plate, parse_date, parse_weight_kg
│   ├── indexer.py      # build delivery index (plate → deliveries)
│   └── matcher.py      # core matching logic
├── tests/
│   ├── fixtures.py         # mock data extracted from 20250901.json
│   ├── test_normalizer.py
│   ├── test_indexer.py
│   ├── test_matcher.py
│   └── test_integration.py # requires 20250901.json at project root
├── runner.py           # entry point — loads JSON, runs match, saves output
└── 20250901.json       # input data (place here before running)
```

## Setup

```bash
git clone <repo>
cd invoice-matcher

python3 -m venv .venv
source .venv/bin/activate

pip install pytest
```

No other dependencies — only Python stdlib.

## Usage

Place `20250901.json` at the project root, then:

```bash
python3 runner.py
# or specify a custom path:
python3 runner.py path/to/data.json
```

Output files written to the same directory as the input:

| File | Contents |
|---|---|
| `output.json` | Full result: matches + unmatched IDs + stats |
| `output.csv` | Flat table: `delivery_id, invoice_id` |

## Run Tests

```bash
# All tests (unit + integration)
python3 -m pytest tests/ -v

# Unit tests only (no data file needed)
python3 -m pytest tests/ -v --ignore=tests/test_integration.py
```

Integration tests auto-skip if `20250901.json` is not present.

## Results (20250901.json)

| Metric | Value |
|---|---|
| Total invoices | 680 |
| Invoices assigned to a delivery | 20 |
| Invoices with no match | 660 |
| Deliveries covered | 10 / 10 |

## Test Coverage

54 tests across 4 files:

| File | What it tests |
|---|---|
| `test_normalizer.py` | Plate normalization, date parsing, weight edge cases (None, NaN) |
| `test_indexer.py` | Index building, duplicate plate grouping, missing truck handling |
| `test_matcher.py` | Plate miss, date window, multi-invoice assignment, location tiebreak, weight tiebreak |
| `test_integration.py` | Full file run, known match assertions, location tiebreak on 72207/72208, no double-assignment |

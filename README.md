# invoice-matcher

Match VAT invoices to delivery records using a unified pipeline, with LLM-assisted province extraction for ambiguous cases.

## Problem

Given a list of **deliveries** (ERP records) and a large list of **VAT invoices**, find which invoices belong to which delivery. Most invoices won't match any delivery.

## Matching Pipeline

Every invoice goes through up to 4 steps:

**Step 1: Plate check**
- Has plate + matches a delivery → candidates → step 2
- Has plate + matches nothing → `unmatched`
- No plate → `manual_review (no_plate)`

**Step 2: Date window `[pickup_date - 1, dropoff_date + 1]`**
- 1 candidate passes → assign ✓
- >1 candidates pass → step 3a
- 0 candidates pass → `manual_review (date_out_of_window)`

**Step 3a: LLM province check**
- Extract province from invoice `(Delivery address)` and each delivery `dropoff_location` via LLM (batched, 1 API call)
- Filter candidates to same province as invoice
- Candidates with no province data are kept (not dropped) to avoid false negatives
- 1 candidate remaining → assign ✓
- >1 candidates remaining → step 3b
- 0 candidates remaining → `manual_review (province_mismatch)`

**Step 3b: Token overlap address match**
- Tokenize invoice `(Delivery address)` and delivery `dropoff_location` with Vietnamese stopword filtering
- Pick candidate(s) with highest token overlap score
- 1 candidate remaining → assign ✓
- >1 candidates remaining → step 4
- 0 overlap → fallback to step 4

**Step 4: Weight tiebreak**
- Compare invoice `net_weight` (kg ÷ 1000) vs delivery `weight` (tons)
- 1 candidate closest → assign ✓
- All weights missing → `manual_review (unclear_details)`

**Output buckets:**
- `matches` — confirmed delivery ↔ invoice assignments
- `unmatched` — plate exists but no delivery found in system
- `manual_review` — could not be confidently assigned, needs human review

## Why LLM for province extraction?

Vietnamese addresses have no standard format — `TP. Hồ Chí Minh`, `Thành phố Hồ Chí Minh`, `TP.HCM` all refer to the same province. Rule-based normalization is fragile. LLM extracts provinces reliably in a single batched API call, keeping token cost minimal. LLM is only invoked when Step 2 leaves >1 candidate.

## Project Structure

```
invoice-matcher/
├── matcher/
│   ├── normalizer.py          # normalize_plate, parse_date, parse_weight_kg
│   ├── indexer.py             # build delivery index (plate → deliveries)
│   ├── province_extractor.py  # LLM-based province extraction (batched, 1 API call)
│   └── matcher.py             # unified matching pipeline
├── tests/
│   ├── fixtures.py            # mock data extracted from 20250901.json
│   ├── test_normalizer.py
│   ├── test_indexer.py
│   ├── test_matcher.py        # unit tests with mocked province extractor
│   └── test_integration.py
├── runner.py                  # entry point — loads JSON, runs match, saves output
├── debug_province.py          # debug script for province extraction tracing
└── 20250901.json              # input data (place here before running)
```

## Setup

```bash
git clone <repo>
cd invoice-matcher

python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install pytest
```

Create a `.env` file at project root:

```
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
source .env
python3 runner.py
# or specify a custom path:
python3 runner.py path/to/data.json
```

Output files written to the same directory as the input:

| File | Contents |
|---|---|
| `output.json` | Full result: matches + unmatched IDs + manual_review + stats |
| `output.csv` | Flat table: `delivery_id, invoice_id` |
| `manual_review.csv` | Invoices needing human review: `invoice_id, reason` |

## Run Tests

```bash
# Unit tests only (no data file or API key needed)
python3 -m pytest tests/ -v --ignore=tests/test_integration.py

# All tests including integration (requires data file + API key)
source .env
python3 -m pytest tests/ -v
```

Unit tests mock the province extractor — no API calls made.
Integration tests auto-skip if `20250901.json` or `ANTHROPIC_API_KEY` is missing.

## Manual Review Reason Codes

| Reason | Meaning |
|---|---|
| `no_plate` | Invoice has no truck plate |
| `date_out_of_window` | Invoice date outside delivery window |
| `province_mismatch` | No delivery dropoff matches invoice province |
| `unclear_details` | Multiple candidates remain after all tiebreaks |

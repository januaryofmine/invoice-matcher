# invoice-matcher-v2

Score-based invoice ↔ delivery matching pipeline with LLM resolution for ambiguous cases.

## Problem

Given a list of **deliveries** and a large list of **VAT invoices**, find which invoices belong to which delivery. Most invoices won't match any delivery in a given dataset.

## Pipeline

```
3,319 invoices
    │
    ▼
Stage 1: Candidate Generation  (plate + date filter)  → 127 relevant
    │
    ▼
Stage 2: Candidate Scoring     (address + weight)
    │
    ├─ gap ≥ 0.05 ────────────────────────────────────→ AUTO MATCH
    ├─ gap < 0.05 → LLM Resolution (~23 cases) ───────→ LLM MATCH
    │                                                 └─→ MANUAL REVIEW
    └─ 0 candidates ──────────────────────────────────→ NO MATCH
```

**Score formula:**
```
score = 0.7 * address_score + 0.3 * weight_score
```
- `address_score` — token overlap between invoice delivery address and dropoff description
- `weight_score` — ratio of invoice weight (kg→tons) to delivery weight; `None` if missing

When weight is missing, address carries full weight (`W_ADDR = 1.0` effectively).

## Project Structure

```
invoice-matcher-v2/
├── matcher/
│   ├── normalizer.py      # plate, date, weight normalization
│   ├── indexer.py         # build plate → deliveries index
│   ├── scorer.py          # address + weight scoring
│   ├── llm_resolver.py    # LLM semantic address matching
│   └── matcher.py         # unified pipeline
├── tests/
│   ├── fixtures.py        # mock data for unit tests
│   ├── test_normalizer.py
│   ├── test_indexer.py
│   ├── test_scorer.py
│   ├── test_matcher.py
│   └── test_integration.py  # requires data files + API key
├── runner.py              # entry point
└── .env                   # ANTHROPIC_API_KEY=sk-ant-...
```

## Setup

```bash
git clone <repo>
cd invoice-matcher-v2

python3 -m venv .venv
source .venv/bin/activate

pip install pytest
```

Create `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# With default filenames (large_set.json + large_set_vat.json)
source .env && python3 runner.py

# With custom paths
source .env && python3 runner.py path/to/deliveries.json path/to/invoices.json
```

**Output files** (written to same directory as input):

| File | Contents |
|---|---|
| `output.json` | Full results with score breakdown per invoice |
| `output.csv` | `delivery_id, invoice_id, confidence_score, method` |
| `manual_review.csv` | `invoice_id, top_candidate, score_gap, reason` |

## Tests

```bash
# Unit tests only (no data files or API key needed)
python3 -m pytest tests/ -v --ignore=tests/test_integration.py

# All tests (requires data files in working directory + API key)
source .env && python3 -m pytest tests/ -v
```

## Configurable Parameters

| Parameter | Default | Description |
|---|---|---|
| `DATE_WINDOW` | 1 day | Filter window around pickup/dropoff |
| `W_ADDR` | 0.7 | Address score weight |
| `W_WEIGHT` | 0.3 | Weight score weight |
| `CONFIDENCE_THRESHOLD` | 0.05 | Min gap to auto-match |
| `LLM_MODEL` | claude-haiku-4-5 | Model for semantic address matching |

## Results (large_set.json)

| Metric | Value |
|---|---|
| Total invoices | 3,319 |
| Invoices with no delivery match | ~3,185 |
| Invoices auto-matched | ~120 |
| Invoices resolved by LLM | ~7 |
| Invoices sent to manual review | ~7 |
| No plate | 75 |

# invoice-matcher

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

When weight is missing, address carries full weight (`w_addr = 1.0` effectively).

## Project Structure

```
invoice-matcher/
│
├── runner.py              # CLI entry point — I/O wiring only
│
├── core/
│   └── types.py           # All shared types (Single Source of Truth)
│
├── pipeline/
│   ├── normalizer.py      # plate, date, weight normalization
│   ├── indexer.py         # build plate → deliveries index
│   ├── scorer.py          # address + weight scoring
│   └── matcher.py         # orchestrate the 3-stage pipeline
│
├── adapters/
│   └── llm.py             # LLM fallback for ambiguous cases (Claude Haiku)
│
├── file_io/
│   ├── loader.py          # read delivery + invoice JSON files
│   └── writer.py          # write output.json, output.csv, manual_review.csv
│
├── tests/
│   ├── fixtures.py        # shared test data
│   ├── test_normalizer.py
│   ├── test_indexer.py
│   ├── test_scorer.py
│   ├── test_matcher.py
│   └── test_integration.py
│
├── invoice-ui/            # React/Vite dashboard (results viewer, deployed on Vercel)
│
├── upload_output.py       # upload output.json to Vercel Blob after each run
├── large_set.json         # input: delivery records
└── large_set_vat.json     # input: VAT invoice records
```

## Setup

```bash
git clone <repo>
cd invoice-matcher

python3 -m venv .venv
source .venv/bin/activate

pip install pytest
```

## Usage

```bash
# Set API key (only needed when use_llm=True, which is the default)
export ANTHROPIC_API_KEY=sk-ant-...

# With default filenames (large_set.json + large_set_vat.json)
python runner.py

# With custom paths
python runner.py path/to/deliveries.json path/to/invoices.json
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
pytest tests/ -v --ignore=tests/test_integration.py

# All tests (requires data files in working directory + API key)
ANTHROPIC_API_KEY=sk-ant-... pytest tests/ -v
```

## Configuration

All parameters live in `MatcherConfig` and `ScorerConfig` (`core/types.py`):

| Parameter | Default | Description |
|---|---|---|
| `date_window_days` | `1` | Days before pickup / after dropoff still valid |
| `scorer.w_addr` | `0.7` | Address score weight |
| `scorer.w_weight` | `0.3` | Weight score weight |
| `scorer.confidence_threshold` | `0.05` | Min gap to auto-match |
| `use_llm` | `True` | Whether to call Claude Haiku on ambiguous cases |

To run without LLM (e.g. in CI):
```python
from pipeline.matcher import match_invoices
from core.types import MatcherConfig

results = match_invoices(deliveries, invoices, MatcherConfig(use_llm=False))
```

## Results (large_set.json)

| Metric | Value |
|---|---|
| Total invoices | 3,319 |
| No plate | 75 |
| No delivery match | ~3,185 |
| Auto-matched (scoring) | ~120 |
| Resolved by LLM | ~7 |
| Sent to manual review | ~7 |

## Dashboard (invoice-ui)

Results are visualised in a React/Vite SPA deployed on Vercel. After each pipeline run, upload the output:

```bash
export BLOB_READ_WRITE_TOKEN=...
python upload_output.py
```

See `invoice-ui/` for frontend source and `Walkthrough.md` for full architecture details.

# Invoice Matcher — Technical Walkthrough
---

## 1. Business Context

Vietnamese logistics companies issue VAT invoices and record deliveries in separate systems. This pipeline reconciles the two: given a batch of deliveries and a batch of VAT invoices, it determines which invoice belongs to which delivery.

A successful match allows the finance team to close the books on a delivery and identify discrepancies (invoices with no matching delivery, or deliveries with no invoice).

**Typical dataset scale:** ~3,000 invoices, ~600 deliveries per run.
**Expected match rate:** ~3–5% — most invoices belong to deliveries outside the current batch.

---

## 2. Repository Structure

```
invoice-matcher/
│
├── runner.py                  # CLI entry point — I/O wiring only
│
├── core/
│   └── types.py               # All shared types (Single Source of Truth)
│
├── pipeline/
│   ├── normalizer.py          # Pure data-cleaning functions
│   ├── indexer.py             # Build plate → deliveries lookup index
│   ├── scorer.py              # Score each (invoice, delivery) pair
│   └── matcher.py             # Orchestrate the 3-stage pipeline
│
├── adapters/
│   └── llm.py                 # LLM fallback for ambiguous cases (Claude Haiku)
│
├── file_io/
│   ├── loader.py              # Read delivery + invoice JSON files
│   └── writer.py              # Write output.json, output.csv, manual_review.csv
│
├── tests/                     # Pytest test suite
│   ├── fixtures.py            # Shared test data
│   ├── test_normalizer.py
│   ├── test_indexer.py
│   ├── test_scorer.py
│   ├── test_matcher.py
│   └── test_integration.py
│
├── invoice-ui/                # React/Vite dashboard (results viewer, Vercel)
│   ├── app.jsx
│   ├── humanreason.js         # Translate technical status → plain English
│   └── api/output.js          # Vercel serverless function — proxies Blob data
│
├── upload_output.py           # Upload output.json to Vercel Blob after each run
├── large_set.json             # Input: delivery records
├── large_set_vat.json         # Input: VAT invoice records
└── output.json                # Output: match results (gitignored)
```

---

## 3. Data Shapes

### 3.1 Input — Delivery record (`large_set.json`)

```json
{
  "id": 67131,
  "pickup_date": "2025-07-04",
  "dropoff_date": "2025-07-05",
  "weight": 15.28,
  "dropoff_location": {
    "name": "CÔNG TY TNHH NGỌC TRƯỜNG",
    "description": "26 Đường Trần Khánh Dư, Phường 8, Đà Lạt, Lâm Đồng"
  },
  "computed_data": {
    "truck": {
      "plate": "49H-019.36"
    }
  }
}
```

### 3.2 Input — VAT invoice record (`large_set_vat.json`)

```json
{
  "id": 34917610,
  "truck_plate": "49H-019.36",
  "metadata": {
    "(Date)": "04/07/2025",
    "(Delivery address)": "26 Trần Khánh Dư, Phường 8, Đà Lạt, Lâm Đồng"
  },
  "sku_data": {
    "net_weight": 15280
  }
}
```

### 3.3 Output — Match result (`output.json`)

```json
{
  "invoice_id": 34917610,
  "status": "AUTO_MATCH",
  "matched_delivery_id": 67131,
  "confidence_score": 0.7862,
  "score_gap": 1.0,
  "reason": "single candidate after filtering",
  "top_candidates": [
    {
      "delivery_id": 67131,
      "delivery_name": "CÔNG TY TNHH NGỌC TRƯỜNG",
      "delivery_description": "26 Đường Trần Khánh Dư, Phường 8, Đà Lạt",
      "score": 0.7862,
      "reasons": {
        "address_score": 0.8571,
        "weight_score": 0.6208
      }
    }
  ]
}
```

---

## 4. Pipeline — End-to-End Flow

```
runner.py
│
├── load_deliveries(path)       → list[dict]
├── load_invoices(path)         → list[dict]
│
└── match_invoices(deliveries, invoices, config)
    │
    ├── [One-time]  build_delivery_index(deliveries)
    │               → dict[plate → list[DeliveryEntry]]
    │
    └── [Per invoice]
        │
        ├── Stage 0 — Guards
        │   ├── No plate on invoice?         → NO_PLATE
        │   └── Plate not in any delivery?   → NO_MATCH
        │
        ├── Stage 1 — Candidate Generation
        │   └── _get_candidates(date, plate, index, window)
        │       └── Filter by: date within [pickup-1d, dropoff+1d]
        │           └── No candidates?       → NO_MATCH
        │
        ├── Stage 2 — Scoring
        │   └── score_all_candidates(address, weight, candidates)
        │       ├── address_score: token overlap ratio
        │       ├── weight_score:  min/max ratio (None if missing)
        │       └── total = 0.7 × addr + 0.3 × weight
        │
        └── Stage 3 — Decision
            ├── Single candidate?            → AUTO_MATCH
            ├── Gap ≥ 0.05?                  → AUTO_MATCH
            ├── Gap < 0.05 + LLM enabled?   → call Claude Haiku
            │   ├── Confidence high/medium? → LLM_MATCH
            │   └── Confidence low/failed?  → MANUAL_REVIEW
            └── LLM disabled?               → MANUAL_REVIEW
```

---

## 5. Module Responsibilities

### `core/types.py`
Central type definitions. **Single source of truth** for all domain types.

| Type | Purpose |
|------|---------|
| `DeliveryEntry` | TypedDict — normalized delivery ready for matching |
| `MatchStatus` | Enum of all possible invoice outcomes |
| `InvoiceResult` | Dataclass — complete result for one invoice |
| `ScorerConfig` | Scoring weights and auto-match threshold |
| `MatcherConfig` | Top-level pipeline configuration |

No logic. No I/O. Import-only.

---

### `pipeline/normalizer.py`
Pure functions — no side effects, no I/O.

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `normalize_plate` | `"62F-003.94"` | `"62F00394"` | Canonical plate key |
| `parse_date` | `"01/07/2025"` | `datetime` | Handles DD/MM/YYYY and ISO |
| `parse_weight_kg` | `sku_data dict` | `float` | Invoice weight in kg |
| `parse_weight_tons` | `delivery dict` | `float \| None` | Delivery weight in tons |
| `normalize_text` | raw address | lowercase, no punct | Pre-tokenization |
| `tokenize` | address string | `set[str]` | Token set for overlap math |

All functions return safe defaults (None / 0.0 / empty set) on bad input — the pipeline degrades gracefully rather than crashing on dirty data.

---

### `pipeline/indexer.py`
Builds the plate lookup index — called once before the main loop.

```
build_delivery_index(deliveries)
│
├── For each delivery:
│   ├── Extract truck.plate from computed_data.truck
│   ├── normalize_plate(plate) → canonical key
│   └── _build_entry(delivery) → DeliveryEntry (normalized, flat)
│
└── Returns: dict[str, list[DeliveryEntry]]
```

**Why an index?** Without it, every invoice would scan all deliveries linearly — O(n_invoices × n_deliveries). The index makes candidate lookup O(1) average case.

---

### `pipeline/scorer.py`
Computes a confidence score for every (invoice, delivery) pair.

**Scoring formula:**
```
total_score = 0.7 × address_score + 0.3 × weight_score
```

**Address score** — token overlap ratio:
```
score = |invoice_tokens ∩ dropoff_tokens| / |invoice_tokens|
```
Uses both `dropoff_name` and `dropoff_description` for maximum coverage.

**Weight score** — symmetric ratio:
```
score = min(inv_tons, del_tons) / max(inv_tons, del_tons)
```
Returns `None` when either weight is missing; the address weight is promoted to 1.0 in that case so candidates are still comparable.

---

### `adapters/llm.py`
Falls back to Claude Haiku when rule-based scoring is ambiguous.

**Three separated concerns (SRP):**

| Function | Responsibility |
|----------|---------------|
| `_build_prompt()` | Construct the LLM prompt — pure, no I/O |
| `_call_api()` | HTTP transport — no business logic |
| `_parse_response()` | Map LLM JSON → domain dict — pure, no I/O |
| `resolve()` | Orchestrate the above three |

**LLMResolver Protocol (DIP):**
`matcher.py` types its resolver parameter as `LLMResolver` — a structural Protocol. This means tests can pass a plain function stub without inheriting from a class, and the real HTTP implementation can be swapped for any other resolver without changing `matcher.py`.

**When is the LLM called?**
Only when `score_gap < confidence_threshold` (default 0.05) — typically 20–44 invoices per run. The model receives the top-3 candidates and returns the best match with a confidence level.

---

### `pipeline/matcher.py`
Orchestrates the three stages. Imports from all other modules; nothing imports from it except `runner.py`.

**Dependency injection:**
```python
def match_invoices(
    deliveries, invoices,
    config=None,
    llm_resolver: LLMResolver = default_llm_resolve,  # injectable
)
```
Passing `llm_resolver=my_stub` in tests avoids real API calls entirely.

---

### `file_io/loader.py` and `file_io/writer.py`
I/O only — no matching logic.

| Function | Responsibility |
|----------|---------------|
| `load_deliveries(path)` | Read + parse delivery JSON; validate shape |
| `load_invoices(path)` | Read + parse invoice JSON; validate shape |
| `save_results(results, dir)` | Write output.json, output.csv, manual_review.csv |

### `runner.py`
Thin CLI entry point — wires `file_io` + `pipeline` together, adds logging.

Uses `logging` throughout (not `print`) so output level is configurable.

---

## 6. SOLID Principles Applied

| Principle | Where |
|-----------|-------|
| **S**ingle Responsibility | Each module has one job: normalize / index / score / resolve / orchestrate / I/O |
| **O**pen/Closed | Add a new status by adding a branch in `_make_decision`; no other file changes |
| **L**iskov Substitution | `LLMResolver` Protocol — any callable with the right signature satisfies it |
| **I**nterface Segregation | `LLMResolver` Protocol is minimal (one `__call__` method) — callers aren't forced to depend on HTTP details |
| **D**ependency Inversion | `matcher.py` depends on the `LLMResolver` Protocol; `runner.py` depends on `match_invoices` signature — not on concrete implementations |

---

## 7. Configuration

All tuneable parameters live in `MatcherConfig` and `ScorerConfig` (`core/types.py`):

| Parameter | Default | Effect |
|-----------|---------|--------|
| `date_window_days` | `1` | Days before pickup / after dropoff an invoice is still valid |
| `scorer.w_addr` | `0.7` | Address weight in scoring formula |
| `scorer.w_weight` | `0.3` | Weight weight in scoring formula |
| `scorer.confidence_threshold` | `0.05` | Min gap between rank-1 and rank-2 to auto-match |
| `use_llm` | `True` | Whether to call Claude Haiku on ambiguous cases |

To run without LLM (e.g. in CI):
```python
runner.run(config=MatcherConfig(use_llm=False))
```

---

## 8. Testing

```
tests/
├── test_normalizer.py    Unit tests for all pure normalization functions
├── test_indexer.py       Unit tests for index building
├── test_scorer.py        Unit tests for scoring formula and edge cases
├── test_matcher.py       Unit tests for decision logic (LLM stubbed out)
└── test_integration.py   End-to-end test with fixture data
```

Run:
```bash
pytest                          # all tests
pytest --cov=matcher            # with coverage
pytest -m unit                  # unit tests only
```

LLM is always stubbed in tests — no API key required.

---

## 9. Running the Pipeline

```bash
# Activate virtual environment
source .venv/bin/activate

# Run with defaults (large_set.json + large_set_vat.json)
python runner.py

# Run with custom files
python runner.py path/to/deliveries.json path/to/invoices.json
```

Required environment variable:
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Only needed when use_llm=True
```

**Output files (written next to the deliveries file):**
| File | Contents |
|------|---------|
| `output.json` | Full results — all invoices with scores and candidates |
| `output.csv` | Matched invoices only — for downstream finance systems |
| `manual_review.csv` | Flagged invoices — human review queue |

---

## 10. Known Limitations & Next Steps

| # | Issue | Impact | Suggested Fix |
|---|-------|--------|---------------|
| 1 | Token overlap misses abbreviations (`HCM` ≠ `Hồ Chí Minh`) | False negatives in address scoring | Vietnamese address normalization dictionary |
| 2 | Date window fixed at ±1 day | Invoices issued late get dropped | Make window configurable per invoice type |
| 3 | 75 invoices have no plate at all | Can't match by plate | Address-only fallback matching |
| 4 | LLM only called for top-3 candidates | True match may be rank 4+ | Expand to top-5 |
| 5 | No feedback loop from manual review | Human corrections don't improve scoring | Log resolved cases; fine-tune weights |
| 6 | `print()` replaced with `logging` | ✅ Done in this refactor | — |
| 7 | `DeliveryEntry = dict` (weak typing) | ✅ Replaced with TypedDict | — |
| 8 | API key silently defaulted to `""` | ✅ Fixed — fails fast with `KeyError` | — |

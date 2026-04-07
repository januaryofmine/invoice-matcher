# Proposed Solution: Invoice ↔ Delivery Matching (Large Dataset)

## Context

- **Dataset:** 32 deliveries, 3,319 invoices
- **Match rate after plate filter:** 127/3,319 (4%) — remaining belong to deliveries outside this dataset
- **Ambiguous after date filter:** 102/127 relevant invoices (80%)
- **Auto-matched (scoring):** 104 invoices
- **Pending LLM resolution:** ~23 invoices
- **Goal:** Maximize correct matches while minimizing false assignments

---

## Architecture Overview

```
3,319 invoices
    │
    ▼
Step 1: Candidate Generation        → 127 relevant invoices (plate + date filter)
    │
    ▼
Step 2: Candidate Scoring           → score per (invoice, delivery) pair
    │
    ├─ gap ≥ 0.05 ──────────────────→ AUTO MATCH
    │
    ├─ gap < 0.05 ──────────────────→ Step 3: LLM Resolution (~23 cases)
    │                                    │
    │                               ├─ confident ──→ AUTO MATCH
    │                               └─ uncertain ──→ MANUAL REVIEW
    │
    └─ 0 candidates ───────────────→ NO MATCH
```

---

## Step 1: Candidate Generation

Filter invoices to relevant delivery candidates using two **hard filters**:

```
normalized_plate match
AND
invoice_date within [pickup_date - DATE_WINDOW, dropoff_date + DATE_WINDOW]
```

**Expected output:**
- 3,117 invoices → `NO_MATCH` (plate not in dataset)
- 127 invoices → proceed to scoring

**Parameters:**
- `DATE_WINDOW = 1 day` (default) — configurable
- Optional widened window `2 days` for low-recall edge cases

**Why hard filter, not soft score:**
Date is a strong eliminator (EDA shows dates cluster at -2 to +1 days). Province, weight, and address are applied in scoring — not filtering — to avoid over-filtering on noisy data.

---

## Step 2: Candidate Scoring

For each (invoice, candidate_delivery) pair, compute a confidence score.

### Score components

**2.1 Date proximity score (weight: 0.10)**

Closer invoice dates score higher. Date discriminates poorly (avg = 0.982 across all candidates) — its main role is filtering, not scoring.

```
0 days difference  → 1.00
1 day difference   → 0.85
2 days difference  → 0.60
3+ days difference → 0.20
```

**2.2 Address similarity score (weight: 0.65)**

Token overlap between invoice `(Delivery address)` and delivery `dropoff_location.description`:

```
address_score = overlap_tokens / len(invoice_tokens)
```

Tokenization: lowercase, strip punctuation, remove tokens < 2 chars.

Important: distinctive business/location tokens (e.g. `big c`, `trần khánh dư`, `liên nghĩa`) carry more signal than generic geo tokens (e.g. `đà nẵng`, `việt nam`). Token weighting dictionary is a V2 improvement.

**2.3 Weight compatibility score (weight: 0.20)**

Only compute when both invoice and delivery weight are valid:

```
weight_diff_ratio = abs(invoice_weight_tons - delivery_weight) / max(delivery_weight, 1)

<= 10% diff → 1.0
<= 25% diff → 0.7
>  25% diff → 0.3
```

If either weight is missing → `weight_score = 0.0` (neutral, not penalized).

**Combined formula:**
```
score = 0.70 * address_score
      + 0.30 * weight_score
```

**Why only 2 components:**
- **Date** — avg score = 0.982 across all candidates (EDA). Nearly all candidates score the same, so date is a strong *filter* (Step 1) but not a *discriminator*. Adding it to scoring adds noise, not signal.
- **Province** — 25% missing in this dataset, inconsistent normalization ("Thành phố Hồ Chí Minh" vs "Hồ Chí Minh" treated as different). Too unreliable to include.
- **Address** — strongest discriminator. EDA shows 47/91 ambiguous cases resolved by address gap alone. Weight: **0.70**.
- **Weight** — reliable when available, but 31% of deliveries have no weight. Acts as tiebreaker. Weight: **0.30**.

All weights are configurable — not hardcoded into business logic.

---

## Step 3: LLM Resolution (~23 cases)

For invoices where score gap < `CONFIDENCE_THRESHOLD`, use LLM to resolve.

**Why LLM here (not earlier):**
Token overlap fails when addresses use abbreviations, different formats, or reference intermediate warehouses. LLM understands semantic similarity (e.g. "Quảng trường Lâm Viên" = "GO! Đà Lạt"). Calling LLM on only ~23 cases keeps token budget minimal — appropriate scope for the problem size.

**Prompt:**
```
You are matching a logistics invoice to a delivery.

Invoice delivery address: {invoice_address}

Candidate deliveries:
1. {delivery_1_name} — {delivery_1_address}
2. {delivery_2_name} — {delivery_2_address}

Which delivery does this invoice most likely belong to?
Return JSON: {"match": 1, "confidence": "high|medium|low", "reason": "..."}
```

**Decision:**
```
confidence == "high"   → AUTO MATCH
confidence == "medium" → AUTO MATCH (flagged for review)
confidence == "low"    → MANUAL REVIEW
```

**Model:** `claude-haiku-4-5` — fast, cheap, sufficient for address matching.

---

## Decision Engine

### Case A — 0 candidates
```json
{
  "status": "NO_MATCH",
  "reason": "no candidate deliveries after plate/date filtering"
}
```

### Case B — 1 candidate
Auto-match directly. Plate match + date match is already sufficient evidence.

### Case C — multiple candidates

Sort by score descending.

```
top_score >= AUTO_MATCH_THRESHOLD
AND (top_score - second_score) >= MARGIN_THRESHOLD
→ AUTO MATCH

otherwise
→ Step 3: LLM Resolution

all candidates below MIN_REVIEW_THRESHOLD
→ MANUAL REVIEW
```

**Parameters:**
- `AUTO_MATCH_THRESHOLD = 0.70` (calibrate from labeled data)
- `MARGIN_THRESHOLD = 0.05` (from EDA gap analysis: 47/91 cases have gap > 0.05)
- `MIN_REVIEW_THRESHOLD = 0.30`

---

## Output Data Model

Each invoice produces a structured result:

```json
{
  "invoice_id": 34917419,
  "status": "AUTO_MATCH",
  "matched_delivery_id": 66975,
  "confidence_score": 0.91,
  "method": "scoring | llm",
  "top_candidates": [
    {
      "delivery_id": 66975,
      "score": 0.91,
      "reasons": {
        "address_score": 0.95,
        "weight_score": 0.70
      }
    },
    {
      "delivery_id": 66976,
      "score": 0.41
    }
  ]
}
```

Output files:
- `output.csv` — `delivery_id, invoice_id, confidence_score, method`
- `manual_review.csv` — `invoice_id, top_candidate, score_gap, llm_reason`

---

## Operational Workflow

**Auto-match bucket:**
Invoices matched with high confidence are persisted automatically.

**Manual review bucket:**
Invoices with ambiguity go into a review queue with:
- Top candidate list with scores
- Signal breakdown (date / address / weight / province)
- Invoice address and delivery destination side by side

Since only 127 invoices survive primary filtering, manual review volume is manageable even at 100% fallback.

---

## Special Cases

| Case | Handling |
|---|---|
| No plate on invoice | `manual_review (no_plate)` — out of V1 scope |
| Plate exists, no delivery match | `NO_MATCH` |
| VINALOG / intermediate warehouse address | Low address scores → small gap → LLM resolves |
| Multi-stop same-plate same-date (43H01450) | LLM or `MANUAL_REVIEW` — do not force auto-match |
| Same dropoff, different dates (62C05274) | Date filter naturally disambiguates |
| Weight missing on both sides | Weight score = 0, address carries full weight |

---

## Configurable Parameters

| Parameter | Default | Description |
|---|---|---|
| `DATE_WINDOW` | 1 day | Date filter window around pickup/dropoff |
| `W_ADDR` | 0.7 | Address score weight |
| `W_WEIGHT` | 0.3 | Weight score weight |
| `CONFIDENCE_THRESHOLD` | 0.05 | Min gap to auto-match |
| `LLM_MODEL` | claude-haiku-4-5 | Model for semantic address matching |

---

## Why Not LLM Earlier?

| Approach | Token cost | Accuracy | Speed |
|---|---|---|---|
| LLM for all 3,319 invoices | Very high | High | Slow |
| LLM for all 127 candidates | High | High | Medium |
| LLM only for ~23 unclear cases | **Minimal** | **High** | **Fast** |

---

## Implementation Plan

```
core/
└── types.py             # All shared types — Single Source of Truth

pipeline/
├── normalizer.py        # plate, date, weight normalization
├── indexer.py           # build plate → deliveries index
├── scorer.py            # address + weight scoring
└── matcher.py           # orchestrate the 3-stage pipeline

adapters/
└── llm.py               # LLM fallback (Claude Haiku) — DIP via LLMResolver Protocol

file_io/
├── loader.py            # read delivery + invoice JSON
└── writer.py            # write output.json, output.csv, manual_review.csv

runner.py                # CLI entry point — I/O wiring only

tests/
├── test_normalizer.py
├── test_indexer.py
├── test_scorer.py
├── test_matcher.py
└── test_integration.py
```

**V1 — Production-safe baseline:**
- Normalization layer
- Candidate generation (plate + date)
- Weighted scoring (address + weight)
- Auto-match + LLM resolution + manual review buckets
- Structured JSON output with score breakdown

**V2 — Accuracy improvements:**
- Token weighting dictionary for logistics/place names
- Smarter address parser (abbreviation expansion)
- Route-level heuristics for multi-stop patterns
- Better warehouse/intermediate-stop detection

**V3 — Data-driven:**
- Learn weights from human-reviewed outcomes
- Ranking model if enough labeled data available

---

## Risks & Limitations

**Warehouse/intermediate-stop invoices:**
Some invoices reference intermediate warehouses (e.g. VINALOG) instead of final delivery point. Address matching will produce weak scores across all candidates.
→ Mitigation: low gap → LLM resolves; unresolvable cases → MANUAL REVIEW.

**Plate reuse across shipments:**
Same truck plate appears across multiple invoices from different days.
→ Mitigation: always apply date window before scoring; never aggregate weight globally per plate.

**Missing/malformed fields:**
Invoices may have missing plate, malformed weight, inconsistent province.
→ Mitigation: normalization layer with explicit fail-safe; NO_MATCH and MANUAL_REVIEW states handle gracefully.

**Weight unit inconsistency:**
Invoice weight heuristic (`> 1000 → divide by 1000`) is fragile.
→ Mitigation: only use weight as supporting signal (W=0.20), never as primary.

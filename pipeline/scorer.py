"""
Candidate scoring — Stage 2 of the matching pipeline.

Responsibility (SRP): given an invoice and a list of candidate deliveries,
compute a confidence score for each pair and return them ranked.
No I/O, no decisions, no LLM calls happen here.

Scoring formula
───────────────
  total = w_addr * address_score  +  w_weight * weight_score

Both components are in [0, 1].  Higher total = more confident match.

When weight data is unavailable for a candidate, its w_weight is redistributed
to address_score so the total is still in [0, 1] and candidates with / without
weight data remain comparable.
"""

from dataclasses import dataclass

from pipeline.normalizer import tokenize
from core.types import DeliveryEntry, ScorerConfig


# ── Score result type ─────────────────────────────────────────────────────────


@dataclass
class CandidateScore:
    """
    Holds all scoring data for one (invoice, delivery) pair.

    Keeping individual components (address_score, weight_score) alongside the
    total makes the result auditable — the UI and manual_review.csv can show
    exactly why each candidate ranked where it did.
    """

    delivery_id: int
    total_score: float
    address_score: float
    weight_score: float | None    # None = weight data was unavailable
    delivery_name: str = ""
    delivery_description: str = ""


# ── Score components ──────────────────────────────────────────────────────────


def address_score(inv_address: str, delivery: DeliveryEntry) -> float:
    """
    Measure how well the invoice delivery address matches a delivery's dropoff.

    Algorithm: token overlap ratio
        score = |invoice_tokens ∩ dropoff_tokens| / |invoice_tokens|

    Intuition: what fraction of the words in the invoice address also appear
    in the delivery's location description?

    Why both dropoff_name AND dropoff_description?
      - dropoff_name  may be a business name: 'Big C Đà Lạt'
      - dropoff_description is the street address: 'Quảng trường Lâm Viên, Đà Lạt'
      Combining both maximizes token coverage.

    Steps:
      1. Tokenize invoice address; return 0.0 if empty (nothing to compare).
      2. Build combined dropoff text and tokenize it.
      3. Return 0.0 if the delivery has no location tokens.
      4. Compute and return overlap ratio.
    """
    # Step 1 — tokenize returns a set; empty means no useful address tokens
    inv_tokens = tokenize(inv_address)
    if not inv_tokens:
        return 0.0

    # Step 2 — concatenate name + description for maximum token coverage
    dropoff_text = (
        f"{delivery.get('dropoff_name', '')} {delivery.get('dropoff_description', '')}"
    )
    dropoff_tokens = tokenize(dropoff_text)

    # Step 3 — delivery has no location data at all
    if not dropoff_tokens:
        return 0.0

    # Step 4 — set intersection is O(min(|A|, |B|)); ratio is in [0, 1]
    overlap = len(inv_tokens & dropoff_tokens)
    return overlap / len(inv_tokens)


def weight_score(inv_weight_kg: float, delivery: DeliveryEntry) -> float | None:
    """
    Compare invoice weight with delivery weight using a symmetric ratio.

    Algorithm: min/max ratio
        score = min(inv_tons, del_tons) / max(inv_tons, del_tons)

    A perfect weight match scores 1.0; a 2x mismatch scores 0.5.

    Returns None (not 0.0) when either side has missing/zero weight, so the
    caller can distinguish 'bad match' from 'no data'.  score_candidate()
    redistributes the weight component when this returns None.

    Steps:
      1. Guard: delivery weight missing or zero → None.
      2. Guard: invoice weight missing or zero → None.
      3. Convert invoice kg → tons for a fair comparison.
      4. Compute and return symmetric ratio.
    """
    del_weight = delivery.get("weight_tons")

    # Step 1 — delivery has no weight data; can't score this component
    if not del_weight or del_weight <= 0:
        return None

    # Step 2 — invoice weight 0.0 means 'unknown' (see parse_weight_kg)
    inv_tons = inv_weight_kg / 1000
    if inv_tons <= 0:
        return None

    # Step 4 — symmetric ratio; always in (0, 1]
    return min(inv_tons, del_weight) / max(inv_tons, del_weight)


# ── Single candidate scoring ──────────────────────────────────────────────────


def score_candidate(
    inv_address: str,
    inv_weight_kg: float,
    delivery: DeliveryEntry,
    config: ScorerConfig,
) -> CandidateScore:
    """
    Compute the combined confidence score for one (invoice, delivery) pair.

    Steps:
      1. Compute address component.
      2. Compute weight component (may be None).
      3. If weight is None, redistribute its configured weight to address so
         the total remains in [0, 1] and candidates are still comparable.
      4. If weight exists, apply the standard weighted formula.
      5. Round to 4 decimal places to keep output clean.
      6. Return a CandidateScore with all components for auditability.
    """
    # Step 1 — address similarity in [0, 1]
    addr = address_score(inv_address, delivery)

    # Step 2 — weight similarity in (0, 1] or None
    wt = weight_score(inv_weight_kg, delivery)

    # Steps 3 & 4 — combine components; handle missing weight
    if wt is None:
        # No weight data: promote address weight to 1.0
        effective_addr_weight = config.w_addr + config.w_weight
        total = effective_addr_weight * addr
    else:
        total = config.w_addr * addr + config.w_weight * wt

    # Step 5 — round for clean JSON output
    return CandidateScore(
        delivery_id=delivery["id"],
        total_score=round(total, 4),
        address_score=round(addr, 4),
        weight_score=round(wt, 4) if wt is not None else None,
        delivery_name=delivery.get("dropoff_name", ""),
        delivery_description=delivery.get("dropoff_description", ""),
    )


# ── Batch scoring ─────────────────────────────────────────────────────────────


def score_all_candidates(
    inv_address: str,
    inv_weight_kg: float,
    candidates: list[DeliveryEntry],
    config: ScorerConfig,
) -> list[CandidateScore]:
    """
    Score every candidate delivery for one invoice and return them ranked.

    Steps:
      1. Score each candidate independently (pure, parallelizable if needed).
      2. Sort descending by total_score so index 0 is always the best match.

    Returns an empty list if candidates is empty (caller handles this).
    """
    # Step 1 — score each candidate; list comprehension keeps it concise
    scores = [
        score_candidate(inv_address, inv_weight_kg, candidate, config)
        for candidate in candidates
    ]

    # Step 2 — rank-1 at index 0; rank-2 at index 1; used by get_score_gap()
    return sorted(scores, key=lambda s: s.total_score, reverse=True)


def get_score_gap(scores: list[CandidateScore]) -> float:
    """
    Compute the confidence gap between the top-ranked and second-ranked candidate.

    A large gap means the best candidate is clearly better than the rest
    (safe to auto-match).  A small gap means the decision is ambiguous
    (send to LLM or manual review).

    Returns 1.0 for a single candidate — no competition means maximum certainty.
    Returns 0.0 for an empty list — treated as no evidence.
    """
    if len(scores) < 2:
        # Single candidate: plate + date filter already narrowed to one option
        return 1.0

    return scores[0].total_score - scores[1].total_score

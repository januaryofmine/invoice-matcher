"""
Candidate scoring: computes confidence score for each (invoice, delivery) pair.

Score = W_ADDR * address_score + W_WEIGHT * weight_score

Both components are in [0, 1]. Higher = more confident match.
"""

from dataclasses import dataclass, field

from matcher.indexer import DeliveryEntry
from matcher.normalizer import tokenize

# ── Config ────────────────────────────────────────────────────────────────────


@dataclass
class ScorerConfig:
    w_addr: float = 0.7
    w_weight: float = 0.3
    confidence_threshold: float = 0.05  # min gap between top-1 and top-2 to auto-match


# ── Score components ──────────────────────────────────────────────────────────


def address_score(inv_address: str, delivery: DeliveryEntry) -> float:
    """
    Token overlap between invoice delivery address and delivery dropoff.

    score = |inv_tokens ∩ dropoff_tokens| / |inv_tokens|

    Uses both dropoff name and description for maximum coverage.
    Returns 0.0 if either side has no tokens.
    """
    inv_tokens = tokenize(inv_address)
    if not inv_tokens:
        return 0.0

    dropoff_text = (
        f"{delivery.get('dropoff_name', '')} {delivery.get('dropoff_description', '')}"
    )
    dropoff_tokens = tokenize(dropoff_text)
    if not dropoff_tokens:
        return 0.0

    overlap = len(inv_tokens & dropoff_tokens)
    return overlap / len(inv_tokens)


def weight_score(inv_weight_kg: float, delivery: DeliveryEntry) -> float | None:
    """
    Compare invoice weight (kg → tons) with delivery weight (tons).

    Returns None if either weight is missing/zero — caller treats as neutral.

    score = min(inv, del) / max(inv, del)   (ratio-based, 1.0 = perfect match)
    """
    del_weight = delivery.get("weight_tons")
    if not del_weight or del_weight <= 0:
        return None

    inv_tons = inv_weight_kg / 1000
    if inv_tons <= 0:
        return None

    return min(inv_tons, del_weight) / max(inv_tons, del_weight)


# ── Candidate score ───────────────────────────────────────────────────────────


@dataclass
class CandidateScore:
    delivery_id: int
    total_score: float
    address_score: float
    weight_score: float | None
    delivery_name: str = ""
    delivery_description: str = ""


def score_candidate(
    inv_address: str,
    inv_weight_kg: float,
    delivery: DeliveryEntry,
    config: ScorerConfig,
) -> CandidateScore:
    """Compute all score components for a single (invoice, delivery) pair."""
    addr = address_score(inv_address, delivery)
    wt = weight_score(inv_weight_kg, delivery)

    # If weight missing, redistribute its weight to address
    if wt is None:
        effective_addr_weight = config.w_addr + config.w_weight
        total = effective_addr_weight * addr
    else:
        total = config.w_addr * addr + config.w_weight * wt

    return CandidateScore(
        delivery_id=delivery["id"],
        total_score=round(total, 4),
        address_score=round(addr, 4),
        weight_score=round(wt, 4) if wt is not None else None,
        delivery_name=delivery.get("dropoff_name", ""),
        delivery_description=delivery.get("dropoff_description", ""),
    )


def score_all_candidates(
    inv_address: str,
    inv_weight_kg: float,
    candidates: list[DeliveryEntry],
    config: ScorerConfig,
) -> list[CandidateScore]:
    """Score all candidates for an invoice. Returns sorted by score descending."""
    scores = [
        score_candidate(inv_address, inv_weight_kg, c, config) for c in candidates
    ]
    return sorted(scores, key=lambda s: s.total_score, reverse=True)


def get_score_gap(scores: list[CandidateScore]) -> float:
    """Gap between top-1 and top-2 scores. 0.0 if fewer than 2 candidates."""
    if len(scores) < 2:
        return 1.0  # single candidate → no competition
    return scores[0].total_score - scores[1].total_score

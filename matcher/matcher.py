"""
Unified matching pipeline.

Stage 1: Candidate generation (plate + date filter)
Stage 2: Candidate scoring (address + weight)
Stage 3: Decision (auto-match | LLM resolve | manual_review)
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

from matcher.indexer import DeliveryEntry, build_delivery_index
from matcher.llm_resolver import resolve as llm_resolve
from matcher.normalizer import normalize_plate, parse_date, parse_weight_kg
from matcher.scorer import (
    CandidateScore,
    ScorerConfig,
    get_score_gap,
    score_all_candidates,
)

# ── Config ────────────────────────────────────────────────────────────────────


@dataclass
class MatcherConfig:
    date_window_days: int = 1
    scorer: ScorerConfig = field(default_factory=ScorerConfig)
    use_llm: bool = True


# ── Result types ──────────────────────────────────────────────────────────────


class MatchStatus(str, Enum):
    AUTO_MATCH = "AUTO_MATCH"
    LLM_MATCH = "LLM_MATCH"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_MATCH = "NO_MATCH"
    NO_PLATE = "NO_PLATE"


@dataclass
class InvoiceResult:
    invoice_id: int
    status: MatchStatus
    matched_delivery_id: int | None = None
    confidence_score: float | None = None
    score_gap: float | None = None
    reason: str = ""
    top_candidates: list[dict] = field(default_factory=list)


# ── Stage 1: Candidate generation ─────────────────────────────────────────────


def _get_candidates(
    inv_date,
    plate: str,
    index: dict[str, list[DeliveryEntry]],
    window_days: int,
) -> list[DeliveryEntry]:
    """Filter deliveries by plate and date window."""
    entries = index.get(plate, [])
    if not inv_date:
        return entries  # no date → keep all (scored later)

    result = []
    for entry in entries:
        pickup = entry.get("pickup_date")
        dropoff = entry.get("dropoff_date")
        if pickup and dropoff:
            lo = pickup - timedelta(days=window_days)
            hi = dropoff + timedelta(days=window_days)
            if lo <= inv_date <= hi:
                result.append(entry)
        else:
            result.append(entry)  # no delivery dates → keep
    return result


# ── Stage 3: Decision ─────────────────────────────────────────────────────────


def _make_decision(
    inv_id: int,
    inv_address: str,
    scores: list[CandidateScore],
    config: MatcherConfig,
) -> InvoiceResult:
    """Apply decision policy based on scores and gap."""

    def _format_candidates(scores: list[CandidateScore]) -> list[dict]:
        return [
            {
                "delivery_id": s.delivery_id,
                "score": s.total_score,
                "reasons": {
                    "address_score": s.address_score,
                    "weight_score": s.weight_score,
                },
            }
            for s in scores[:3]
        ]

    if not scores:
        return InvoiceResult(
            invoice_id=inv_id,
            status=MatchStatus.NO_MATCH,
            reason="no candidates after date filter",
        )

    gap = get_score_gap(scores)
    top = scores[0]

    # Single candidate → auto-match (plate + date already sufficient evidence)
    if len(scores) == 1:
        return InvoiceResult(
            invoice_id=inv_id,
            status=MatchStatus.AUTO_MATCH,
            matched_delivery_id=top.delivery_id,
            confidence_score=top.total_score,
            score_gap=gap,
            reason="single candidate after filtering",
            top_candidates=_format_candidates(scores),
        )

    # Clear winner → auto-match
    if gap >= config.scorer.confidence_threshold:
        return InvoiceResult(
            invoice_id=inv_id,
            status=MatchStatus.AUTO_MATCH,
            matched_delivery_id=top.delivery_id,
            confidence_score=top.total_score,
            score_gap=gap,
            reason=f"score gap {gap:.3f} >= threshold {config.scorer.confidence_threshold}",
            top_candidates=_format_candidates(scores),
        )

    # Ambiguous → LLM
    if config.use_llm:
        llm_result = llm_resolve(inv_address, scores[:3])  # pass top 3 to LLM
        confidence = llm_result.get("confidence", "failed")
        del_id = llm_result.get("matched_delivery_id")
        reason = llm_result.get("reason", "")

        if del_id and confidence in ("high", "medium"):
            return InvoiceResult(
                invoice_id=inv_id,
                status=MatchStatus.LLM_MATCH,
                matched_delivery_id=del_id,
                confidence_score=top.total_score,
                score_gap=gap,
                reason=f"LLM ({confidence}): {reason}",
                top_candidates=_format_candidates(scores),
            )

    # Fallback → manual review
    return InvoiceResult(
        invoice_id=inv_id,
        status=MatchStatus.MANUAL_REVIEW,
        confidence_score=top.total_score,
        score_gap=gap,
        reason=f"score gap {gap:.3f} < threshold, LLM inconclusive",
        top_candidates=_format_candidates(scores),
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────


def match_invoices(
    deliveries: list[dict],
    invoices: list[dict],
    config: MatcherConfig | None = None,
) -> list[InvoiceResult]:
    """
    Match VAT invoices to deliveries.

    Stage 1: Plate + date filter → candidates
    Stage 2: Score candidates (address + weight)
    Stage 3: Decide (auto | LLM | manual_review)

    Returns list of InvoiceResult, one per invoice.
    """
    if config is None:
        config = MatcherConfig()

    index = build_delivery_index(deliveries)
    results = []

    for inv in invoices:
        inv_id = inv["id"]
        plate = normalize_plate(inv.get("truck_plate"))

        # No plate → manual review immediately
        if not plate:
            results.append(
                InvoiceResult(
                    invoice_id=inv_id,
                    status=MatchStatus.NO_PLATE,
                    reason="missing truck plate",
                )
            )
            continue

        # Plate not in any delivery → no match
        if plate not in index:
            results.append(
                InvoiceResult(
                    invoice_id=inv_id,
                    status=MatchStatus.NO_MATCH,
                    reason="plate not found in any delivery",
                )
            )
            continue

        meta = inv.get("metadata") or {}
        inv_date = parse_date(meta.get("(Date)"))
        inv_address = meta.get("(Delivery address)", "") or ""
        inv_weight_kg = parse_weight_kg(inv.get("sku_data"))

        # Stage 1: candidates
        candidates = _get_candidates(inv_date, plate, index, config.date_window_days)

        if not candidates:
            results.append(
                InvoiceResult(
                    invoice_id=inv_id,
                    status=MatchStatus.NO_MATCH,
                    reason="plate matches but invoice date outside delivery window",
                )
            )
            continue

        # Stage 2: score
        scores = score_all_candidates(
            inv_address, inv_weight_kg, candidates, config.scorer
        )

        # Stage 3: decide
        result = _make_decision(inv_id, inv_address, scores, config)
        results.append(result)

    return results


def summarize(results: list[InvoiceResult]) -> dict:
    """Compute summary statistics from match results."""
    counts: dict[str, int] = defaultdict(int)
    for r in results:
        counts[r.status.value] += 1

    matched = counts[MatchStatus.AUTO_MATCH] + counts[MatchStatus.LLM_MATCH]

    return {
        "total": len(results),
        "auto_match": counts[MatchStatus.AUTO_MATCH],
        "llm_match": counts[MatchStatus.LLM_MATCH],
        "manual_review": counts[MatchStatus.MANUAL_REVIEW],
        "no_match": counts[MatchStatus.NO_MATCH],
        "no_plate": counts[MatchStatus.NO_PLATE],
        "total_matched": matched,
    }

"""
Unified matching pipeline — orchestrates all three stages.

Stage 1: Candidate generation  — filter deliveries by plate + date window
Stage 2: Candidate scoring     — rank candidates by address + weight similarity
Stage 3: Decision              — auto-match, LLM resolve, or flag for review

Design principles applied:
  - SRP: this module only orchestrates; it does not normalize, score, or call
    the LLM itself.  Each concern lives in its own module.
  - DIP: the LLM resolver is injected via the LLMResolver Protocol rather than
    imported directly.  Pass a stub in tests to avoid real API calls.
  - OCP: adding a new decision rule (e.g. a 'weight-only' path) means adding a
    branch in _make_decision() — the other stages are unchanged.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from pipeline.indexer import DeliveryEntry, build_delivery_index
from adapters.llm import LLMResolver, resolve as llm_resolve
from pipeline.normalizer import normalize_plate, parse_date, parse_weight_kg
from pipeline.scorer import CandidateScore, get_score_gap, score_all_candidates
from core.types import InvoiceResult, MatcherConfig, MatchStatus

logger = logging.getLogger(__name__)

# ── Invoice metadata field names ──────────────────────────────────────────────
# The upstream VAT invoice JSON uses parenthesised keys.  Defining them as
# constants here prevents typos and makes it easy to update if the API changes.

FIELD_DATE            = "(Date)"
FIELD_DELIVERY_ADDR   = "(Delivery address)"


# ── Stage 1 — Candidate generation ───────────────────────────────────────────


def _get_candidates(
    inv_date,
    plate: str,
    index: dict[str, list[DeliveryEntry]],
    window_days: int,
) -> list[DeliveryEntry]:
    """
    Filter the indexed deliveries for a given plate to those within the date window.

    Why a date window?
      An invoice is only valid evidence for a delivery if it was issued within
      a reasonable time of that delivery's pickup / dropoff.  The default window
      is ±1 day; this is configurable via MatcherConfig.date_window_days.

    Steps:
      1. Look up all deliveries for this plate.  Returns [] if plate not found.
      2. If the invoice has no parseable date, keep ALL deliveries for this plate
         (the scorer will rank them; none can be excluded by date alone).
      3. For each delivery with known dates, check whether inv_date falls in
         [pickup_date - window, dropoff_date + window].
      4. Keep deliveries with missing dates (can't exclude without evidence).
      5. Return the filtered list.
    """
    # Step 1 — O(1) lookup; returns [] for unknown plates
    entries = index.get(plate, [])

    # Step 2 — no invoice date means we can't filter by date at all
    if not inv_date:
        return entries

    filtered = []
    for entry in entries:
        pickup  = entry.get("pickup_date")
        dropoff = entry.get("dropoff_date")

        if pickup and dropoff:
            # Step 3 — expand the window symmetrically around the delivery period
            window_start = pickup  - timedelta(days=window_days)
            window_end   = dropoff + timedelta(days=window_days)

            if window_start <= inv_date <= window_end:
                filtered.append(entry)
            # else: invoice date outside window — silently excluded
        else:
            # Step 4 — delivery has no dates; keep it to avoid false negatives
            filtered.append(entry)

    return filtered


# ── Stage 3 — Decision ────────────────────────────────────────────────────────


def _format_top_candidates(scores: list[CandidateScore]) -> list[dict]:
    """
    Serialise the top-3 scored candidates for the InvoiceResult output.

    Keeping delivery_name / delivery_description here allows the UI to render
    candidate details without a second API call.
    """
    return [
        {
            "delivery_id":          s.delivery_id,
            "delivery_name":        s.delivery_name,
            "delivery_description": s.delivery_description,
            "score":                s.total_score,
            "reasons": {
                "address_score": s.address_score,
                "weight_score":  s.weight_score,
            },
        }
        for s in scores[:3]
    ]


def _make_decision(
    inv_id: int,
    inv_address: str,
    scores: list[CandidateScore],
    config: MatcherConfig,
    llm_resolver: LLMResolver,
) -> InvoiceResult:
    """
    Apply the decision policy to a ranked list of scored candidates.

    Decision tree (in order):
      A. No candidates after date filter → NO_MATCH
      B. Single candidate               → AUTO_MATCH (plate+date sufficient)
      C. Score gap ≥ threshold          → AUTO_MATCH (clear winner)
      D. LLM enabled + gap < threshold  → call LLM
           D1. LLM high/medium          → LLM_MATCH
           D2. LLM low / failed         → MANUAL_REVIEW
      E. LLM disabled                   → MANUAL_REVIEW

    Steps:
      1. Handle empty candidates (NO_MATCH).
      2. Compute score gap between rank-1 and rank-2.
      3. Single-candidate fast path (AUTO_MATCH).
      4. Clear winner fast path (AUTO_MATCH).
      5. Call LLM resolver if enabled.
      6. Accept LLM result if confidence is high or medium.
      7. Fall through to MANUAL_REVIEW.
    """
    # Step 1 — no candidates survived the date filter
    if not scores:
        return InvoiceResult(
            invoice_id=inv_id,
            status=MatchStatus.NO_MATCH,
            reason="no candidates after date filter",
        )

    gap = get_score_gap(scores)   # Step 2
    top = scores[0]
    formatted = _format_top_candidates(scores)

    # Step 3 — single candidate: plate + date already narrow to one delivery
    if len(scores) == 1:
        return InvoiceResult(
            invoice_id=inv_id,
            status=MatchStatus.AUTO_MATCH,
            matched_delivery_id=top.delivery_id,
            confidence_score=top.total_score,
            score_gap=gap,
            reason="single candidate after filtering",
            top_candidates=formatted,
        )

    # Step 4 — gap is large enough that rank-1 is clearly better than rank-2
    if gap >= config.scorer.confidence_threshold:
        return InvoiceResult(
            invoice_id=inv_id,
            status=MatchStatus.AUTO_MATCH,
            matched_delivery_id=top.delivery_id,
            confidence_score=top.total_score,
            score_gap=gap,
            reason=f"score gap {gap:.3f} >= threshold {config.scorer.confidence_threshold}",
            top_candidates=formatted,
        )

    # Step 5 — ambiguous; ask the LLM to resolve semantically
    if config.use_llm:
        llm_result = llm_resolver(inv_address, scores[:3])
        confidence = llm_result.get("confidence", "failed")
        del_id     = llm_result.get("matched_delivery_id")
        reason     = llm_result.get("reason", "")

        # Step 6 — accept the LLM's answer only if it is reasonably confident
        if del_id and confidence in ("high", "medium"):
            return InvoiceResult(
                invoice_id=inv_id,
                status=MatchStatus.LLM_MATCH,
                matched_delivery_id=del_id,
                confidence_score=top.total_score,
                score_gap=gap,
                reason=f"LLM ({confidence}): {reason}",
                top_candidates=formatted,
            )

    # Step 7 — LLM inconclusive or disabled; flag for human review
    return InvoiceResult(
        invoice_id=inv_id,
        status=MatchStatus.MANUAL_REVIEW,
        confidence_score=top.total_score,
        score_gap=gap,
        reason=f"score gap {gap:.3f} < threshold, LLM inconclusive",
        top_candidates=formatted,
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────


def match_invoices(
    deliveries: list[dict],
    invoices: list[dict],
    config: MatcherConfig | None = None,
    llm_resolver: LLMResolver = llm_resolve,
) -> list[InvoiceResult]:
    """
    Match every VAT invoice to the most likely delivery.

    Returns one InvoiceResult per invoice, regardless of outcome.

    Parameters:
        deliveries:   Raw delivery records from the API / JSON file.
        invoices:     Raw VAT invoice records from the API / JSON file.
        config:       Pipeline configuration; uses defaults if None.
        llm_resolver: Injected resolver for Stage-3 LLM calls.
                      Override in tests with a stub to avoid real API calls.

    Steps:
      1. Apply default config if none provided.
      2. Build the plate → deliveries index (one-time O(n_deliveries) cost).
      3. For each invoice, run the three-stage pipeline.
         3a. Extract and normalise the truck plate.
         3b. Guard: no plate → NO_PLATE immediately.
         3c. Guard: plate not in any delivery → NO_MATCH immediately.
         3d. Parse invoice metadata (date, delivery address, weight).
         3e. Stage 1: filter candidates by date window.
         3f. Guard: no candidates after filter → NO_MATCH.
         3g. Stage 2: score remaining candidates.
         3h. Stage 3: decide outcome.
      4. Return all results.
    """
    # Step 1 — default config covers the common case
    if config is None:
        config = MatcherConfig()

    # Step 2 — build index once; reused for every invoice
    index = build_delivery_index(deliveries)
    logger.info("Built delivery index: %d unique plates", len(index))

    results: list[InvoiceResult] = []

    for inv in invoices:
        inv_id = inv["id"]

        # Step 3a — normalise plate to the same canonical form used in the index
        plate = normalize_plate(inv.get("truck_plate"))

        # Step 3b — invoice has no truck plate; cannot match by plate
        if not plate:
            results.append(InvoiceResult(
                invoice_id=inv_id,
                status=MatchStatus.NO_PLATE,
                reason="missing truck plate",
            ))
            continue

        # Step 3c — plate exists on the invoice but not in any delivery record
        if plate not in index:
            results.append(InvoiceResult(
                invoice_id=inv_id,
                status=MatchStatus.NO_MATCH,
                reason="plate not found in any delivery",
            ))
            continue

        # Step 3d — extract fields from invoice metadata
        meta         = inv.get("metadata") or {}
        inv_date     = parse_date(meta.get(FIELD_DATE))
        inv_address  = meta.get(FIELD_DELIVERY_ADDR) or ""
        inv_weight_kg = parse_weight_kg(inv.get("sku_data"))

        # Step 3e — Stage 1: narrow candidates by date window
        candidates = _get_candidates(inv_date, plate, index, config.date_window_days)

        # Step 3f — plate matched but no delivery falls within the date window
        if not candidates:
            results.append(InvoiceResult(
                invoice_id=inv_id,
                status=MatchStatus.NO_MATCH,
                reason="plate matches but invoice date outside delivery window",
            ))
            continue

        # Step 3g — Stage 2: score all candidates
        scores = score_all_candidates(inv_address, inv_weight_kg, candidates, config.scorer)

        # Step 3h — Stage 3: apply decision policy
        result = _make_decision(inv_id, inv_address, scores, config, llm_resolver)
        results.append(result)

    return results


# ── Summary statistics ────────────────────────────────────────────────────────


def summarize(results: list[InvoiceResult]) -> dict:
    """
    Compute a flat summary of match outcomes from the full result list.

    Used by runner.py to print a human-readable report and by tests to assert
    on aggregate behaviour without inspecting every record.
    """
    counts: dict[str, int] = defaultdict(int)
    for result in results:
        counts[result.status.value] += 1

    total_matched = counts[MatchStatus.AUTO_MATCH] + counts[MatchStatus.LLM_MATCH]

    return {
        "total":          len(results),
        "auto_match":     counts[MatchStatus.AUTO_MATCH],
        "llm_match":      counts[MatchStatus.LLM_MATCH],
        "manual_review":  counts[MatchStatus.MANUAL_REVIEW],
        "no_match":       counts[MatchStatus.NO_MATCH],
        "no_plate":       counts[MatchStatus.NO_PLATE],
        "total_matched":  total_matched,
    }

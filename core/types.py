"""
Central type definitions for the invoice-matcher pipeline.

Keeping all domain types in one place enforces the Single Responsibility
Principle: each other module imports types from here rather than defining
its own, so type changes propagate from a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict

from datetime import datetime


# ── Delivery types ────────────────────────────────────────────────────────────


class DeliveryEntry(TypedDict, total=False):
    """
    Normalized representation of one delivery, ready for matching.

    Built by indexer.py from the raw API/JSON shape.  Using TypedDict (instead
    of a plain dict) gives editors and type checkers visibility into the keys
    without the overhead of a full dataclass.

    Fields marked optional (total=False) may be absent when the upstream data
    is incomplete — callers must handle None / missing values explicitly.
    """

    id: int                        # Unique delivery ID (always present)
    pickup_date: datetime | None   # Normalized pickup datetime
    dropoff_date: datetime | None  # Normalized dropoff datetime
    weight_tons: float | None      # Delivery weight in metric tons
    dropoff_name: str              # Short name of the dropoff location
    dropoff_description: str       # Full address / description of the dropoff
    dropoff_location_id: int | None


# ── Match status ──────────────────────────────────────────────────────────────


class MatchStatus(str, Enum):
    """
    All possible outcomes for a single invoice.

    Inheriting from `str` means the enum serializes cleanly to JSON without
    a custom encoder (e.g. MatchStatus.AUTO_MATCH == "AUTO_MATCH" is True).
    """

    AUTO_MATCH    = "AUTO_MATCH"     # Rule-based match; score gap above threshold
    LLM_MATCH     = "LLM_MATCH"     # Ambiguous gap; resolved by Claude Haiku
    MANUAL_REVIEW = "MANUAL_REVIEW" # LLM inconclusive; needs human eyes
    NO_MATCH      = "NO_MATCH"      # Plate found but no delivery in date window
    NO_PLATE      = "NO_PLATE"      # Invoice has no usable truck plate


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass
class InvoiceResult:
    """
    The complete outcome of matching one VAT invoice.

    One InvoiceResult is produced per invoice, regardless of whether a match
    was found.  Fields default to None/empty so callers only populate what is
    relevant for each MatchStatus.
    """

    invoice_id: int
    status: MatchStatus

    # Only set when status is AUTO_MATCH or LLM_MATCH
    matched_delivery_id: int | None = None

    # Scoring metadata — None for NO_PLATE / NO_MATCH (no candidates scored)
    confidence_score: float | None = None
    score_gap: float | None = None

    # Human-readable explanation for auditing / UI display
    reason: str = ""

    # Up to 3 closest candidates with their score breakdown (for UI / review)
    top_candidates: list[dict] = field(default_factory=list)


# ── Configuration types ───────────────────────────────────────────────────────


@dataclass
class ScorerConfig:
    """
    Weights and thresholds used by the scoring stage.

    w_addr + w_weight should sum to 1.0.  When weight data is absent the
    address weight is promoted to 1.0 automatically in scorer.py.

    confidence_threshold: minimum score gap between rank-1 and rank-2 to
    accept a rule-based AUTO_MATCH without calling the LLM.
    """

    w_addr: float = 0.7               # Weight given to address similarity
    w_weight: float = 0.3             # Weight given to weight similarity
    confidence_threshold: float = 0.05  # Min gap to skip LLM arbitration


@dataclass
class MatcherConfig:
    """
    Top-level configuration for the full matching pipeline.

    Pass a custom instance to match_invoices() to override defaults, e.g.
    during testing or batch experiments without modifying source code.
    """

    # How many days before pickup / after dropoff an invoice date is still valid
    date_window_days: int = 1

    # Scorer weights and auto-match threshold
    scorer: ScorerConfig = field(default_factory=ScorerConfig)

    # Whether to call the LLM when score gap is below threshold.
    # Set to False in unit tests or offline runs to avoid API calls.
    use_llm: bool = True

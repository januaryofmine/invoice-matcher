"""
I/O layer — output data writing.

Responsibility (SRP): serialize InvoiceResult objects to the three output
formats consumed by different downstream systems.  No matching logic, no
data loading.

Output files:
  output.json       — full results with score breakdown (UI / analysis)
  output.csv        — matched invoices only (downstream finance integration)
  manual_review.csv — flagged invoices for human review queue
"""

import csv
import json
import logging
from pathlib import Path

from core.types import InvoiceResult, MatchStatus

logger = logging.getLogger(__name__)


def save_results(results: list[InvoiceResult], out_dir: Path) -> None:
    """
    Write all three output files to out_dir.

    Each format serves a different consumer; keeping them separate avoids
    coupling the UI format to the downstream integration format.
    """
    _write_json(results, out_dir / "output.json")
    _write_matched_csv(results, out_dir / "output.csv")
    _write_review_csv(results, out_dir / "manual_review.csv")


def _write_json(results: list[InvoiceResult], path: Path) -> None:
    """
    Write full results to output.json.

    Includes every invoice regardless of status, with complete score
    breakdown and top candidates — used by the invoice-ui dashboard.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "invoice_id":          r.invoice_id,
                    "status":              r.status.value,
                    "matched_delivery_id": r.matched_delivery_id,
                    "confidence_score":    r.confidence_score,
                    "score_gap":           r.score_gap,
                    "reason":              r.reason,
                    "top_candidates":      r.top_candidates,
                }
                for r in results
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("Saved → %s", path)


def _write_matched_csv(results: list[InvoiceResult], path: Path) -> None:
    """
    Write matched invoices only to output.csv.

    Only AUTO_MATCH and LLM_MATCH rows are included.
    Used by downstream finance systems that only need confirmed pairs.
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["delivery_id", "invoice_id", "confidence_score", "method"])
        for r in results:
            if r.matched_delivery_id:
                method = "llm" if r.status == MatchStatus.LLM_MATCH else "scoring"
                writer.writerow([r.matched_delivery_id, r.invoice_id, r.confidence_score, method])
    logger.info("Saved → %s", path)


def _write_review_csv(results: list[InvoiceResult], path: Path) -> None:
    """
    Write MANUAL_REVIEW invoices to manual_review.csv.

    These are cases where the LLM was inconclusive — a human reviewer
    should inspect the invoice and candidate deliveries listed here.
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["invoice_id", "top_candidate_delivery_id", "score_gap", "reason"])
        for r in results:
            if r.status == MatchStatus.MANUAL_REVIEW:
                top_del = r.top_candidates[0]["delivery_id"] if r.top_candidates else ""
                writer.writerow([r.invoice_id, top_del, r.score_gap, r.reason])
    logger.info("Saved → %s", path)

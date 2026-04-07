"""
Pipeline entry point.

Responsibility (SRP): coordinate I/O only.
  - load_deliveries()  — read and parse the delivery JSON file
  - load_invoices()    — read and parse the invoice JSON file
  - save_results()     — write output.json, output.csv, manual_review.csv
  - run()              — tie the above together with the matching pipeline

No matching logic lives here.  All domain logic is in matcher/.

Usage:
    python runner.py [deliveries.json] [invoices.json]

Defaults to large_set.json / large_set_vat.json when no args given.
"""

import csv
import json
import logging
import sys
from pathlib import Path

from matcher.matcher import MatchStatus, match_invoices, summarize
from matcher.types import InvoiceResult, MatcherConfig

# ── Logging setup ─────────────────────────────────────────────────────────────
# Configure once at module level; all child loggers (matcher.*) inherit this.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Data loading ──────────────────────────────────────────────────────────────


def load_deliveries(path: str) -> list[dict]:
    """
    Load and extract the delivery list from a JSON file.

    The upstream API wraps records in two possible shapes:
      { "data": { "items": [...] } }      — newer API response
      { "data": { "deliveries": [...] } } — legacy shape

    Steps:
      1. Validate that the file exists before opening (clear error message).
      2. Parse JSON.
      3. Extract the record list from either known wrapper shape.
      4. Return the flat list.

    Raises:
        FileNotFoundError: if path does not exist.
        KeyError / ValueError: if the JSON structure is unrecognised.
    """
    file = Path(path)

    # Step 1 — fail early with a helpful message rather than a raw FileNotFoundError
    if not file.exists():
        raise FileNotFoundError(f"Deliveries file not found: {path}")

    logger.info("Loading deliveries from %s", path)

    with open(file, encoding="utf-8") as f:
        raw = json.load(f)

    # Step 3 — support both known API wrapper shapes
    data = raw.get("data", {})
    if "items" in data:
        deliveries = data["items"]
    elif "deliveries" in data:
        deliveries = data["deliveries"]
    else:
        raise ValueError(
            f"Unrecognised deliveries JSON shape in {path}. "
            "Expected 'data.items' or 'data.deliveries'."
        )

    logger.info("Loaded %d deliveries", len(deliveries))
    return deliveries


def load_invoices(path: str) -> list[dict]:
    """
    Load and extract the VAT invoice list from a JSON file.

    Expected shape: { "data": { "vat_invoices": [...] } }

    Steps:
      1. Validate that the file exists.
      2. Parse JSON.
      3. Extract 'vat_invoices' from the data wrapper.
      4. Return the flat list.
    """
    file = Path(path)

    if not file.exists():
        raise FileNotFoundError(f"Invoices file not found: {path}")

    logger.info("Loading invoices from %s", path)

    with open(file, encoding="utf-8") as f:
        raw = json.load(f)

    try:
        invoices = raw["data"]["vat_invoices"]
    except KeyError as exc:
        raise ValueError(
            f"Unrecognised invoices JSON shape in {path}. "
            "Expected 'data.vat_invoices'."
        ) from exc

    logger.info("Loaded %d invoices", len(invoices))
    return invoices


# ── Output writing ────────────────────────────────────────────────────────────


def save_results(results: list[InvoiceResult], out_dir: Path) -> None:
    """
    Write three output files to out_dir:
      output.json       — full results with score breakdown (for UI / analysis)
      output.csv        — matched invoices only (for downstream systems)
      manual_review.csv — invoices flagged for human review

    Each output format serves a different consumer; keeping them separate
    avoids coupling the UI format to the downstream integration format.

    Steps per file:
      1. Build the output path.
      2. Write the file.
      3. Log the saved path.
    """
    # ── output.json ──────────────────────────────────────────────────────────
    json_path = out_dir / "output.json"
    with open(json_path, "w", encoding="utf-8") as f:
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
    logger.info("Saved → %s", json_path)

    # ── output.csv — matched invoices only ───────────────────────────────────
    csv_path = out_dir / "output.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["delivery_id", "invoice_id", "confidence_score", "method"])
        for r in results:
            if r.matched_delivery_id:
                method = "llm" if r.status == MatchStatus.LLM_MATCH else "scoring"
                writer.writerow([r.matched_delivery_id, r.invoice_id, r.confidence_score, method])
    logger.info("Saved → %s", csv_path)

    # ── manual_review.csv — human review queue ────────────────────────────────
    review_path = out_dir / "manual_review.csv"
    with open(review_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["invoice_id", "top_candidate_delivery_id", "score_gap", "reason"])
        for r in results:
            if r.status == MatchStatus.MANUAL_REVIEW:
                top_del = r.top_candidates[0]["delivery_id"] if r.top_candidates else ""
                writer.writerow([r.invoice_id, top_del, r.score_gap, r.reason])
    logger.info("Saved → %s", review_path)


# ── Orchestrator ──────────────────────────────────────────────────────────────


def run(
    deliveries_path: str = "large_set.json",
    invoices_path: str = "large_set_vat.json",
    config: MatcherConfig | None = None,
) -> list[InvoiceResult]:
    """
    End-to-end pipeline: load → match → save → return results.

    Steps:
      1. Load delivery and invoice data.
      2. Run the matching pipeline.
      3. Log summary statistics.
      4. Determine the output directory (same folder as deliveries file).
      5. Write all three output files.
      6. Return results (useful for programmatic callers / tests).
    """
    # Step 1 — load inputs
    deliveries = load_deliveries(deliveries_path)
    invoices   = load_invoices(invoices_path)

    # Step 2 — run pipeline
    logger.info("Starting matching pipeline (%d deliveries, %d invoices)", len(deliveries), len(invoices))
    results = match_invoices(deliveries, invoices, config)

    # Step 3 — log summary
    stats = summarize(results)
    logger.info("=== MATCH SUMMARY ===")
    for key, value in stats.items():
        logger.info("  %-20s %d", key, value)

    # Step 4 — output directory follows the deliveries file location
    out_dir = Path(deliveries_path).parent

    # Step 5 — write outputs
    save_results(results, out_dir)

    # Step 6 — return for programmatic use
    return results


# ── CLI entry point ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    # Validate argument count before use to give a clear usage message
    if len(sys.argv) > 3:
        print("Usage: python runner.py [deliveries.json] [invoices.json]")
        sys.exit(1)

    del_path = sys.argv[1] if len(sys.argv) > 1 else "large_set.json"
    inv_path = sys.argv[2] if len(sys.argv) > 2 else "large_set_vat.json"

    run(del_path, inv_path)

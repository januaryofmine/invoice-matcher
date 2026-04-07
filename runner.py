"""
Pipeline entry point — CLI only.

Responsibility (SRP): wire together the io/ and pipeline/ layers.
No matching logic, no data-shape knowledge lives here.

Usage:
    python runner.py [deliveries.json] [invoices.json]

Defaults to large_set.json / large_set_vat.json when no args given.
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from file_io.loader import load_deliveries, load_invoices
from file_io.writer import save_results
from pipeline.matcher import match_invoices, summarize
from core.types import MatcherConfig

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(
    deliveries_path: str = "large_set.json",
    invoices_path: str = "large_set_vat.json",
    config: MatcherConfig | None = None,
) -> list:
    """
    End-to-end pipeline: load → match → save → return results.

    Steps:
      1. Load delivery and invoice data from disk.
      2. Run the 3-stage matching pipeline.
      3. Log summary statistics.
      4. Write all three output files next to the deliveries file.
      5. Return results for programmatic / test callers.
    """
    # Step 1 — load inputs
    deliveries = load_deliveries(deliveries_path)
    invoices   = load_invoices(invoices_path)

    # Step 2 — run pipeline
    logger.info(
        "Starting matching pipeline (%d deliveries, %d invoices)",
        len(deliveries), len(invoices),
    )
    results = match_invoices(deliveries, invoices, config)

    # Step 3 — log summary
    stats = summarize(results)
    logger.info("=== MATCH SUMMARY ===")
    for key, value in stats.items():
        logger.info("  %-20s %d", key, value)

    # Step 4 — write outputs next to the deliveries file
    out_dir = Path(deliveries_path).parent
    save_results(results, out_dir)

    return results


if __name__ == "__main__":
    if len(sys.argv) > 3:
        print("Usage: python runner.py [deliveries.json] [invoices.json]")
        sys.exit(1)

    del_path = sys.argv[1] if len(sys.argv) > 1 else "large_set.json"
    inv_path = sys.argv[2] if len(sys.argv) > 2 else "large_set_vat.json"

    run(del_path, inv_path)

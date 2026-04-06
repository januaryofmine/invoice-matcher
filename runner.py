"""
Entry point: load data, run matching, save outputs.
"""

import csv
import json
import sys
from pathlib import Path

from matcher.matcher import MatcherConfig, MatchStatus, match_invoices, summarize


def run(
    deliveries_path: str = "large_set.json",
    invoices_path: str = "large_set_vat.json",
    config: MatcherConfig | None = None,
) -> list:
    # Load
    with open(deliveries_path, encoding="utf-8") as f:
        raw = json.load(f)
        deliveries = (
            raw["data"]["items"]
            if "items" in raw.get("data", {})
            else raw["data"]["deliveries"]
        )

    with open(invoices_path, encoding="utf-8") as f:
        raw = json.load(f)
        invoices = raw["data"]["vat_invoices"]

    print(f"Loaded {len(deliveries)} deliveries, {len(invoices)} invoices")

    # Match
    results = match_invoices(deliveries, invoices, config)

    # Stats
    stats = summarize(results)
    print("\n=== STATS ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    out_dir = Path(deliveries_path).parent

    # output.json — full results
    out_json = out_dir / "output.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "invoice_id": r.invoice_id,
                    "status": r.status.value,
                    "matched_delivery_id": r.matched_delivery_id,
                    "confidence_score": r.confidence_score,
                    "score_gap": r.score_gap,
                    "reason": r.reason,
                    "top_candidates": r.top_candidates,
                }
                for r in results
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nSaved → {out_json}")

    # output.csv — matched invoices
    out_csv = out_dir / "output.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["delivery_id", "invoice_id", "confidence_score", "method"])
        for r in results:
            if r.matched_delivery_id:
                method = "llm" if r.status == MatchStatus.LLM_MATCH else "scoring"
                writer.writerow(
                    [r.matched_delivery_id, r.invoice_id, r.confidence_score, method]
                )
    print(f"Saved → {out_csv}")

    # manual_review.csv
    out_manual = out_dir / "manual_review.csv"
    with open(out_manual, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["invoice_id", "top_candidate_delivery_id", "score_gap", "reason"]
        )
        for r in results:
            if r.status == MatchStatus.MANUAL_REVIEW:
                top_del = r.top_candidates[0]["delivery_id"] if r.top_candidates else ""
                writer.writerow([r.invoice_id, top_del, r.score_gap, r.reason])
    print(f"Saved → {out_manual}")

    return results


if __name__ == "__main__":
    del_path = sys.argv[1] if len(sys.argv) > 1 else "large_set.json"
    inv_path = sys.argv[2] if len(sys.argv) > 2 else "large_set_vat.json"
    run(del_path, inv_path)

"""
LLM-based semantic address matching.

Called only when score gap < confidence_threshold (~44 cases in large dataset).
Batches multiple candidates into a single API call per invoice.
"""

import json
import os
import urllib.error
import urllib.request

from matcher.scorer import CandidateScore

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are a logistics address matching expert.
Given a VAT invoice delivery address and a list of candidate delivery dropoff locations,
determine which delivery the invoice most likely belongs to.

Consider:
- Street names, numbers, landmarks
- District, city, province
- Business names that may appear in abbreviated form

Return ONLY valid JSON. No explanation outside the JSON."""

USER_TEMPLATE = """Invoice delivery address:
{invoice_address}

Candidate deliveries:
{candidates}

Which delivery does this invoice belong to?
Return JSON:
{{
  "match": <candidate_number_1_indexed>,
  "confidence": "high" | "medium" | "low",
  "reason": "<brief explanation>"
}}"""


def _call_llm(system: str, user: str, max_tokens: int = 200) -> dict | None:
    """Make a single Anthropic API call. Returns parsed JSON or None on error."""
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            raw = data["content"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[llm_resolver] HTTP {e.code}: {body[:200]}")
        return None
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        print(f"[llm_resolver] Error: {e}")
        return None


def resolve(
    inv_address: str,
    candidates: list[CandidateScore],
) -> dict:
    """
    Use LLM to resolve ambiguous candidates.

    Returns:
        {
            'matched_delivery_id': int | None,
            'confidence': 'high' | 'medium' | 'low' | 'failed',
            'reason': str,
        }
    """
    if not candidates:
        return {
            "matched_delivery_id": None,
            "confidence": "failed",
            "reason": "no candidates",
        }

    # Build candidate list for prompt
    candidate_lines = []
    for i, c in enumerate(candidates, 1):
        name = c.delivery_name or ""
        desc = c.delivery_description or ""
        candidate_lines.append(f"{i}. {name} — {desc}")

    prompt = USER_TEMPLATE.format(
        invoice_address=inv_address or "(not provided)",
        candidates="\n".join(candidate_lines),
    )

    result = _call_llm(SYSTEM_PROMPT, prompt)

    if not result:
        return {
            "matched_delivery_id": None,
            "confidence": "failed",
            "reason": "LLM call failed",
        }

    try:
        match_idx = int(result.get("match", 0)) - 1  # convert to 0-indexed
        confidence = result.get("confidence", "low")
        reason = result.get("reason", "")

        if 0 <= match_idx < len(candidates):
            return {
                "matched_delivery_id": candidates[match_idx].delivery_id,
                "confidence": confidence,
                "reason": reason,
            }
        else:
            return {
                "matched_delivery_id": None,
                "confidence": "failed",
                "reason": f"invalid match index: {match_idx + 1}",
            }
    except (TypeError, ValueError) as e:
        return {
            "matched_delivery_id": None,
            "confidence": "failed",
            "reason": f"parse error: {e}",
        }

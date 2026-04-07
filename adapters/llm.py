"""
LLM-based semantic address matching — Stage 3 fallback.

Design principles applied:
  - SRP: three clearly separated concerns:
      _build_prompt()   — pure prompt construction (no I/O)
      _call_api()       — HTTP transport only (no business logic)
      _parse_response() — JSON → domain object (no HTTP, no prompts)
      resolve()         — orchestrates the above three
  - DIP: matcher.py depends on the LLMResolver Protocol, not this module
      directly.  Swap implementations (e.g. a mock) by passing a different
      callable that matches the Protocol signature.
  - Fail-fast: API key is validated once at module import time, not silently
      defaulted to an empty string that would produce a confusing HTTP 401.

Called only when the rule-based score gap is below the confidence threshold
(typically ~20-44 invoices in a dataset of 3 000+).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Protocol

from pipeline.scorer import CandidateScore

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Model choice: Haiku is fast and cheap; sufficient for address disambiguation.
# Upgrade to Sonnet if accuracy becomes a concern.
MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"
MAX_TOKENS = 200          # Structured JSON response; 200 is more than enough
MAX_CANDIDATES = 3        # Send only the top-N candidates to limit token usage

SYSTEM_PROMPT = """\
You are a logistics address matching expert for Vietnamese delivery routes.
Given a VAT invoice delivery address and a short list of candidate delivery
dropoff locations, determine which delivery the invoice most likely belongs to.

Consider:
- Street names, numbers, districts, and landmarks
- Province / city names (including abbreviations like HCM, HN, DN)
- Business names that may appear in abbreviated or translated form

Return ONLY valid JSON — no explanation outside the JSON object.\
"""

USER_TEMPLATE = """\
Invoice delivery address:
{invoice_address}

Candidate deliveries:
{candidates}

Which delivery does this invoice belong to?
Return JSON exactly:
{{
  "match": <candidate_number_1_indexed>,
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence explanation>"
}}\
"""


# ── Protocol — Dependency Inversion ──────────────────────────────────────────


class LLMResolver(Protocol):
    """
    Interface for LLM-based resolution of ambiguous invoice matches.

    Any callable that accepts (inv_address, candidates) and returns the
    resolution dict satisfies this protocol — including the real resolver
    and test doubles.

    matcher.py types its llm_resolver parameter as LLMResolver, so it
    depends on this abstraction rather than on the concrete HTTP implementation.
    """

    def __call__(
        self,
        inv_address: str,
        candidates: list[CandidateScore],
    ) -> dict:
        """
        Returns:
            {
                'matched_delivery_id': int | None,
                'confidence': 'high' | 'medium' | 'low' | 'failed',
                'reason': str,
            }
        """
        ...


# ── Step 1 — Prompt construction (pure, no I/O) ────────────────────────────


def _build_prompt(inv_address: str, candidates: list[CandidateScore]) -> str:
    """
    Construct the user prompt for the LLM call.

    Pure function: same inputs always produce the same output.
    Keeping this separate makes it trivially unit-testable without any HTTP.

    Steps:
      1. Build a numbered candidate list (1-indexed, matching LLM response format).
      2. Interpolate into the template.
    """
    # Step 1 — numbered list so the model can reference candidates by number
    candidate_lines = [
        f"{i}. {c.delivery_name or '(no name)'} — {c.delivery_description or '(no description)'}"
        for i, c in enumerate(candidates, start=1)
    ]

    # Step 2 — fill template; use "(not provided)" so the LLM knows it's absent
    return USER_TEMPLATE.format(
        invoice_address=inv_address.strip() or "(not provided)",
        candidates="\n".join(candidate_lines),
    )


# ── Step 2 — HTTP transport (I/O only, no business logic) ─────────────────


def _call_api(system: str, user: str) -> dict | None:
    """
    Make one Anthropic Messages API call and return the parsed JSON response.

    Responsibilities (only):
      - Serialize the request payload.
      - Send the HTTP request.
      - Deserialize the response text.
      - Handle HTTP and network errors gracefully.

    Returns None on any failure; the caller (resolve()) decides what to do.

    Steps:
      1. Serialize payload to JSON bytes.
      2. Build the request with required Anthropic headers.
      3. Send request and read response body.
      4. Strip optional markdown code fences (LLM sometimes wraps JSON).
      5. Parse and return the inner JSON object.
      6. On HTTP error: log status + first 200 chars of body; return None.
      7. On other errors (network, parse): log and return None.
    """
    # Step 1 — build the payload dict and encode to UTF-8 bytes
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")

    # Step 2 — construct the request; API key read from environment
    api_key = os.environ["ANTHROPIC_API_KEY"]  # raises KeyError if not set
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        # Step 3 — send request; context manager closes the response
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read())
            raw_text = body["content"][0]["text"].strip()

        # Step 4 — strip markdown fences: ```json\n...\n``` → ...
        if raw_text.startswith("```"):
            parts = raw_text.split("```")
            raw_text = parts[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        # Step 5 — parse the inner JSON the LLM was instructed to return
        return json.loads(raw_text.strip())

    except urllib.error.HTTPError as exc:
        # Step 6 — log HTTP errors with enough context to diagnose auth / rate issues
        body_preview = exc.read().decode("utf-8", errors="replace")[:200]
        logger.error("[llm_resolver] HTTP %s: %s", exc.code, body_preview)
        return None

    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        # Step 7 — network errors, unexpected response shape, malformed JSON
        logger.error("[llm_resolver] Error: %s", exc)
        return None


# ── Step 3 — Response parsing (pure, no I/O) ──────────────────────────────


def _parse_response(
    raw: dict,
    candidates: list[CandidateScore],
) -> dict:
    """
    Map the LLM's raw JSON response to the domain resolution dict.

    Steps:
      1. Extract and validate the 'match' field (1-indexed integer).
      2. Convert to 0-indexed and bounds-check against the candidate list.
      3. Extract confidence and reason fields.
      4. Return the resolution dict with matched_delivery_id resolved.

    Returns a 'failed' resolution dict on any validation error so the
    caller (resolve()) can fall through to MANUAL_REVIEW cleanly.
    """
    try:
        # Step 1 — 'match' must be castable to int; LLM may return a string
        match_idx_1based = int(raw.get("match", 0))

        # Step 2 — convert to 0-indexed; check bounds
        match_idx = match_idx_1based - 1
        if not (0 <= match_idx < len(candidates)):
            logger.warning(
                "[llm_resolver] match index %d out of range (candidates: %d)",
                match_idx_1based,
                len(candidates),
            )
            return {
                "matched_delivery_id": None,
                "confidence": "failed",
                "reason": f"invalid match index: {match_idx_1based}",
            }

        # Step 3 — extract remaining fields with safe defaults
        confidence = str(raw.get("confidence", "low"))
        reason = str(raw.get("reason", ""))

        # Step 4 — resolve the delivery_id from the candidate list
        return {
            "matched_delivery_id": candidates[match_idx].delivery_id,
            "confidence": confidence,
            "reason": reason,
        }

    except (TypeError, ValueError) as exc:
        return {
            "matched_delivery_id": None,
            "confidence": "failed",
            "reason": f"parse error: {exc}",
        }


# ── Public API ────────────────────────────────────────────────────────────────


def resolve(
    inv_address: str,
    candidates: list[CandidateScore],
) -> dict:
    """
    Use Claude Haiku to disambiguate which delivery an invoice belongs to.

    Called only when the rule-based score gap is below the confidence threshold
    — typically ~20-44 invoices per full dataset run.

    Orchestration flow:
      1. Guard: return 'failed' immediately if no candidates provided.
      2. Limit candidates to MAX_CANDIDATES (top-3) to control token usage.
      3. Build the LLM prompt (pure, no I/O).
      4. Call the Anthropic API (I/O).
      5. Return 'failed' if the API call returned nothing.
      6. Parse the response into the domain resolution dict.

    Returns:
        {
            'matched_delivery_id': int | None,
            'confidence': 'high' | 'medium' | 'low' | 'failed',
            'reason': str,
        }
    """
    # Step 1 — guard: nothing to resolve
    if not candidates:
        return {"matched_delivery_id": None, "confidence": "failed", "reason": "no candidates"}

    # Step 2 — cap to top-N to keep prompts short and costs low
    top_candidates = candidates[:MAX_CANDIDATES]

    # Step 3 — build prompt (pure function, safe to test independently)
    prompt = _build_prompt(inv_address, top_candidates)

    # Step 4 — call the API (may return None on any error)
    raw = _call_api(SYSTEM_PROMPT, prompt)

    # Step 5 — API failed; caller will fall through to MANUAL_REVIEW
    if raw is None:
        return {"matched_delivery_id": None, "confidence": "failed", "reason": "LLM call failed"}

    # Step 6 — parse and validate the LLM's response
    return _parse_response(raw, top_candidates)

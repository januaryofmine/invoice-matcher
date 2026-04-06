"""
LLM-based Vietnamese address utilities:
  - Province extraction (batched, 1 API call)
  - Address similarity check (per-pair, called only when needed)
"""

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"


# ── API helper ────────────────────────────────────────────────────────────────


def _call_llm(system: str, user: str, max_tokens: int = 1000) -> str | None:
    """Make a single Anthropic API call. Returns text content or None on error."""
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
            return data["content"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[llm] HTTP {e.code}: {body[:200]}")
        return None
    except (urllib.error.URLError, KeyError) as e:
        print(f"[llm] Error: {e}")
        return None


# ── Step 3a: Province extraction ──────────────────────────────────────────────

_PROVINCE_SYSTEM = """You are a Vietnamese address parser.
Given a list of Vietnamese addresses, extract the province/city (tỉnh/thành phố) for each.
Normalize to standard form, e.g.:
  - "TP. Hồ Chí Minh", "TP.HCM", "Thành phố Hồ Chí Minh" → "Hồ Chí Minh"
  - "Tỉnh Long An", "Long An" → "Long An"
  - "Đà Nẵng", "TP. Đà Nẵng" → "Đà Nẵng"
Return ONLY a JSON object mapping each address to its province. No explanation."""

_PROVINCE_USER = """Extract the province/city from each address below.
Return ONLY valid JSON, no markdown, no explanation.

Addresses:
{addresses}

Expected format:
{{"address1": "Province1", "address2": "Province2"}}"""


def extract_provinces(addresses: list[str]) -> dict[str, str]:
    """
    Batch extract province from all address strings in a single LLM call.
    Returns dict mapping address → province. Missing addresses default to ''.
    """
    if not addresses:
        return {}

    unique = list(dict.fromkeys(a for a in addresses if a))
    if not unique:
        return {}

    prompt = _PROVINCE_USER.format(addresses="\n".join(f"- {addr}" for addr in unique))

    raw = _call_llm(_PROVINCE_SYSTEM, prompt, max_tokens=4096)
    if not raw:
        return {addr: "" for addr in addresses}

    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return {addr: result.get(addr, "") for addr in addresses}
    except json.JSONDecodeError as e:
        print(f"[province_extractor] JSON parse error: {e}")
        return {addr: "" for addr in addresses}


def provinces_match(province_a: str, province_b: str) -> bool:
    """Check if two province strings refer to the same province.
    Normalizes diacritics and common abbreviations before comparing.
    """
    if not province_a or not province_b:
        return False

    def normalize(s: str) -> str:
        s = s.strip().upper()
        # Remove diacritics
        nfkd = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in nfkd if not unicodedata.combining(c))
        # Normalize common abbreviations
        s = s.replace("TP.", "").replace("TP ", "").replace("THANH PHO ", "")
        s = s.replace("TINH ", "").replace("TINH.", "")
        return s.strip()

    return normalize(province_a) == normalize(province_b)


# ── Step 3b: Exact/near-exact address match ───────────────────────────────────


def _normalize_address(addr: str) -> str:
    """Normalize address for exact comparison: uppercase, remove punctuation/spaces."""
    if not addr:
        return ""
    # Remove diacritics for near-exact match
    nfkd = unicodedata.normalize("NFKD", addr.upper())
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Remove punctuation and collapse whitespace
    return re.sub(r"[^\w\s]", " ", ascii_str).split()


def addresses_match_exact(inv_addr: str, dropoff_addr: str) -> bool:
    """
    Near-exact address match after normalization.
    Checks if meaningful tokens from invoice address appear in dropoff address.
    Requires at least 2 significant tokens to match (avoids single-word false positives).
    """
    inv_tokens = set(_normalize_address(inv_addr))
    dropoff_tokens = set(_normalize_address(dropoff_addr))

    # Filter out very short tokens (< 3 chars) and common words
    _IGNORE = {
        "THE",
        "AND",
        "VIET",
        "NAM",
        "SO",
        "KHU",
        "PHUONG",
        "QUAN",
        "TINH",
        "THANH",
        "PHO",
    }
    inv_tokens = {t for t in inv_tokens if len(t) >= 3 and t not in _IGNORE}
    dropoff_tokens = {t for t in dropoff_tokens if len(t) >= 3 and t not in _IGNORE}

    if not inv_tokens or not dropoff_tokens:
        return False

    overlap = inv_tokens & dropoff_tokens
    # Require at least 2 tokens overlap OR overlap covers >50% of invoice tokens
    return len(overlap) >= 2 or (len(overlap) / len(inv_tokens)) >= 0.5


# ── Step 3c: LLM address similarity ──────────────────────────────────────────

_ADDR_SYSTEM = """You are a Vietnamese address expert.
Given an invoice delivery address and a delivery dropoff address, determine if they refer to the same location.
Consider abbreviations, different formats, and minor differences.
Return ONLY "yes" or "no". No explanation."""

_ADDR_USER = """Invoice delivery address: {inv_addr}
Delivery dropoff address: {dropoff_addr}

Are these the same location? Answer only "yes" or "no"."""


def addresses_match_llm(inv_addr: str, dropoff_addr: str) -> bool:
    """
    Use LLM to check if two addresses refer to the same location.
    Called only when exact match fails.
    """
    if not inv_addr or not dropoff_addr:
        return False

    prompt = _ADDR_USER.format(inv_addr=inv_addr, dropoff_addr=dropoff_addr)
    raw = _call_llm(_ADDR_SYSTEM, prompt, max_tokens=10)

    if not raw:
        return False
    return raw.strip().lower().startswith("yes")

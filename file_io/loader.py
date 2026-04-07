"""
I/O layer — input data loading.

Responsibility (SRP): read raw JSON files from disk and extract the record
lists that the pipeline expects.  No matching logic, no output writing.

Knowing the upstream JSON shape lives here and only here — if the API
response structure changes, this is the only file that needs updating.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_deliveries(path: str) -> list[dict]:
    """
    Load and extract the delivery list from a JSON file.

    The upstream API wraps records in two possible shapes:
      { "data": { "items": [...] } }       — newer API response
      { "data": { "deliveries": [...] } }  — legacy shape

    Steps:
      1. Validate that the file exists before opening (clear error message).
      2. Parse JSON.
      3. Extract the record list from either known wrapper shape.
      4. Return the flat list.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if the JSON structure is unrecognised.
    """
    file = Path(path)

    if not file.exists():
        raise FileNotFoundError(f"Deliveries file not found: {path}")

    logger.info("Loading deliveries from %s", path)

    with open(file, encoding="utf-8") as f:
        raw = json.load(f)

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

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if the JSON structure is unrecognised.
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

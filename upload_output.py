"""
Upload output.json to Vercel Blob.
Usage: python upload_output.py
"""

import os
import sys
import json
import urllib.request

BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "output.json")


def upload():
    if not BLOB_TOKEN:
        print("ERROR: BLOB_READ_WRITE_TOKEN not set in environment")
        sys.exit(1)

    if not os.path.exists(OUTPUT_FILE):
        print(f"ERROR: {OUTPUT_FILE} not found — run match_invoices.py first")
        sys.exit(1)

    print(f"Uploading {OUTPUT_FILE} to Vercel Blob...")

    with open(OUTPUT_FILE, "rb") as f:
        data = f.read()

    req = urllib.request.Request(
        "https://blob.vercel-storage.com/output.json",
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "Content-Type": "application/json",
            "x-add-random-suffix": "0",
        },
    )

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        url = result["url"]
        print(f"Done! URL: {url}")
        return url


if __name__ == "__main__":
    upload()

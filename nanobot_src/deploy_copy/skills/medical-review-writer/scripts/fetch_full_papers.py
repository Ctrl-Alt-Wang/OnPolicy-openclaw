#!/usr/bin/env python3
"""
Batch fetch full paper payloads from the InfoX-Med full-paper API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://60.205.166.229:9306"
DEFAULT_TOKEN = "e3f62087e126439aa12ad4637cf4f12b|1106970"


def fetch_one(base_url: str, token: str, doc_id: str, raw: bool) -> dict[str, Any]:
    query = "?raw=true" if raw else ""
    url = f"{base_url.rstrip('/')}/api/v1/paper/doc-id/{urllib.parse.quote(str(doc_id))}{query}"
    req = urllib.request.Request(url, headers={"X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"doc_id": doc_id, "ok": True, "response": payload}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "doc_id": doc_id,
            "ok": False,
            "status": exc.code,
            "error": body,
        }
    except Exception as exc:  # noqa: BLE001
        return {"doc_id": doc_id, "ok": False, "error": str(exc)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch full paper records by doc_id.")
    parser.add_argument("--doc-id", nargs="+", required=True, help="One or more doc_id values.")
    parser.add_argument("--base-url", default=os.environ.get("FULL_PAPER_API_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token", default=os.environ.get("FULL_PAPER_API_TOKEN", DEFAULT_TOKEN))
    parser.add_argument("--raw", action="store_true", help="Request raw=true from the API.")
    parser.add_argument("--output", "-o", help="Write JSON output to this path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = [
        fetch_one(args.base_url, args.token, doc_id, args.raw)
        for doc_id in args.doc_id
    ]

    text = json.dumps(
        {
            "base_url": args.base_url,
            "raw": args.raw,
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

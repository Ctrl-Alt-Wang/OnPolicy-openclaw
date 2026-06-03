#!/usr/bin/env python3
"""
Turn InfoX-Med search results into a deduplicated markdown review packet.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_docs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    docs_by_id: dict[str, dict[str, Any]] = {}
    categories_by_id: dict[str, set[str]] = defaultdict(set)

    if "records" in payload:
        for record in payload.get("records", []):
            doc_id = str(record.get("id") or record.get("doc_id") or "")
            if not doc_id:
                continue
            docs_by_id.setdefault(doc_id, record)
            categories_by_id[doc_id].add("free")
    else:
        for category, records in payload.items():
            if not isinstance(records, list):
                continue
            for record in records:
                doc_id = str(record.get("id") or record.get("doc_id") or "")
                if not doc_id:
                    continue
                docs_by_id.setdefault(doc_id, record)
                categories_by_id[doc_id].add(category)

    normalized = []
    for doc_id, record in docs_by_id.items():
        normalized.append(
            {
                "doc_id": doc_id,
                "title": record.get("title") or record.get("docTitle") or "",
                "journal": record.get("journal") or record.get("docSourceJournal") or record.get("docSimpleJournal") or "",
                "publish_date": record.get("publish_date") or record.get("publish_time") or record.get("docPublishTime") or "",
                "impact_factor": record.get("impact_factor") or record.get("docIf") or "",
                "publication_type": record.get("publication_type") or record.get("docPublishType") or "",
                "link": record.get("link") or record.get("url") or "",
                "categories": sorted(categories_by_id.get(doc_id, set())),
            }
        )

    normalized.sort(
        key=lambda item: (
            item["publish_date"] or "",
            str(item["impact_factor"] or ""),
            item["doc_id"],
        ),
        reverse=True,
    )
    return normalized


def to_markdown(topic: str, docs: list[dict[str, Any]], top: int) -> str:
    picked = docs[:top] if top > 0 else docs
    lines = [
        f"# {topic or 'Review Evidence Packet'}",
        "",
        f"- Total deduplicated records: {len(docs)}",
        f"- Displayed records: {len(picked)}",
        "",
        "| # | Category | Doc ID | Year | IF | Type | Title | Journal | Link |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for idx, doc in enumerate(picked, start=1):
        year = str(doc["publish_date"])[:4] if doc["publish_date"] else ""
        lines.append(
            "| {idx} | {category} | {doc_id} | {year} | {impact_factor} | {pub_type} | {title} | {journal} | {link} |".format(
                idx=idx,
                category=", ".join(doc["categories"]) or "-",
                doc_id=doc["doc_id"],
                year=year or "-",
                impact_factor=doc["impact_factor"] or "-",
                pub_type=(doc["publication_type"] or "-").replace("|", "/"),
                title=(doc["title"] or "-").replace("|", "/"),
                journal=(doc["journal"] or "-").replace("|", "/"),
                link=doc["link"] or "-",
            )
        )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a markdown review packet from search JSON.")
    parser.add_argument("--input", "-i", required=True, help="Search result JSON path.")
    parser.add_argument("--output", "-o", help="Markdown output path.")
    parser.add_argument("--topic", default="", help="Optional review topic title.")
    parser.add_argument("--top", type=int, default=40, help="Max records to render.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_payload(Path(args.input))
    docs = normalize_docs(payload)
    markdown = to_markdown(args.topic, docs, args.top)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

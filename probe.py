#!/usr/bin/env python3
"""
One-off probe: dump ALL Firestore field keys (+ type tags) for one real memory doc.

Run AFTER auth is configured:
  cd neo-recall
  python -m venv .venv && source .venv/bin/activate
  pip install -e .
  neo-recall-auth
  python probe.py

Writes probe_dump.json (gitignored). Confirm mom/transcript key names before trusting
get_memory / get_transcript against Firestore.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from neosapien_mcp.client.firestore import FirestoreClient
from neosapien_mcp.client import parse


def _type_tag(node: dict) -> str:
    for k in (
        "stringValue",
        "doubleValue",
        "integerValue",
        "booleanValue",
        "timestampValue",
        "arrayValue",
        "mapValue",
        "nullValue",
        "referenceValue",
    ):
        if k in node:
            return k
    return "unknown"


async def main() -> None:
    client = FirestoreClient()
    try:
        memories = await client.list_all_memories()
        if not memories:
            print("No memories returned — check auth.")
            return
        # Prefer a recent non-trivial memory
        target = next((m for m in memories if m.summary and m.duration_sec > 10), memories[0])
        print(f"Probing memory id={target.id} title={target.title!r}")
        doc = await client.get_document(target.id)
        fields = doc.get("fields") or {}
        report = {
            "memory_id": target.id,
            "title": target.title,
            "field_keys": parse.list_field_keys(doc),
            "field_types": {
                k: _type_tag(v if isinstance(v, dict) else {}) for k, v in fields.items()
            },
            "mom_preview": parse.parse_detail(doc, include_mom=True).mom
            if parse.parse_detail(doc, include_mom=True)
            else None,
            "transcript_segment_count": len(parse.parse_transcript(doc)),
            # Truncated raw fields for inspection (no secrets expected)
            "raw_fields_sample": {k: fields[k] for k in list(fields)[:40]},
        }
        out = Path(__file__).resolve().parent / "probe_dump.json"
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"Wrote {out}")
        print("Keys:", ", ".join(report["field_keys"]))
        print("Types:", json.dumps(report["field_types"], indent=2))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

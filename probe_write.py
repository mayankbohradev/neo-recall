#!/usr/bin/env python3
"""
One-off WRITE probe: establish the write contract before building write tools.

The desktop app (neo-memory-manager) only ever implemented hard delete, so there is
no reverse-engineered contract for edit / participants / archive. This probe answers
four questions against the live API, using the LOWEST-QUALITY memory as the target:

  Q1. Does Firestore accept PATCH + updateMask with our Firebase ID token?
  Q2. Does a PATCH SURVIVE, or does the backend (neo-backend-v2, the primary store)
      sync over it? -> write, wait, re-read.
  Q3. Which field actually backs "participants"? parse.py:85 falls back
      `participants or entities`, so writing the wrong one is a silent no-op.
  Q4. Is `archived` writable from our side? (It's in the schema and filterable,
      but nothing in the codebase has ever written it.)

SAFETY
  - Targets the lowest-quality memory (rank_by_quality, ascending) and prints it
    for confirmation before touching anything.
  - Requires interactive typed confirmation. No flags, no auto-run.
  - Captures the original doc to probe_write_backup.json BEFORE any write.
  - Reverts every field it touches, then verifies the revert.
  - Touches ONLY: archived (bool), participants/entities (array). Never title/summary,
    never delete.

Run:
  cd neo-recall && source .venv/bin/activate && python probe_write.py
Writes probe_write_report.json + probe_write_backup.json (both gitignored).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from neosapien_mcp import constants
from neosapien_mcp.client import parse
from neosapien_mcp.client.firestore import FirestoreClient
from neosapien_mcp.enrich.quality import compute_quality_score

SETTLE_SECONDS = 20  # how long to wait before re-reading, to catch a backend sync-over
PROBE_MARKER = "__neo_recall_probe__"


def _doc_url(uid: str, memory_id: str) -> str:
    return (
        f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}"
        f"/memories/{quote(memory_id, safe='')}"
    )


async def _patch(
    client: FirestoreClient,
    uid: str,
    memory_id: str,
    fields: dict[str, Any],
    mask: list[str],
) -> tuple[int, str]:
    """PATCH with an explicit updateMask so we only ever touch named fields."""
    headers, _ = await client._auth_headers()
    url = _doc_url(uid, memory_id)
    query = "&".join(f"updateMask.fieldPaths={quote(f, safe='')}" for f in mask)
    resp = await client._http.patch(
        f"{url}?{query}",
        headers={**headers, "Content-Type": "application/json"},
        json={"fields": fields},
    )
    return resp.status_code, resp.text[:300]


async def _read_fields(client: FirestoreClient, memory_id: str) -> dict[str, Any]:
    doc = await client.get_document(memory_id)
    return doc.get("fields") or {}


def _str_array(values: list[str]) -> dict[str, Any]:
    return {"arrayValue": {"values": [{"stringValue": v} for v in values]}}


async def main() -> None:
    client = FirestoreClient()
    report: dict[str, Any] = {}
    try:
        _, uid = await client._auth_headers()
        memories = await client.list_all_memories()
        if not memories:
            print("No memories returned — check auth (`neo-recall-auth`).")
            return

        # --- pick the lowest-quality memory ---------------------------------
        scored = sorted(memories, key=lambda m: (compute_quality_score(m), m.created_at))
        target = scored[0]
        q = compute_quality_score(target)

        print("\n" + "=" * 68)
        print(f"WRITE PROBE TARGET (lowest-quality memory of {len(memories)})")
        print("=" * 68)
        print(f"  id            : {target.id}")
        print(f"  title         : {target.title!r}")
        print(f"  summary       : {(target.summary or '')[:100]!r}")
        print(f"  created_at    : {target.created_at}")
        print(f"  duration_sec  : {target.duration_sec}")
        print(f"  participants  : {target.participants}")
        print(f"  archived      : {target.archived}")
        print(f"  quality_score : {q}/100")
        print("=" * 68)
        print("\nThis probe will, on THIS memory only:")
        print("  1. back up the full raw doc to probe_write_backup.json")
        print("  2. toggle `archived`, wait, re-read, then revert it")
        print("  3. append a marker to participants/entities, re-read, then revert")
        print("It will NOT touch title/summary and will NOT delete anything.\n")

        answer = input("Type the memory id above to proceed (anything else aborts): ").strip()
        if answer != target.id:
            print("Aborted — no writes performed.")
            return

        # --- back up BEFORE any write ---------------------------------------
        original_doc = await client.get_document(target.id)
        backup = Path(__file__).resolve().parent / "probe_write_backup.json"
        backup.write_text(json.dumps(original_doc, indent=2, default=str))
        print(f"\n[backup] wrote {backup}")

        original_fields = original_doc.get("fields") or {}
        report["memory_id"] = target.id
        report["field_keys_before"] = sorted(original_fields.keys())

        # --- Q3: which field actually backs participants? --------------------
        has_participants_key = "participants" in original_fields
        has_entities_key = "entities" in original_fields
        parts_raw = parse._arr(original_fields, "participants")
        ents_raw = parse._arr(original_fields, "entities")
        backing = (
            "participants"
            if parts_raw
            else ("entities" if ents_raw else ("participants" if has_participants_key else None))
        )
        report["participants_backing_field"] = {
            "participants_key_present": has_participants_key,
            "entities_key_present": has_entities_key,
            "participants_values": parts_raw,
            "entities_values": ents_raw,
            "resolved_backing_field": backing,
            "note": "parse.py:85 reads `participants or entities` — a write must pick one.",
        }
        print(f"[probe] participants backing field resolves to: {backing!r}")

        # --- Q1/Q4: is `archived` writable? ----------------------------------
        orig_archived = parse._bool(original_fields, "archived")
        new_archived = not orig_archived
        code, body = await _patch(
            client,
            uid,
            target.id,
            {"archived": {"booleanValue": new_archived}},
            ["archived"],
        )
        print(f"[probe] PATCH archived={new_archived} -> HTTP {code}")
        report["archived_patch"] = {"status": code, "body": body, "attempted": new_archived}

        if code == 200:
            immediate = parse._bool(await _read_fields(client, target.id), "archived")
            print(f"[probe] immediate re-read archived = {immediate}")
            print(f"[probe] waiting {SETTLE_SECONDS}s to detect a backend sync-over...")
            await asyncio.sleep(SETTLE_SECONDS)
            settled = parse._bool(await _read_fields(client, target.id), "archived")
            print(f"[probe] after {SETTLE_SECONDS}s archived = {settled}")
            report["archived_patch"].update(
                immediate_read=immediate,
                settled_read=settled,
                survived=(settled == new_archived),
            )
            # revert
            rcode, _ = await _patch(
                client,
                uid,
                target.id,
                {"archived": {"booleanValue": orig_archived}},
                ["archived"],
            )
            reverted = parse._bool(await _read_fields(client, target.id), "archived")
            print(
                f"[probe] revert archived -> HTTP {rcode}, now {reverted} "
                f"(original {orig_archived})"
            )
            report["archived_patch"]["revert_ok"] = reverted == orig_archived

        # --- Q1/Q2: is the participants array writable + does it survive? -----
        if backing:
            orig_list = parse._arr(original_fields, backing)
            probe_list = [*orig_list, PROBE_MARKER]
            code, body = await _patch(
                client, uid, target.id, {backing: _str_array(probe_list)}, [backing]
            )
            print(f"[probe] PATCH {backing} += marker -> HTTP {code}")
            report["participants_patch"] = {
                "field": backing,
                "status": code,
                "body": body,
                "original": orig_list,
            }
            if code == 200:
                immediate = parse._arr(await _read_fields(client, target.id), backing)
                print(f"[probe] immediate re-read {backing} = {immediate}")
                print(f"[probe] waiting {SETTLE_SECONDS}s to detect a backend sync-over...")
                await asyncio.sleep(SETTLE_SECONDS)
                settled = parse._arr(await _read_fields(client, target.id), backing)
                print(f"[probe] after {SETTLE_SECONDS}s {backing} = {settled}")
                report["participants_patch"].update(
                    immediate_read=immediate,
                    settled_read=settled,
                    survived=(PROBE_MARKER in settled),
                )
                # revert
                rcode, _ = await _patch(
                    client, uid, target.id, {backing: _str_array(orig_list)}, [backing]
                )
                after = parse._arr(await _read_fields(client, target.id), backing)
                print(
                    f"[probe] revert {backing} -> HTTP {rcode}, now {after} (original {orig_list})"
                )
                report["participants_patch"]["revert_ok"] = after == orig_list
                if PROBE_MARKER in after:
                    print(
                        "\n  *** WARNING: marker still present after revert. "
                        "Restore manually from probe_write_backup.json ***\n"
                    )
        else:
            print("[probe] no participants/entities field on target — skipping array probe.")
            report["participants_patch"] = {"skipped": "no participants/entities field on target"}

        out = Path(__file__).resolve().parent / "probe_write_report.json"
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"\n[report] wrote {out}")
        print(json.dumps(report, indent=2, default=str))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

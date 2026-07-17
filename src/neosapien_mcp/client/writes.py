"""Firestore WRITE client — archive / unarchive / edit / participants.

Contract notes (see probe_write.py, which establishes these against the live API):

* Writes go to Firestore via PATCH + updateMask so we only ever touch named fields.
  A PATCH without updateMask REPLACES the whole document — never issue one.
* neo-backend-v2 is the primary store and Firestore is a sync layer (the desktop app
  deletes from both). A Firestore-only write may therefore be synced over. Callers get
  `verified` back from a post-write re-read so a silent revert is visible, not assumed.
* Participants live in EITHER `participants` OR `entities` — parse.py reads
  `participants or entities` as a fallback. Writing the wrong key returns HTTP 200 and
  changes nothing observable. resolve_participants_field() picks the live one per-doc.
* We never hard-delete. `archived` is a first-class schema field the Neo app itself
  sets, so archive is reversible and is the delete primitive we expose.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from neosapien_mcp import constants
from neosapien_mcp.client import parse
from neosapien_mcp.client.firestore import FirestoreClient


class WriteError(RuntimeError):
    """Raised when a write is rejected or cannot be verified."""


def str_array(values: list[str]) -> dict[str, Any]:
    """Encode a python list[str] as a Firestore typed arrayValue."""
    return {"arrayValue": {"values": [{"stringValue": v} for v in values]}}


def resolve_participants_field(fields: dict[str, Any]) -> str:
    """
    Decide which Firestore key actually backs 'participants' for THIS doc.

    parse.py:85 reads `participants or entities`. If a doc's people live in
    `entities`, patching `participants` is a silent no-op — the reader keeps
    falling through to `entities`. So mirror the reader's precedence exactly:
    whichever field the reader would have read from is the one we write to.
    """
    if parse._arr(fields, "participants"):
        return "participants"
    if parse._arr(fields, "entities"):
        return "entities"
    # Both empty — prefer an existing key, else default to the canonical name.
    if "participants" in fields:
        return "participants"
    if "entities" in fields:
        return "entities"
    return "participants"


class WriteClient:
    """Thin write layer over FirestoreClient's auth + http session."""

    def __init__(self, reader: FirestoreClient | None = None) -> None:
        self._reader = reader or FirestoreClient()

    async def aclose(self) -> None:
        await self._reader.aclose()

    def _doc_url(self, uid: str, memory_id: str) -> str:
        return (
            f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}"
            f"/memories/{quote(memory_id, safe='')}"
        )

    async def patch_fields(
        self,
        memory_id: str,
        fields: dict[str, Any],
        mask: list[str],
    ) -> dict[str, Any]:
        """
        PATCH named fields with an explicit updateMask, retrying once on 401.

        updateMask is REQUIRED: without it Firestore replaces the entire document,
        which would wipe transcript/MOM/everything not named here.
        """
        if not mask:
            raise WriteError("refusing to PATCH without an updateMask (would replace the doc)")

        headers, uid = await self._reader._auth_headers()
        query = "&".join(f"updateMask.fieldPaths={quote(f, safe='')}" for f in mask)
        url = f"{self._doc_url(uid, memory_id)}?{query}"
        resp = await self._reader._http.patch(
            url, headers={**headers, "Content-Type": "application/json"}, json={"fields": fields}
        )
        if resp.status_code == 401:
            from neosapien_mcp.auth import tokens

            tokens.invalidate()
            headers, uid = await self._reader._auth_headers(force_refresh=True)
            url = f"{self._doc_url(uid, memory_id)}?{query}"
            resp = await self._reader._http.patch(
                url,
                headers={**headers, "Content-Type": "application/json"},
                json={"fields": fields},
            )
        if resp.status_code == 404:
            raise KeyError(f"Memory not found: {memory_id}")
        if resp.status_code == 403:
            raise WriteError(
                f"Firestore rejected the write (403) for {memory_id}. Your token may be "
                "read-scoped for this field, or security rules forbid client writes."
            )
        if not resp.is_success:
            raise WriteError(f"Firestore PATCH {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def read_fields(self, memory_id: str) -> dict[str, Any]:
        doc = await self._reader.get_document(memory_id)
        return doc.get("fields") or {}

    async def delete_memories(self, memory_ids: list[str]) -> dict[str, Any]:
        """
        PERMANENT dual-store delete. Ported from neo-memory-manager/neosapien.rs:285.

        Order matters and mirrors the desktop app: neo-backend-v2 (PostgreSQL) is the
        SOURCE OF TRUTH and is deleted FIRST; Firestore is the downstream sync layer and
        is deleted per-id after. A Firestore-only delete does NOT propagate to Postgres —
        the memory reappears (SECURITY_LEARNINGS.md §7 drift bug). Firestore 404s are
        tolerated: the row may already be gone.

        Verified against the backend, not against Firestore. Firestore echoing our own
        write back is not proof — the app reads Postgres.
        """
        from neosapien_mcp.auth import tokens

        id_token, uid = await tokens.get_id_token()
        headers = {"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"}

        # Step 1 — source of truth first.
        backend_resp = await self._reader._http.request(
            "DELETE",
            f"{constants.BACKEND_BASE}/memories/delete",
            headers=headers,
            json=list(memory_ids),
        )
        if not backend_resp.is_success:
            raise WriteError(
                f"Backend delete failed ({backend_resp.status_code}): "
                f"{backend_resp.text[:200]}. Nothing was deleted from Firestore either."
            )

        # Step 2 — sync layer. Best-effort; a 404 means it was already gone.
        firestore_deleted, firestore_errors = 0, []
        for mid in memory_ids:
            url = self._doc_url(uid, mid)
            r = await self._reader._http.delete(url, headers=headers)
            if r.is_success or r.status_code == 404:
                firestore_deleted += 1
            else:
                firestore_errors.append(f"{mid}: {r.status_code}")

        # Step 3 — verify against the SOURCE OF TRUTH, never Firestore.
        still_present = await self._ids_still_in_backend(memory_ids, headers)
        return {
            "requested": len(memory_ids),
            "backend_status": backend_resp.status_code,
            "firestore_deleted": firestore_deleted,
            "firestore_errors": firestore_errors,
            "still_present_in_backend": still_present,
            "verified": not still_present,
        }

    async def _ids_still_in_backend(self, memory_ids: list[str], headers: dict) -> list[str]:
        """
        Re-read the backend to confirm the rows are really gone.

        Must paginate: page_size caps at 100, so scanning one page would miss any
        memory outside the newest 100 and report a false "verified" on a delete.
        """
        survivors = await self._scan_backend(headers, set(memory_ids))
        return sorted(survivors.keys())

    async def _scan_backend(
        self, headers: dict, want: set[str], *, max_pages: int = 60
    ) -> dict[str, dict[str, Any]]:
        """
        Cursor-paginate the backend looking for specific ids.

        page_size is HARD-CAPPED AT 100 — 101+ returns 422 with an empty body. A single
        unpaginated call therefore only ever sees the newest 100 memories, so any check
        for an older memory would wrongly conclude it is absent. Follow next_cursor.
        Stops early once every wanted id is found.
        """
        found: dict[str, dict[str, Any]] = {}
        for flag in ("false", "true"):  # active view, then archived view
            cursor: str | None = None
            for _ in range(max_pages):
                url = f"{constants.BACKEND_BASE}/memories?is_archived={flag}&page_size=100"
                if cursor:
                    url += f"&cursor={quote(cursor, safe='')}"
                r = await self._reader._http.get(url, headers=headers)
                if not r.is_success:
                    break
                body = r.json()
                for x in body.get("data") or []:
                    if x.get("id") in want:
                        found[x["id"]] = x
                if len(found) == len(want):
                    return found
                pag = body.get("pagination") or {}
                cursor = pag.get("next_cursor")
                if not cursor or not pag.get("has_more"):
                    break
        return found

    async def _backend_memory(self, memory_id: str, headers: dict) -> dict[str, Any] | None:
        """Fetch one memory from the backend (the source of truth the phone reads)."""
        return (await self._scan_backend(headers, {memory_id})).get(memory_id)

    async def update_backend_memory(
        self, memory_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """
        PATCH /memories/update — the source of truth the phone app reads.

        Body shape is taken verbatim from the official NeoSapien app bundle: it always
        sends the FULL object, not a sparse patch (a sparse body 500s). So we read the
        current row, overlay `changes`, and echo everything else back unchanged.

        NOTE: this endpoint silently IGNORES fields outside its schema — it returns
        200 {"success": true} regardless. `archived` is one such field. Never infer
        success from the status code; always verify by re-reading.
        """
        from neosapien_mcp.auth import tokens

        id_token, _ = await tokens.get_id_token()
        headers = {"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"}

        cur = await self._backend_memory(memory_id, headers)
        if cur is None:
            raise KeyError(f"Memory not found in backend: {memory_id}")

        body = {
            "memory_id": memory_id,
            "mom": cur.get("mom"),
            "entities": cur.get("entities"),
            "title": cur.get("title"),
            "tags": cur.get("tags"),
            "topics": cur.get("topics"),
            "domain": cur.get("domain"),
            "summary": cur.get("summary"),
            "should_detect_corrections": False,
            "correction_to_save": None,
        }
        if cur.get("participants") is not None:
            body["participants"] = cur.get("participants")
        body.update(changes)

        r = await self._reader._http.patch(
            f"{constants.BACKEND_BASE}/memories/update", headers=headers, json=body
        )
        if not r.is_success:
            raise WriteError(f"Backend update failed ({r.status_code}): {r.text[:200]}")

        # Verify against the backend — a 200 proves nothing here.
        after = await self._backend_memory(memory_id, headers)
        actual = {k: (after or {}).get(k) for k in changes}
        verified = all(actual.get(k) == v for k, v in changes.items())

        # Mirror into Firestore so the two stores agree (the desktop app dual-writes for
        # exactly this reason — a drifted Firestore confuses every downstream reader).
        mirror_ok = None
        try:
            fs_fields: dict[str, Any] = {}
            for k, v in changes.items():
                if isinstance(v, str):
                    fs_fields[k] = {"stringValue": v}
                elif isinstance(v, list):
                    fs_fields[k] = str_array([str(i) for i in v])
            if fs_fields:
                await self.patch_fields(memory_id, fs_fields, list(fs_fields.keys()))
                mirror_ok = True
        except Exception:  # noqa: BLE001 - Firestore is the sync layer; backend already won
            mirror_ok = False

        return {
            "id": memory_id,
            "requested": changes,
            "actual": actual,
            "verified": verified,
            "firestore_mirrored": mirror_ok,
        }

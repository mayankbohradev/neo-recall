"""Async Firestore + neo-backend-v2 clients. READ-ONLY except token refresh elsewhere."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from neosapien_mcp import constants
from neosapien_mcp.auth import tokens
from neosapien_mcp.client import parse
from neosapien_mcp.models.memory import MemoryDetail, MemoryLight, Profile, TranscriptSegment


class FirestoreClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _auth_headers(self, *, force_refresh: bool = False) -> tuple[dict[str, str], str]:
        id_token, uid = await tokens.get_id_token(force=force_refresh)
        return {"Authorization": f"Bearer {id_token}"}, uid

    async def _get(self, url: str) -> httpx.Response:
        headers, _ = await self._auth_headers()
        resp = await self._http.get(url, headers=headers)
        if resp.status_code == 401:
            tokens.invalidate()
            headers, _ = await self._auth_headers(force_refresh=True)
            resp = await self._http.get(url, headers=headers)
        return resp

    async def list_all_memories(self) -> list[MemoryLight]:
        headers, uid = await self._auth_headers()
        base = f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}/memories"
        out: list[MemoryLight] = []
        page_token: str | None = None
        while True:
            url = f"{base}?pageSize={constants.PAGE_SIZE}"
            if page_token:
                url += f"&pageToken={quote(page_token, safe='')}"
            resp = await self._http.get(url, headers=headers)
            if resp.status_code == 401:
                tokens.invalidate()
                headers, uid = await self._auth_headers(force_refresh=True)
                base = f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}/memories"
                url = f"{base}?pageSize={constants.PAGE_SIZE}"
                if page_token:
                    url += f"&pageToken={quote(page_token, safe='')}"
                resp = await self._http.get(url, headers=headers)
            if not resp.is_success:
                raise RuntimeError(f"Firestore list error {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            for doc in body.get("documents") or []:
                mem = parse.parse_light(doc)
                if mem:
                    if not mem.user_id:
                        mem.user_id = uid
                    out.append(mem)
            page_token = body.get("nextPageToken")
            if not page_token:
                break
        out.sort(key=lambda m: m.created_at, reverse=True)
        return out

    async def get_document(self, memory_id: str) -> dict[str, Any]:
        _, uid = await self._auth_headers()
        url = (
            f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}"
            f"/memories/{quote(memory_id, safe='')}"
        )
        resp = await self._get(url)
        if resp.status_code == 404:
            raise KeyError(f"Memory not found: {memory_id}")
        if not resp.is_success:
            raise RuntimeError(f"Firestore get error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def get_memory(self, memory_id: str, *, include_mom: bool = True) -> MemoryDetail:
        doc = await self.get_document(memory_id)
        detail = parse.parse_detail(doc, include_mom=include_mom)
        if not detail:
            raise KeyError(f"Unparseable memory: {memory_id}")
        return detail

    async def get_transcript(self, memory_id: str) -> list[TranscriptSegment]:
        doc = await self.get_document(memory_id)
        return parse.parse_transcript(doc)

    async def get_profile(self) -> Profile:
        """
        Profile from Firestore users/{uid} (what the Neo app actually reads).

        Note: GET neo-backend-v2/.../users/{uid} returns 404 in production today —
        the KB's backend profile path is stale. Never surface DOB / push tokens /
        voiceprint / secondary PII from the Firestore user doc.
        """
        headers, uid = await self._auth_headers()
        url = f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}"
        resp = await self._http.get(url, headers=headers)
        if resp.status_code == 401:
            tokens.invalidate()
            headers, uid = await self._auth_headers(force_refresh=True)
            url = f"{constants.FIRESTORE_BASE}/users/{quote(uid, safe='')}"
            resp = await self._http.get(url, headers=headers)
        if resp.status_code == 404:
            # Minimal fallback from auth store / JWT — still no PII scrape
            from neosapien_mcp.auth import store as cred_store

            creds = cred_store.load()
            return Profile(
                display_name=(creds.email.split("@")[0] if creds and creds.email else ""),
                email=(creds.email if creds else ""),
                subscription_status=None,
            )
        if not resp.is_success:
            raise RuntimeError(f"Profile error {resp.status_code}: {resp.text[:200]}")
        fields = (resp.json() or {}).get("fields") or {}
        name = parse._str(fields, "name") or parse._str(fields, "displayName")
        email = parse._str(fields, "email")
        # No reliable subscription field on Firestore user doc; omit rather than invent
        return Profile(
            display_name=name,
            email=email,
            subscription_status=None,
        )

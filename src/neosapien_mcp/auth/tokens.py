"""Firebase Identity Platform: refresh token → hourly ID token."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from neosapien_mcp import constants
from neosapien_mcp.auth import store


class ReauthRequiredError(RuntimeError):
    """Refresh token missing/revoked — user must run auth bootstrap."""


@dataclass
class _TokenCache:
    id_token: str
    expires_at: float  # epoch seconds
    uid: str


_cache: _TokenCache | None = None


def extract_uid_from_jwt(token: str) -> str:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode())
    data = json.loads(decoded)
    uid = data.get("user_id") or data.get("sub")
    if not uid:
        raise ValueError("No user_id/sub in JWT")
    return str(uid)


def invalidate() -> None:
    global _cache
    _cache = None


def _api_key_and_refresh() -> tuple[str, str, store.StoredCredentials | None]:
    """Resolve credentials: env override → keyring/file store."""
    env_key = os.environ.get("NEOSAPIEN_FIREBASE_API_KEY", "").strip()
    env_refresh = os.environ.get("NEOSAPIEN_REFRESH_TOKEN", "").strip()
    if env_key and env_refresh:
        return env_key, env_refresh, None

    creds = store.load()
    if not creds:
        raise ReauthRequiredError(
            "No Neosapien credentials. Run `neo-recall-auth` or set "
            "NEOSAPIEN_FIREBASE_API_KEY + NEOSAPIEN_REFRESH_TOKEN."
        )
    return creds.firebase_api_key, creds.refresh_token, creds


async def refresh_id_token(client: httpx.AsyncClient | None = None) -> _TokenCache:
    global _cache
    api_key, refresh_token, creds = _api_key_and_refresh()
    url = f"{constants.SECURE_TOKEN_URL}?key={api_key}"
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        resp = await client.post(
            url,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 400:
            text = resp.text[:200]
            if any(x in text for x in ("TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN", "USER_DISABLED")):
                store.clear()
                invalidate()
                raise ReauthRequiredError(
                    "Refresh token revoked/expired. Re-run `neo-recall-auth`."
                )
            raise RuntimeError(f"Token refresh failed: {resp.status_code} {text}")
        resp.raise_for_status()
        body = resp.json()
        id_token = body["id_token"]
        new_refresh = body.get("refresh_token") or refresh_token
        expires_in = int(body.get("expires_in", 3600))
        uid = body.get("user_id") or extract_uid_from_jwt(id_token)
        if creds is not None and new_refresh != creds.refresh_token:
            creds.refresh_token = new_refresh
            creds.uid = uid
            store.save(creds)
        _cache = _TokenCache(
            id_token=id_token,
            expires_at=time.time() + expires_in,
            uid=uid,
        )
        return _cache
    finally:
        if owns_client:
            await client.aclose()


async def get_id_token(*, force: bool = False) -> tuple[str, str]:
    """Return (id_token, uid), refreshing when near expiry."""
    global _cache
    margin = constants.TOKEN_SAFETY_MARGIN_SECONDS
    if not force and _cache and time.time() < _cache.expires_at - margin:
        return _cache.id_token, _cache.uid
    cached = await refresh_id_token()
    return cached.id_token, cached.uid


def try_desktop_id_token() -> tuple[str, str] | None:
    """Optional MVP bootstrap: read Neo desktop config.json (ID token only)."""
    path = Path(constants.NEO_DESKTOP_CONFIG).expanduser()
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    token = data.get("authToken")
    if not token or not str(token).startswith("eyJ"):
        return None
    uid = extract_uid_from_jwt(token)
    return token, uid

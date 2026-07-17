"""Write-path tests: confirmation gate, guards, and participants field resolution.

All offline — these must never touch the network or mutate real memories.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neosapien_mcp.client.writes import WriteError, resolve_participants_field, str_array
from neosapien_mcp.models.memory import MemoryLight
from neosapien_mcp.tools import handlers


def _fields(**arrays: list[str]) -> dict:
    return {
        k: {"arrayValue": {"values": [{"stringValue": s} for s in v]}} for k, v in arrays.items()
    }


# --- participants field resolution ------------------------------------------
# parse.py reads `participants or entities`. Writing the wrong key returns 200 and
# silently changes nothing, so resolution must mirror the reader's precedence.


def test_resolves_to_participants_when_populated():
    assert (
        resolve_participants_field(_fields(participants=["Ada"], entities=["Grace"]))
        == "participants"
    )


def test_falls_back_to_entities_when_participants_empty():
    assert resolve_participants_field(_fields(participants=[], entities=["Ada"])) == "entities"


def test_defaults_to_participants_when_both_absent():
    assert resolve_participants_field({}) == "participants"


def test_prefers_existing_entities_key_when_both_empty():
    assert resolve_participants_field(_fields(entities=[])) == "entities"


def test_str_array_encodes_firestore_shape():
    assert str_array(["A", "B"]) == {
        "arrayValue": {"values": [{"stringValue": "A"}, {"stringValue": "B"}]}
    }


# --- the updateMask guard ----------------------------------------------------


@pytest.mark.asyncio
async def test_patch_without_mask_refuses():
    """A PATCH with no updateMask REPLACES the whole doc — must never be issued."""
    from neosapien_mcp.client.writes import WriteClient

    client = WriteClient(reader=AsyncMock())
    with pytest.raises(WriteError, match="updateMask"):
        await client.patch_fields("m1", {"archived": {"booleanValue": True}}, [])


# --- confirmation gate (DELETE is permanent — these are the critical tests) ---

_FAKE = [MemoryLight(id="m1", title="Standup", archived=False, created_at="2026-07-01T10:00:00Z")]


@pytest.mark.asyncio
async def test_delete_preview_issues_no_write():
    """The preview path must never construct a write client, let alone delete."""
    with patch("neosapien_mcp.service.ensure_index", AsyncMock(return_value=_FAKE)):
        with patch("neosapien_mcp.client.writes.WriteClient") as wc:
            r = await handlers.delete_memories(["m1"])
    assert r["status"] == "confirmation_required"
    assert not wc.called, "preview must not construct a write client"


@pytest.mark.asyncio
async def test_delete_preview_warns_irreversible():
    with patch("neosapien_mcp.service.ensure_index", AsyncMock(return_value=_FAKE)):
        r = await handlers.delete_memories(["m1"])
    assert "IRREVERSIBLE" in r["detail"]
    assert r["preview"][0]["title"] == "Standup"


@pytest.mark.asyncio
async def test_delete_batch_cap_enforced():
    r = await handlers.delete_memories([f"x{i}" for i in range(handlers.MAX_WRITE_BATCH + 1)])
    assert r["status"] == "error" and "MAX_WRITE_BATCH" in r["error"]


@pytest.mark.asyncio
async def test_delete_empty_ids_rejected():
    assert (await handlers.delete_memories([]))["status"] == "error"


@pytest.mark.asyncio
async def test_delete_still_present_reports_unverified():
    """If a row survives in the backend, it will reappear on the phone. Never say success."""
    fake = AsyncMock()
    fake.delete_memories = AsyncMock(
        return_value={
            "requested": 1, "backend_status": 200, "firestore_deleted": 1,
            "firestore_errors": [], "still_present_in_backend": ["m1"], "verified": False,
        }
    )
    with patch("neosapien_mcp.service.ensure_index", AsyncMock(return_value=_FAKE)):
        with patch("neosapien_mcp.service.invalidate_index"):
            with patch("neosapien_mcp.client.writes.WriteClient", return_value=fake):
                r = await handlers.delete_memories(["m1"], confirm=True)
    assert r["status"] == "unverified"
    assert "NOT fully deleted" in r["warning"]
    assert "m1" in r["warning"]


@pytest.mark.asyncio
async def test_confirmed_delete_invalidates_cache():
    fake = AsyncMock()
    fake.delete_memories = AsyncMock(
        return_value={
            "requested": 1, "backend_status": 200, "firestore_deleted": 1,
            "firestore_errors": [], "still_present_in_backend": [], "verified": True,
        }
    )
    with patch("neosapien_mcp.service.ensure_index", AsyncMock(return_value=_FAKE)):
        with patch("neosapien_mcp.service.invalidate_index") as inv:
            with patch("neosapien_mcp.client.writes.WriteClient", return_value=fake):
                r = await handlers.delete_memories(["m1"], confirm=True)
    assert r["status"] == "done"
    assert inv.called, "a confirmed delete must invalidate the index cache"


# --- input guards -----------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_with_is_exclusive():
    r = await handlers.update_participants("m1", add=["A"], replace_with=["B"])
    assert r["status"] == "error" and "exclusive" in r["error"]


@pytest.mark.asyncio
async def test_participants_requires_an_operation():
    assert (await handlers.update_participants("m1"))["status"] == "error"


@pytest.mark.asyncio
async def test_update_memory_requires_a_field():
    assert (await handlers.update_memory("m1"))["status"] == "error"


# --- stale-cache self-correction ---------------------------------------------
# A memory recorded minutes ago is absent from a cache that still reports "fresh".
# A zero-hit search then looks identical to "it does not exist" — the worst failure
# mode for a memory app. search_memories must retry live before reporting nothing.


@pytest.mark.asyncio
async def test_zero_hit_search_retries_against_live_data():
    fresh_hit = MemoryLight(
        id="new", title="Dashboard Automation", created_at="2026-07-17T08:52:14Z"
    )
    calls: list[bool] = []

    async def fake_index(*, force_refresh: bool = False):
        calls.append(force_refresh)
        return [] if not force_refresh else [fresh_hit]

    with patch("neosapien_mcp.service.ensure_index", side_effect=fake_index):
        r = await handlers.search_memories(query="Dashboard Automation")

    assert calls == [False, True], "must retry once with force_refresh after a cached miss"
    assert r["total_found"] == 1, "the live retry should surface the recent memory"
    assert r["items"][0]["id"] == "new"
    assert "re-checked" in r.get("note", ""), "must tell the model it went live"


@pytest.mark.asyncio
async def test_search_with_hits_does_not_refetch():
    hit = MemoryLight(id="a", title="Dashboard Automation", created_at="2026-03-21T10:29:45Z")
    calls: list[bool] = []

    async def fake_index(*, force_refresh: bool = False):
        calls.append(force_refresh)
        return [hit]

    with patch("neosapien_mcp.service.ensure_index", side_effect=fake_index):
        r = await handlers.search_memories(query="Dashboard Automation")

    assert calls == [False], "a cached hit must not trigger a second live fetch"
    assert "note" not in r


# --- user-facing language ----------------------------------------------------
# Internal plumbing (Firestore, "the backend", sync layers) must never surface in what
# the model says to the user. They have a NeoSapien profile, not a database topology.
# The tool docstring and preview text are what the model echoes, so they set the tone.


@pytest.mark.asyncio
async def test_delete_preview_speaks_in_profile_terms_not_store_names():
    with patch("neosapien_mcp.service.ensure_index", AsyncMock(return_value=_FAKE)):
        r = await handlers.delete_memories(["m1"])
    detail = r["detail"]
    assert "NeoSapien profile" in detail
    assert "Firestore" not in detail
    assert "both stores" not in detail


@pytest.mark.asyncio
async def test_failed_delete_warning_avoids_store_names():
    fake = AsyncMock()
    fake.delete_memories = AsyncMock(
        return_value={
            "requested": 1, "backend_status": 200, "firestore_deleted": 0,
            "firestore_errors": [], "still_present_in_backend": ["m1"], "verified": False,
        }
    )
    with patch("neosapien_mcp.service.ensure_index", AsyncMock(return_value=_FAKE)):
        with patch("neosapien_mcp.service.invalidate_index"):
            with patch("neosapien_mcp.client.writes.WriteClient", return_value=fake):
                r = await handlers.delete_memories(["m1"], confirm=True)
    assert "NeoSapien profile" in r["warning"]
    assert "Firestore" not in r["warning"]


def test_delete_tool_docstring_tells_model_to_say_profile():
    """The docstring is the model's script — it must forbid store names explicitly."""
    from neosapien_mcp import server

    doc = server.delete_memories.__doc__ or ""
    assert "NeoSapien profile" in doc
    assert "never name the underlying databases" in doc
    # the instruction must not itself spell out the store names — a model reading a
    # banned-word list is more likely to echo them back to the user.
    assert "Firestore" not in doc

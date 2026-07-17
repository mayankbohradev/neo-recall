"""MCP tool handlers — read-only."""

from __future__ import annotations

import csv
import io
from typing import Any

from neosapien_mcp.enrich import briefs, quality
from neosapien_mcp import service
from neosapien_mcp.client import parse  # used by write handlers (participants field resolution)


async def search_memories(
    query: str | None = None,
    owner_name: str | None = None,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    topics: list[str] | None = None,
    domains: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Primary search — light objects only (no transcript/MOM)."""
    ent = list(entities or [])
    if owner_name:
        ent.append(owner_name)

    def _filter(mems: list[Any]) -> list[Any]:
        return service.apply_filters(
            mems,
            query=query,
            tags=tags,
            entities=ent or None,
            topics=topics,
            domains=domains,
            start_date=start_date,
            end_date=end_date,
        )

    memories = await service.ensure_index(force_refresh=force_refresh)
    filtered = _filter(memories)

    # Stale-cache self-correction: the index is cached for 10 minutes, so a memory
    # recorded minutes ago is absent while the cache still reports "fresh". A zero-hit
    # search is indistinguishable from "it doesn't exist" — which is the worst failure
    # for a memory app. Retry once against live data before reporting nothing.
    refreshed = False
    if not filtered and not force_refresh:
        memories = await service.ensure_index(force_refresh=True)
        filtered = _filter(memories)
        refreshed = True

    # Preserve BM25 relevance order when a text query is present
    out = service.paginate(
        filtered,
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        preserve_order=bool((query or "").strip()),
    )
    if refreshed:
        out["note"] = (
            "No cached hits — automatically re-checked the live NeoSapien profile before answering."
        )
    return out


async def list_memories(
    archived: bool | None = None,
    limit: int = 20,
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    force_refresh: bool = False,
) -> dict[str, Any]:
    memories = await service.ensure_index(force_refresh=force_refresh)
    filtered = service.apply_filters(memories, archived=archived)
    return service.paginate(
        filtered, page=page, limit=limit, sort_by=sort_by, sort_order=sort_order
    )


async def list_filtered_memories(
    memory_ids: list[str],
    limit: int = 20,
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    force_refresh: bool = False,
) -> dict[str, Any]:
    memories = await service.ensure_index(force_refresh=force_refresh)
    id_set = set(memory_ids)
    filtered = [m for m in memories if m.id in id_set]
    return service.paginate(
        filtered, page=page, limit=limit, sort_by=sort_by, sort_order=sort_order
    )


async def get_memory(memory_id: str, include_mom: bool = True) -> dict[str, Any]:
    client = service.get_client()
    detail = await client.get_memory(memory_id, include_mom=include_mom)
    return detail.model_dump()


async def get_transcript(memory_id: str) -> dict[str, Any]:
    client = service.get_client()
    segs = await client.get_transcript(memory_id)
    return {"id": memory_id, "transcript": [s.model_dump() for s in segs]}


async def search_people(name_query: str | None = None, limit: int = 20) -> dict[str, Any]:
    memories = await service.ensure_index()
    return service.collect_people(memories, name_query, limit)


async def get_latest_by_person(
    owner_name: str,
    limit: int = 10,
    sort_order: str = "desc",
) -> dict[str, Any]:
    memories = await service.ensure_index()
    q = owner_name.strip().lower()
    matched = [
        m
        for m in memories
        if any(q in p.lower() for p in m.participants + m.mentioned_entities)
        or q in m.searchable_text()
    ]
    page = service.paginate(
        matched, page=1, limit=min(limit, 50), sort_by="created_at", sort_order=sort_order
    )
    page["person_query"] = owner_name
    page["total_memories"] = len(matched)
    return page


async def memory_stats(
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    topics: list[str] | None = None,
    domains: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    max_metadata_items: int = 50,
) -> dict[str, Any]:
    memories = await service.ensure_index()
    filtered = service.apply_filters(
        memories,
        tags=tags,
        entities=entities,
        topics=topics,
        domains=domains,
        start_date=start_date,
        end_date=end_date,
    )
    return service.metadata_aggregate(filtered, max_items=max_metadata_items)


async def get_profile() -> dict[str, Any]:
    client = service.get_client()
    profile = await client.get_profile()
    return profile.model_dump()


async def export_memories(
    memory_ids: list[str],
    format: str = "json",
) -> dict[str, Any] | str:
    memories = await service.ensure_index()
    id_set = set(memory_ids)
    chosen = [m for m in memories if m.id in id_set]
    # Heavy: pull MOM for export when fetching detail one-by-one would be slow —
    # export light fields by default; caller can get_memory for MOM.
    if format.lower() == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "id",
                "title",
                "summary",
                "created_at",
                "duration_sec",
                "topics",
                "participants",
                "domains",
            ],
        )
        writer.writeheader()
        for m in chosen:
            writer.writerow(
                {
                    "id": m.id,
                    "title": m.title,
                    "summary": m.summary,
                    "created_at": m.created_at,
                    "duration_sec": m.duration_sec,
                    "topics": "|".join(m.topics),
                    "participants": "|".join(m.participants),
                    "domains": "|".join(m.domains),
                }
            )
        return buf.getvalue()
    return {
        "format": "json",
        "memories": [m.model_dump() for m in chosen],
        "total_exported": len(chosen),
    }


async def weekly_brief(
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    memories = await service.ensure_index()
    if not start_date or not end_date:
        start_date, end_date = briefs.default_week_bounds()
    start = service.normalize_start_date(start_date) or start_date
    end = service.normalize_end_date(end_date) or end_date
    window = briefs.filter_window(memories, start=start, end=end)
    return briefs.build_weekly_brief(window, start=start or "", end=end or "")


async def triage_memories(
    start_date: str | None = None,
    end_date: str | None = None,
    use_llm: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    memories = await service.ensure_index()
    filtered = service.apply_filters(memories, start_date=start_date, end_date=end_date)
    filtered = filtered[: max(1, min(limit, 200))]
    results = quality.triage_batch(filtered, use_llm=use_llm)
    return {
        "count": len(results),
        "items": [r.model_dump() for r in results],
        "use_llm": use_llm,
    }


async def rank_by_quality(
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    memories = await service.ensure_index()
    filtered = service.apply_filters(memories, start_date=start_date, end_date=end_date)
    ranked = quality.rank_by_quality(filtered, limit=limit)
    return {"items": [r.model_dump() for r in ranked], "returned": len(ranked)}


async def people_digest(name: str, limit: int = 20) -> str:
    memories = await service.ensure_index()
    return briefs.build_people_digest(memories, name, limit=limit)


async def related_memories(memory_id: str, limit: int = 10) -> dict[str, Any]:
    from neosapien_mcp.enrich import related

    memories = await service.ensure_index()
    items = related.find_related(memories, memory_id, limit=limit)
    return {
        "memory_id": memory_id,
        "items": items,
        "returned": len(items),
        "note": "Scored by shared participants (3) > entities (2) > topics (1) > domains (0.5)",
    }


async def whats_new(
    since: str | None = None,
    limit: int = 30,
    mark_seen: bool = True,
) -> dict[str, Any]:
    """Memories created after `since` (or last whats_new check). Updates last_seen marker."""
    from datetime import datetime, timezone

    cache = service.get_cache()
    memories = await service.ensure_index()
    since_ts = since or cache.get_meta("last_seen")
    if not since_ts:
        # Default: last 24h
        since_ts = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
        if since_ts.endswith("+00:00"):
            since_ts = since_ts.replace("+00:00", "Z")
        else:
            since_ts = since_ts[:19] + "Z"

    start = service.normalize_start_date(since_ts) or since_ts
    filtered = [m for m in memories if m.created_at and m.created_at >= start]
    filtered.sort(key=lambda m: m.created_at, reverse=True)
    chunk = filtered[: max(1, min(limit, 100))]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if mark_seen:
        cache.set_meta("last_seen", now)

    return {
        "since": start,
        "checked_at": now,
        "total_new": len(filtered),
        "returned": len(chunk),
        "items": [m.model_dump() for m in chunk],
        "mark_seen": mark_seen,
    }


async def topic_timeline(
    topic: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    memories = await service.ensure_index()
    start = service.normalize_start_date(start_date)
    end = service.normalize_end_date(end_date)
    return briefs.build_topic_timeline(memories, topic, start=start, end=end)


async def daily_brief(date: str | None = None) -> str:
    """Convenience: weekly_brief for a single calendar day (default: today UTC)."""
    from datetime import datetime, timezone

    day = date[:10] if date else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await weekly_brief(start_date=day, end_date=day)


async def compare_periods(
    period_a_start: str | None = None,
    period_a_end: str | None = None,
    period_b_start: str | None = None,
    period_b_end: str | None = None,
) -> dict[str, Any]:
    from neosapien_mcp.enrich import analytics

    memories = await service.ensure_index()
    if not all([period_a_start, period_a_end, period_b_start, period_b_end]):
        a_s, a_e, b_s, b_e = analytics.default_week_vs_prior()
        period_a_start = period_a_start or a_s
        period_a_end = period_a_end or a_e
        period_b_start = period_b_start or b_s
        period_b_end = period_b_end or b_e
    return analytics.compare_periods(
        memories,
        period_a_start=service.normalize_start_date(period_a_start) or period_a_start,  # type: ignore[arg-type]
        period_a_end=service.normalize_end_date(period_a_end) or period_a_end,  # type: ignore[arg-type]
        period_b_start=service.normalize_start_date(period_b_start) or period_b_start,  # type: ignore[arg-type]
        period_b_end=service.normalize_end_date(period_b_end) or period_b_end,  # type: ignore[arg-type]
    )


async def action_items(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    from neosapien_mcp.enrich import extract

    memories = await service.ensure_index()
    filtered = service.apply_filters(memories, start_date=start_date, end_date=end_date)
    return extract.action_items(filtered, limit=limit)


async def follow_ups_due(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    from neosapien_mcp.enrich import extract

    memories = await service.ensure_index()
    filtered = service.apply_filters(memories, start_date=start_date, end_date=end_date)
    return extract.follow_ups_due(filtered, limit=limit)


async def decision_log(
    topic: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    from neosapien_mcp.enrich import extract

    memories = await service.ensure_index()
    filtered = service.apply_filters(memories, start_date=start_date, end_date=end_date)
    return extract.decision_log(filtered, topic=topic, limit=limit)


async def memory_graph(
    memory_id: str,
    depth: int = 1,
    limit: int = 15,
) -> dict[str, Any]:
    from neosapien_mcp.enrich import graph

    memories = await service.ensure_index()
    return graph.memory_graph(memories, seed_id=memory_id, depth=max(1, min(depth, 2)), limit=limit)


async def duplicate_candidates(
    start_date: str | None = None,
    end_date: str | None = None,
    threshold: float = 0.55,
    limit: int = 25,
) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    from neosapien_mcp.enrich import duplicates

    memories = await service.ensure_index()
    if not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    return duplicates.duplicate_candidates(
        memories,
        threshold=threshold,
        limit=limit,
        start_date=service.normalize_start_date(start_date),
        end_date=service.normalize_end_date(end_date),
    )


async def habit_signals(
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    from neosapien_mcp.enrich import analytics

    memories = await service.ensure_index()
    return analytics.habit_signals(
        memories,
        start=service.normalize_start_date(start_date),
        end=service.normalize_end_date(end_date),
        days=days,
    )


async def export_brief_pack(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Artifact-ready bundle: weekly brief + facets + top people."""
    memories = await service.ensure_index()
    if not start_date or not end_date:
        start_date, end_date = briefs.default_week_bounds()
    start = service.normalize_start_date(start_date) or start_date
    end = service.normalize_end_date(end_date) or end_date
    window = briefs.filter_window(memories, start=start, end=end)
    brief = briefs.build_weekly_brief(window, start=start or "", end=end or "")
    stats = service.metadata_aggregate(window, max_items=12)
    people = service.collect_people(window, None, limit=12)
    from neosapien_mcp.enrich import extract

    actions = extract.action_items(window, limit=15)
    return {
        "start": start,
        "end": end,
        "brief_markdown": brief,
        "stats": {
            "total_count": stats["total_count"],
            "top_topics": stats["topics"],
            "top_domains": stats["domains"],
            "top_entities": stats["entities"],
        },
        "people": people["matches"],
        "action_items": actions["items"],
        "memory_ids": [m.id for m in window[:40]],
        "note": "Ready for ChatGPT theme card / Claude artifact — ask the user first",
    }


async def set_presentation_pref(mode: str = "ask") -> dict[str, Any]:
    """Persist visual preference: ask | always | never."""
    allowed = {"ask", "always", "never"}
    mode = (mode or "ask").strip().lower()
    if mode not in allowed:
        return {"ok": False, "error": f"mode must be one of {sorted(allowed)}"}
    cache = service.get_cache()
    cache.set_meta("presentation_pref", mode)
    return {"ok": True, "presentation_pref": mode}


async def get_presentation_pref() -> dict[str, Any]:
    cache = service.get_cache()
    return {"presentation_pref": cache.get_meta("presentation_pref") or "ask"}


async def quote_search(
    query: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    max_scan: int = 60,
) -> dict[str, Any]:
    """
    Search transcript text for an exact-ish quote/phrase.

    Heavy: fetches transcripts for up to max_scan candidate memories
    (date-filtered + BM25 prefilter). Prefer date windows.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    if not (query or "").strip():
        return {"error": "query required", "items": []}

    memories = await service.ensure_index()
    if not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    filtered = service.apply_filters(
        memories, query=query, start_date=start_date, end_date=end_date
    )
    # Also include non-text-prefiltered window slice for recall
    window = service.apply_filters(memories, start_date=start_date, end_date=end_date, ranked=False)
    seen: set[str] = set()
    candidates: list = []
    for m in list(filtered) + list(window):
        if m.id in seen:
            continue
        seen.add(m.id)
        candidates.append(m)
        if len(candidates) >= max(1, min(max_scan, 120)):
            break

    client = service.get_client()
    sem = asyncio.Semaphore(8)
    q = query.strip().lower()
    hits: list[dict[str, Any]] = []

    async def scan(m) -> None:
        async with sem:
            try:
                segs = await client.get_transcript(m.id)
            except Exception:
                return
            for s in segs:
                text = (s.text or "").strip()
                if q in text.lower():
                    hits.append(
                        {
                            "memory_id": m.id,
                            "title": m.title,
                            "created_at": m.created_at,
                            "speaker": s.speaker,
                            "start": s.start,
                            "end": s.end,
                            "text": text[:400],
                        }
                    )

    await asyncio.gather(*(scan(m) for m in candidates))
    hits.sort(key=lambda h: h.get("created_at") or "", reverse=True)
    return {
        "query": query,
        "scanned": len(candidates),
        "hit_count": len(hits),
        "returned": min(len(hits), limit),
        "items": hits[:limit],
        "note": "Transcript scan is heavy — narrow with start_date/end_date when possible",
    }


# ---------------------------------------------------------------------------
# WRITE handlers
#
# Safety model (per user decision):
#   * No hard delete is exposed. `archived` is a first-class schema field the Neo
#     app itself sets, so archiving is reversible and is our delete primitive.
#   * Every write is two-phase. An MCP tool cannot prompt mid-call, so the FIRST
#     call always returns a preview of exactly what would change and performs no
#     write. The caller must re-invoke with confirm=True to execute.
#   * Writes go to Firestore; neo-backend-v2 is the primary store and may sync
#     over us. Each result carries `verified` from a post-write re-read so a
#     silent revert surfaces as verified=False rather than a false success.
# ---------------------------------------------------------------------------

MAX_WRITE_BATCH = 50


def _confirm_stub(action: str, preview: list[dict[str, Any]], detail: str) -> dict[str, Any]:
    return {
        "status": "confirmation_required",
        "action": action,
        "affected_count": len(preview),
        "preview": preview,
        "detail": detail,
        "next_step": f"Re-run {action} with confirm=true to apply. Nothing has been changed.",
    }


async def _light_by_ids(memory_ids: list[str]) -> dict[str, Any]:
    memories = await service.ensure_index()
    return {m.id: m for m in memories if m.id in set(memory_ids)}


async def delete_memories(memory_ids: list[str], confirm: bool = False) -> dict[str, Any]:
    """
    PERMANENT delete from BOTH stores. Preview first; confirm=True to execute.

    There is no archive endpoint on neo-backend-v2 (verified: the official app exposes
    none, PATCH /memories/update silently drops `archived`, POST /memories/archive 404s).
    Deleting from both stores is the only way to make a memory disappear from the phone,
    which reads PostgreSQL. This is IRREVERSIBLE — there is no undo tool, by definition.
    """
    from neosapien_mcp.client.writes import WriteClient

    if not memory_ids:
        return {"status": "error", "error": "memory_ids is empty"}
    if len(memory_ids) > MAX_WRITE_BATCH:
        return {
            "status": "error",
            "error": f"{len(memory_ids)} ids exceeds MAX_WRITE_BATCH={MAX_WRITE_BATCH}. "
            "Split into smaller batches.",
        }

    found = await _light_by_ids(memory_ids)
    missing = [i for i in memory_ids if i not in found]
    preview = [
        {
            "id": i,
            "title": found[i].title,
            "created_at": found[i].created_at,
            "duration_sec": found[i].duration_sec,
            "participants": found[i].participants,
            "summary": (found[i].summary or "")[:160],
        }
        for i in memory_ids
        if i in found
    ]
    if not confirm:
        out = _confirm_stub(
            "delete_memories",
            preview,
            "PERMANENT AND IRREVERSIBLE. This removes the memories above from the user's "
            "NeoSapien profile, including the phone app. There is no undo and no recycle "
            "bin — the transcripts are destroyed too. Show this list to the user verbatim "
            "and get an explicit yes before re-running with confirm=true. Describe it to them "
            "as deleting from their NeoSapien profile; do not name internal infrastructure.",
        )
        if missing:
            out["not_found"] = missing
        return out

    client = WriteClient()
    try:
        result = await client.delete_memories([i for i in memory_ids if i in found])
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)[:300]}
    finally:
        await client.aclose()

    service.invalidate_index()
    result["status"] = "done" if result["verified"] else "unverified"
    result["deleted_titles"] = [p["title"] for p in preview]
    if missing:
        result["not_found"] = missing
    if not result["verified"]:
        result["warning"] = (
            "These memories were NOT fully deleted and will still appear in the user's "
            "NeoSapien profile and phone app: "
            + ", ".join(result["still_present_in_backend"])
            + ". Tell the user the deletion did not complete. Do not report success."
        )
    return result


async def update_memory(
    memory_id: str,
    title: str | None = None,
    summary: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Edit a memory's title and/or summary. Preview first; confirm=True to apply."""
    from neosapien_mcp.client.writes import WriteClient

    updates = {k: v for k, v in (("title", title), ("summary", summary)) if v is not None}
    if not updates:
        return {"status": "error", "error": "Provide at least one of title or summary."}

    found = await _light_by_ids([memory_id])
    if memory_id not in found:
        return {"status": "error", "error": f"Memory not found: {memory_id}"}
    m = found[memory_id]

    preview = [
        {
            "id": memory_id,
            "field": k,
            "current": getattr(m, k, ""),
            "new": v,
            "no_op": getattr(m, k, "") == v,
        }
        for k, v in updates.items()
    ]
    if not confirm:
        return _confirm_stub(
            "update_memory",
            preview,
            "This OVERWRITES the current value — the original is not recoverable "
            "through this server. Copy anything you want to keep.",
        )

    client = WriteClient()
    try:
        r = await client.update_backend_memory(memory_id, dict(updates))
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "id": memory_id, "error": str(e)[:200]}
    finally:
        await client.aclose()

    service.invalidate_index()
    r["status"] = "ok" if r["verified"] else "unverified"
    if not r["verified"]:
        r["warning"] = (
            "Backend returned success but the value did not change on re-read — this "
            "endpoint silently ignores fields outside its schema. Do not report success."
        )
    return r


async def update_participants(
    memory_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace_with: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Add / remove / replace participants. Preview first; confirm=True to apply."""
    from neosapien_mcp.client.writes import WriteClient, resolve_participants_field

    if replace_with is not None and (add or remove):
        return {
            "status": "error",
            "error": "replace_with is exclusive — do not combine it with add/remove.",
        }
    if replace_with is None and not add and not remove:
        return {"status": "error", "error": "Provide add, remove, or replace_with."}

    client = WriteClient()
    try:
        before_fields = await client.read_fields(memory_id)
    except KeyError:
        await client.aclose()
        return {"status": "error", "error": f"Memory not found: {memory_id}"}
    except Exception as e:  # noqa: BLE001
        await client.aclose()
        return {"status": "error", "error": str(e)[:200]}

    field = resolve_participants_field(before_fields)
    current = parse._arr(before_fields, field)

    if replace_with is not None:
        target = list(dict.fromkeys(replace_with))
    else:
        target = list(current)
        for name in remove or []:
            target = [t for t in target if t != name]
        for name in add or []:
            if name not in target:
                target.append(name)

    preview = [
        {
            "id": memory_id,
            "field_to_write": field,
            "current": current,
            "new": target,
            "added": [t for t in target if t not in current],
            "removed": [c for c in current if c not in target],
            "no_op": target == current,
        }
    ]
    if not confirm:
        await client.aclose()
        return _confirm_stub(
            "update_participants",
            preview,
            f"Participants on this memory are backed by the '{field}' field. "
            "This replaces the whole array.",
        )

    try:
        r = await client.update_backend_memory(memory_id, {field: target})
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "id": memory_id, "error": str(e)[:200]}
    finally:
        await client.aclose()

    service.invalidate_index()
    r["status"] = "ok" if r["verified"] else "unverified"
    if not r["verified"]:
        r["warning"] = (
            "Backend returned success but the value did not change on re-read — this "
            "endpoint silently ignores fields outside its schema. Do not report success."
        )
    return r

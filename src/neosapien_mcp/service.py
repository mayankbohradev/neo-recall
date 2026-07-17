"""Shared memory index: cache-backed list + filters."""

from __future__ import annotations

from collections import Counter
from typing import Any

from neosapien_mcp.cache.sqlite import MemoryCache
from neosapien_mcp.client.firestore import FirestoreClient
from neosapien_mcp.models.memory import MemoryLight

_client: FirestoreClient | None = None
_cache: MemoryCache | None = None


def get_client() -> FirestoreClient:
    global _client
    if _client is None:
        _client = FirestoreClient()
    return _client


def get_cache() -> MemoryCache:
    global _cache
    if _cache is None:
        _cache = MemoryCache()
    return _cache


async def ensure_index(*, force_refresh: bool = False) -> list[MemoryLight]:
    cache = get_cache()
    if not force_refresh and cache.is_fresh() and cache.count() > 0:
        return cache.list_all()
    client = get_client()
    memories = await client.list_all_memories()
    cache.replace_all(memories)
    return memories


def invalidate_index() -> None:
    """
    Force the next ensure_index() to re-fetch from Firestore.

    Writes must call this. The cache has a 10-minute TTL, so without it an
    archive/edit would not show up in list/search until the TTL lapsed — which
    reads to the user as "the write silently failed".
    """
    cache = get_cache()
    cache.set_meta("synced_at", "0")


def normalize_end_date(end_date: str | None) -> str | None:
    """Include the full calendar day when user passes YYYY-MM-DD."""
    if not end_date:
        return None
    if len(end_date) == 10 and "T" not in end_date:
        return f"{end_date}T23:59:59Z"
    return end_date


def normalize_start_date(start_date: str | None) -> str | None:
    if not start_date:
        return None
    if len(start_date) == 10 and "T" not in start_date:
        return f"{start_date}T00:00:00Z"
    return start_date


def apply_filters(
    memories: list[MemoryLight],
    *,
    query: str | None = None,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    topics: list[str] | None = None,
    domains: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    archived: bool | None = None,
    ranked: bool = True,
) -> list[MemoryLight]:
    start = normalize_start_date(start_date)
    end = normalize_end_date(end_date)
    q = (query or "").strip()
    tag_set = {t.lower() for t in (tags or [])}
    ent_set = {e.lower() for e in (entities or [])}
    topic_set = {t.lower() for t in (topics or [])}
    domain_set = {d.lower() for d in (domains or [])}

    out: list[MemoryLight] = []
    for m in memories:
        if archived is not None and m.archived != archived:
            continue
        if start and m.created_at and m.created_at < start:
            continue
        if end and m.created_at and m.created_at > end:
            continue
        if tag_set and not tag_set.intersection({t.lower() for t in m.tags}):
            continue
        if topic_set and not topic_set.intersection({t.lower() for t in m.topics}):
            continue
        if domain_set and not domain_set.intersection({d.lower() for d in m.domains}):
            continue
        if ent_set:
            people = {p.lower() for p in m.participants + m.mentioned_entities + m.present_entities}
            if not ent_set.intersection(people):
                continue
        out.append(m)

    if q:
        from neosapien_mcp.enrich.search_rank import rank_memories

        if ranked:
            scored = rank_memories(out, q)
            return [m for _, m in scored]
        ql = q.lower()
        return [m for m in out if ql in m.searchable_text()]
    return out


def paginate(
    items: list[MemoryLight],
    *,
    page: int = 1,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    preserve_order: bool = False,
) -> dict[str, Any]:
    page = max(1, page)
    limit = max(1, min(limit, 100))
    if preserve_order:
        ordered = list(items)
    else:
        reverse = sort_order.lower() != "asc"
        key = sort_by if sort_by in ("created_at", "updated_at", "title") else "created_at"

        def sort_key(m: MemoryLight) -> str:
            return getattr(m, key, "") or ""

        ordered = sorted(items, key=sort_key, reverse=reverse)
    total = len(ordered)
    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    start = (page - 1) * limit
    chunk = ordered[start : start + limit]
    return {
        "items": [m.model_dump() for m in chunk],
        "total_found": total,
        "returned": len(chunk),
        "page": page,
        "total_pages": total_pages,
        "has_more": page < total_pages,
    }


def metadata_aggregate(
    memories: list[MemoryLight],
    *,
    max_items: int = 50,
) -> dict[str, Any]:
    tags: Counter[str] = Counter()
    topics: Counter[str] = Counter()
    entities: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    emotions: Counter[str] = Counter()
    for m in memories:
        tags.update(m.tags)
        topics.update(m.topics)
        entities.update(m.participants + m.mentioned_entities)
        domains.update(m.domains)
        emotions.update(m.emotions)
    created = [m.created_at for m in memories if m.created_at]
    return {
        "total_count": len(memories),
        "tags": [t for t, _ in tags.most_common(max_items)],
        "topics": [t for t, _ in topics.most_common(max_items)],
        "entities": [e for e, _ in entities.most_common(max_items)],
        "domains": [d for d, _ in domains.most_common(max_items)],
        "emotions": [e for e, _ in emotions.most_common(max_items)],
        "min_created_at": min(created) if created else None,
        "max_created_at": max(created) if created else None,
        "memory_ids": [m.id for m in memories[: max(max_items * 5, 50)]],
        "note": f"Facet lists limited to {max_items} items",
    }


def collect_people(
    memories: list[MemoryLight], name_query: str | None, limit: int
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for m in memories:
        counts.update(m.participants)
        counts.update(m.mentioned_entities)
    q = (name_query or "").strip().lower()
    names = [n for n, _ in counts.most_common()]
    if q:
        names = [n for n in names if q in n.lower()]
    matches = [{"name": n, "mentions": counts[n]} for n in names[:limit]]
    return {"matches": matches, "total_found": len(names), "query": name_query, "limited_to": limit}

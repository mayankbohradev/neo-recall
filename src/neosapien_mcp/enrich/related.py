"""Related-memory scoring and lookup."""

from __future__ import annotations

from neosapien_mcp.models.memory import MemoryLight


def relatedness_score(
    anchor: MemoryLight,
    other: MemoryLight,
    *,
    ignore_people: set[str] | None = None,
) -> float:
    """
    Overlap score for corpus linking.

    Weights (participants > entities > topics > domains):
    same people usually = same thread; topics like "AI" are noisier.
    ignore_people: corpus-dominant names (e.g. the account owner) that would
    otherwise make every pair look related.
    """
    if anchor.id == other.id:
        return 0.0

    ignore = {p.lower() for p in (ignore_people or set())}

    score = 0.0
    a_part = {p.lower() for p in anchor.participants if p and p.lower() not in ignore}
    o_part = {p.lower() for p in other.participants if p and p.lower() not in ignore}
    score += 3.0 * len(a_part & o_part)

    a_ent = {
        e.lower()
        for e in (anchor.mentioned_entities + anchor.present_entities)
        if e and e.lower() not in ignore
    }
    o_ent = {
        e.lower()
        for e in (other.mentioned_entities + other.present_entities)
        if e and e.lower() not in ignore
    }
    score += 2.0 * len(a_ent & o_ent)

    a_topics = {t.lower() for t in anchor.topics if t}
    o_topics = {t.lower() for t in other.topics if t}
    score += 1.0 * len(a_topics & o_topics)

    a_dom = {d.lower() for d in anchor.domains if d}
    o_dom = {d.lower() for d in other.domains if d}
    score += 0.5 * len(a_dom & o_dom)

    return score


def _dominant_people(memories: list[MemoryLight], *, threshold: float = 0.35) -> set[str]:
    """Names present on a large fraction of memories (usually the account owner)."""
    if not memories:
        return set()
    from collections import Counter

    c: Counter[str] = Counter()
    for m in memories:
        c.update({p.lower() for p in m.participants if p})
    n = len(memories)
    return {name for name, cnt in c.items() if cnt / n >= threshold}


def find_related(
    memories: list[MemoryLight],
    memory_id: str,
    *,
    limit: int = 10,
) -> list[dict]:
    anchor = next((m for m in memories if m.id == memory_id), None)
    if anchor is None:
        return []

    ignore = _dominant_people(memories)
    scored: list[tuple[float, MemoryLight, list[str]]] = []
    for other in memories:
        s = relatedness_score(anchor, other, ignore_people=ignore)
        if s <= 0:
            continue
        shared: list[str] = []
        for p in set(anchor.participants) & set(other.participants):
            if p.lower() in ignore:
                continue
            shared.append(f"participant:{p}")
        for e in set(anchor.mentioned_entities) & set(other.mentioned_entities):
            if e.lower() in ignore:
                continue
            shared.append(f"entity:{e}")
        for t in set(anchor.topics) & set(other.topics):
            shared.append(f"topic:{t}")
        for d in set(anchor.domains) & set(other.domains):
            shared.append(f"domain:{d}")
        scored.append((s, other, shared))

    scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
    out: list[dict] = []
    for s, m, shared in scored[:limit]:
        out.append(
            {
                "id": m.id,
                "title": m.title,
                "summary": m.summary[:200],
                "created_at": m.created_at,
                "score": round(s, 2),
                "shared": shared[:12],
            }
        )
    return out

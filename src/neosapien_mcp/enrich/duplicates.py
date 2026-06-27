"""Near-duplicate memory detection for cleanup."""

from __future__ import annotations

import re
from typing import Any

from neosapien_mcp.models.memory import MemoryLight

_WORD = re.compile(r"[a-z0-9]{3,}", re.I)


def _tokens(m: MemoryLight) -> set[str]:
    text = f"{m.title} {m.summary}".lower()
    return set(_WORD.findall(text))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def duplicate_candidates(
    memories: list[MemoryLight],
    *,
    threshold: float = 0.55,
    limit: int = 25,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Pairwise near-duplicates on title+summary tokens.

    Scoped to a date window when provided (recommended — full corpus is O(n²)).
    """
    pool = memories
    if start_date:
        pool = [m for m in pool if m.created_at and m.created_at >= start_date]
    if end_date:
        pool = [m for m in pool if m.created_at and m.created_at <= end_date]
    # Cap pairwise work
    pool = sorted(pool, key=lambda m: m.created_at, reverse=True)[:400]
    tok = {m.id: _tokens(m) for m in pool}
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(pool):
        ta = tok[a.id]
        if len(ta) < 3:
            continue
        for b in pool[i + 1 : i + 40]:  # local neighborhood by recency
            tb = tok[b.id]
            sim = jaccard(ta, tb)
            if sim < threshold:
                continue
            # Prefer short+thin pairs as cleanup candidates
            thin = a.duration_sec < 30 and b.duration_sec < 30
            pairs.append(
                {
                    "score": round(sim, 3),
                    "a": {"id": a.id, "title": a.title, "created_at": a.created_at},
                    "b": {"id": b.id, "title": b.title, "created_at": b.created_at},
                    "likely_noise_pair": thin,
                }
            )
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return {
        "threshold": threshold,
        "scanned": len(pool),
        "count": min(len(pairs), limit),
        "items": pairs[:limit],
        "note": "Read-only suggestions — delete only in the NeoSapien app",
    }

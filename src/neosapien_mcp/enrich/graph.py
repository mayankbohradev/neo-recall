"""Memory graph: nodes + edges from relatedness scores."""

from __future__ import annotations

from typing import Any

from neosapien_mcp.enrich.related import relatedness_score
from neosapien_mcp.models.memory import MemoryLight


def memory_graph(
    memories: list[MemoryLight],
    *,
    seed_id: str,
    depth: int = 1,
    limit: int = 15,
    min_score: float = 0.5,
) -> dict[str, Any]:
    """
    Ego graph around a seed memory.

    depth=1: direct neighbors only. depth=2: also neighbors-of-neighbors
    (capped) for a denser map without O(n²) full corpus graph.
    """
    from neosapien_mcp.enrich.related import _dominant_people

    by_id = {m.id: m for m in memories}
    seed = by_id.get(seed_id)
    if not seed:
        return {"seed_id": seed_id, "error": "memory not found", "nodes": [], "edges": []}

    ignore = _dominant_people(memories)

    def neighbors(anchor: MemoryLight) -> list[tuple[float, MemoryLight]]:
        scored = []
        for other in memories:
            s = relatedness_score(anchor, other, ignore_people=ignore)
            if s >= min_score:
                scored.append((s, other))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:limit]

    nodes: dict[str, dict[str, Any]] = {
        seed.id: {
            "id": seed.id,
            "title": seed.title,
            "created_at": seed.created_at,
            "topics": seed.topics[:6],
            "people": seed.participants[:6],
            "layer": 0,
        }
    }
    edges: list[dict[str, Any]] = []

    ring1 = neighbors(seed)
    for s, m in ring1:
        nodes[m.id] = {
            "id": m.id,
            "title": m.title,
            "created_at": m.created_at,
            "topics": m.topics[:6],
            "people": m.participants[:6],
            "layer": 1,
        }
        edges.append({"source": seed.id, "target": m.id, "score": round(s, 2), "layer": 1})

    if depth >= 2:
        for _, m in ring1[: max(3, limit // 3)]:
            for s, n in neighbors(m):
                if n.id == seed.id:
                    continue
                if n.id not in nodes:
                    nodes[n.id] = {
                        "id": n.id,
                        "title": n.title,
                        "created_at": n.created_at,
                        "topics": n.topics[:6],
                        "people": n.participants[:6],
                        "layer": 2,
                    }
                edges.append({"source": m.id, "target": n.id, "score": round(s, 2), "layer": 2})
                if len(nodes) >= limit + 1:
                    break
            if len(nodes) >= limit + 1:
                break

    return {
        "seed_id": seed_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges[: limit * 3],
        "note": "Edges weighted participants(3) > entities(2) > topics(1) > domains(0.5)",
    }

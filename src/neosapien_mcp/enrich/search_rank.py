"""Local BM25-style ranking over light memory text (no remote FTS dependency)."""

from __future__ import annotations

import math
import re
from collections import Counter

from neosapien_mcp.models.memory import MemoryLight

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_'/-]{1,}", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def rank_memories(
    memories: list[MemoryLight],
    query: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[float, MemoryLight]]:
    """
    Okapi BM25 over title/summary/topics/people/questions.

    Substring fallback: if BM25 yields nothing (typo / very short query),
    keep memories whose searchable_text contains the raw query.
    """
    q_tokens = tokenize(query)
    if not q_tokens:
        return [(0.0, m) for m in memories]

    docs = [tokenize(m.searchable_text()) for m in memories]
    N = len(docs) or 1
    avgdl = sum(len(d) for d in docs) / N
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))

    scored: list[tuple[float, MemoryLight]] = []
    for m, doc in zip(memories, docs, strict=True):
        if not doc:
            continue
        tf = Counter(doc)
        score = 0.0
        for term in q_tokens:
            if term not in tf:
                continue
            n_qi = df.get(term, 0)
            idf = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * len(doc) / (avgdl or 1))
            score += idf * (freq * (k1 + 1)) / (denom or 1)
        # Title/phrase bonus for exact contiguous match
        hay = m.searchable_text()
        if query.strip().lower() in hay:
            score += 2.0
        if score > 0:
            scored.append((score, m))

    if not scored:
        q = query.strip().lower()
        scored = [(0.1, m) for m in memories if q in m.searchable_text()]

    scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
    return scored

"""Local BM25-style ranking over light memory text (no remote FTS dependency).

Why this is more than plain BM25
--------------------------------
Users ask questions, not keywords: "what did <person> say about <topic>". Plain BM25 over a
single flat text blob handles that badly, for two reasons:

1. **Question words match everything.** "what", "did", "say", "about" appear in nearly
   every memory, so a 6-word question drags in ~75% of the corpus (measured: 2251/3041)
   and the ranking is then decided by whichever chatty memory repeats "about" the most.
   -> We drop stopwords from the query, and require a match on a CONTENT word.

2. **A flat blob loses signal.** Blending title/summary/topics/people into one string
   makes a name matching a participant score the same as that name appearing mid-sentence
   in a summary. -> We score fields separately and weight them.

Both fixes are pure Python over the already-cached index — no new dependencies, no index
to rebuild, and the corpus (~3k memories, ~2M chars) still ranks in ~0.1s.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from neosapien_mcp.models.memory import MemoryLight

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_'/-]{1,}", re.I)

# Question scaffolding + generic filler. These carry no retrieval signal in a personal
# memory corpus: every recorded conversation is something someone "said" "about" a topic.
STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those there here
    i me my mine myself we us our ours you your yours he him his she her hers it its
    they them their theirs who whom whose what which when where why how
    is am are was were be been being do does did doing done have has had having
    will would shall should can could may might must
    of in on at to from by for with about into over after before between during
    up down out off again further once
    not no nor only own same so too very just also
    say says said tell tells told talk talks talked talking speak spoke spoken
    discuss discussed discussing mention mentioned conversation memory memories
    show find get give me any some all thing things stuff
    """.split()
)

# Field weights. A title hit is a strong signal of aboutness; a summary hit is weak.
W_TITLE = 3.0
W_TOPICS = 2.0
W_PEOPLE = 2.5  # a named person IS usually the point of the question
W_TAGS = 1.5
W_SUMMARY = 1.0
W_QUESTIONS = 1.0


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def content_tokens(query: str) -> list[str]:
    """Query tokens with stopwords removed — falls back to raw tokens if all were stop."""
    toks = tokenize(query)
    kept = [t for t in toks if t not in STOPWORDS]
    return kept or toks


def _field_text(m: MemoryLight) -> dict[str, str]:
    return {
        "title": m.title or "",
        "topics": " ".join(m.topics),
        "people": " ".join(m.participants + m.mentioned_entities + m.present_entities),
        "tags": " ".join(m.tags),
        "summary": m.summary or "",
        "questions": " ".join(m.questions),
    }


_WEIGHTS = {
    "title": W_TITLE,
    "topics": W_TOPICS,
    "people": W_PEOPLE,
    "tags": W_TAGS,
    "summary": W_SUMMARY,
    "questions": W_QUESTIONS,
}


def rank_memories(
    memories: list[MemoryLight],
    query: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
    min_score: float = 0.35,
) -> list[tuple[float, MemoryLight]]:
    """
    Field-weighted BM25 with stopword-stripped queries.

    Returns (score, memory) sorted best-first. Memories scoring below `min_score` are
    dropped: without a floor, a single incidental term match keeps a memory in the
    result set forever, which is how a 6-word question came back with 2251 "hits".
    """
    q_tokens = content_tokens(query)
    if not q_tokens:
        return [(0.0, m) for m in memories]
    q_set = set(q_tokens)

    # Per-field corpora, so IDF is computed within a field rather than across a blob.
    fields = list(_WEIGHTS)
    docs: list[dict[str, list[str]]] = [
        {f: tokenize(t) for f, t in _field_text(m).items()} for m in memories
    ]
    N = len(docs) or 1
    avgdl = {f: (sum(len(d[f]) for d in docs) / N) or 1.0 for f in fields}
    df: dict[str, Counter[str]] = {f: Counter() for f in fields}
    for d in docs:
        for f in fields:
            df[f].update(set(d[f]) & q_set)

    scored: list[tuple[float, MemoryLight]] = []
    for m, doc in zip(memories, docs, strict=True):
        score = 0.0
        for f in fields:
            toks = doc[f]
            if not toks:
                continue
            tf = Counter(toks)
            dl = len(toks)
            for term in q_tokens:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                n_qi = df[f].get(term, 0)
                idf = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))
                denom = freq + k1 * (1 - b + b * dl / avgdl[f])
                score += _WEIGHTS[f] * idf * (freq * (k1 + 1)) / (denom or 1)

        if score <= 0:
            continue

        hay = m.searchable_text()
        # Exact contiguous phrase — strongest signal a user can give.
        if query.strip().lower() in hay:
            score += 6.0

        # Reward covering MORE of the question's content words, so a memory hitting
        # both the person and the topic beats one hitting the topic five times.
        covered = sum(1 for t in q_set if t in hay)
        if len(q_set) > 1:
            score *= 1.0 + 0.6 * (covered / len(q_set))

        # A query term matching an entity name is near-categorical intent: "what did
        # <person> say about <topic>" asks about that person, not about any memory that
        # happens to contain their name. Term frequency cannot express this — a long
        # document about the topic with no mention of the person will otherwise outrank
        # the conversation the user actually wants. When the query names an entity present
        # in the memory AND another content word also lands, treat it as the conjunction
        # the user meant.
        # The entity list is not purely people — upstream mixes in products, orgs and
        # places. A term that is ALSO a common topic/title term across the corpus is
        # therefore not evidence of entity intent (a project name appears in both the
        # entity list and half the titles). Only boost on terms that behave like proper
        # nouns here: present in the entity field and rare in topical fields.
        named = q_set & set(doc["people"])
        named = {t for t in named if df["topics"].get(t, 0) + df["title"].get(t, 0) < N * 0.02}
        if named:
            other_hits = sum(1 for t in (q_set - named) if t in hay)
            if len(q_set) > len(named) and other_hits:
                score *= 2.5  # entity + topic both present — this is the conjunction meant
            else:
                score *= 1.4  # entity named, nothing else to corroborate

        scored.append((score, m))

    scored = [(s, m) for s, m in scored if s >= min_score]

    # Fallback: a strict floor can empty the list for rare/typo'd terms. Prefer a weak
    # substring answer over "nothing found" — the caller can still see the low scores.
    if not scored:
        q = query.strip().lower()
        scored = [(0.1, m) for m in memories if q in m.searchable_text()]
        if not scored:
            scored = [
                (0.05, m) for m in memories if any(t in m.searchable_text() for t in q_tokens)
            ]

    scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
    return scored

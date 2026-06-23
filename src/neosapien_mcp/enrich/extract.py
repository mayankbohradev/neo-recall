"""Action items, follow-ups, and decision-log heuristics over light fields."""

from __future__ import annotations

import re
from typing import Any

from neosapien_mcp.models.memory import MemoryLight

_ACTION = re.compile(
    r"(?i)\b(action items?|todo|to-do|need to|we should|will\s+\w+|follow[- ]?up|"
    r"next steps?|owner:|assign(?:ed)?\s+to)\b"
)
_DECISION = re.compile(
    r"(?i)\b(decid(?:e|ed|ing)|decision|agreed|we'?ll go with|chose|chosen|"
    r"instead of|revisit|changed (?:our )?mind|pivot(?:ed)?|final(?:ly)?)\b"
)
_FOLLOW = re.compile(
    r"(?i)\b(next (?:week|monday|tuesday|wednesday|thursday|friday)|tomorrow|"
    r"by\s+\w+day|follow[- ]?up|ping|remind|schedule|due|deadline|"
    r"will (?:call|send|share|check))\b"
)
_DATEISH = re.compile(
    r"(?i)\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2})\b"
)


def action_items(
    memories: list[MemoryLight],
    *,
    limit: int = 40,
) -> dict[str, Any]:
    """Prefer Firestore `questions`; fall back to MOM-like lines in summary."""
    items: list[dict[str, Any]] = []
    for m in sorted(memories, key=lambda x: x.created_at, reverse=True):
        for q in m.questions:
            items.append(
                {
                    "memory_id": m.id,
                    "title": m.title,
                    "created_at": m.created_at,
                    "kind": "question",
                    "text": q,
                    "people": m.participants[:6],
                }
            )
        if m.tasks_count > 0 and not m.questions:
            items.append(
                {
                    "memory_id": m.id,
                    "title": m.title,
                    "created_at": m.created_at,
                    "kind": "tasks_count",
                    "text": f"{m.tasks_count} task(s) flagged on this memory",
                    "people": m.participants[:6],
                }
            )
        # Summary bullets that look like commitments
        for line in (m.summary or "").split("."):
            line = line.strip()
            if len(line) > 25 and _ACTION.search(line):
                items.append(
                    {
                        "memory_id": m.id,
                        "title": m.title,
                        "created_at": m.created_at,
                        "kind": "summary_cue",
                        "text": line[:240],
                        "people": m.participants[:6],
                    }
                )
        if len(items) >= limit * 2:
            break
    return {"count": min(len(items), limit), "items": items[:limit]}


def follow_ups_due(
    memories: list[MemoryLight],
    *,
    limit: int = 30,
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for m in sorted(memories, key=lambda x: x.created_at, reverse=True):
        blob = f"{m.title}. {m.summary}. " + " ".join(m.questions)
        if not (_FOLLOW.search(blob) or _DATEISH.search(blob)):
            continue
        cue = None
        for q in m.questions:
            if _FOLLOW.search(q) or _DATEISH.search(q):
                cue = q
                break
        if not cue:
            for sent in re.split(r"[.!?]\s+", m.summary or ""):
                if _FOLLOW.search(sent) or _DATEISH.search(sent):
                    cue = sent.strip()[:240]
                    break
        hits.append(
            {
                "memory_id": m.id,
                "title": m.title,
                "created_at": m.created_at,
                "cue": cue or (m.summary or "")[:160],
                "people": m.participants[:6],
                "topics": m.topics[:6],
            }
        )
        if len(hits) >= limit:
            break
    return {"count": len(hits), "items": hits}


def decision_log(
    memories: list[MemoryLight],
    *,
    topic: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Chronological decision / pivot cues; optional topic filter."""
    q = (topic or "").strip().lower()
    cand = memories
    if q:
        cand = [m for m in memories if q in m.searchable_text()]
    events: list[dict[str, Any]] = []
    for m in sorted(cand, key=lambda x: x.created_at):
        blob = f"{m.title}. {m.summary}"
        if not _DECISION.search(blob):
            continue
        snippet = None
        for sent in re.split(r"[.!?]\s+", blob):
            if _DECISION.search(sent):
                snippet = sent.strip()[:260]
                break
        events.append(
            {
                "memory_id": m.id,
                "title": m.title,
                "created_at": m.created_at,
                "snippet": snippet or (m.summary or "")[:200],
                "topics": m.topics[:6],
                "people": m.participants[:6],
            }
        )
        if len(events) >= limit:
            break

    # Soft contradiction pairs: same topic, decision language, later memory
    contradictions: list[dict[str, Any]] = []
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        for t in e["topics"] or ["(untagged)"]:
            by_topic.setdefault(t.lower(), []).append(e)
    for t, arr in by_topic.items():
        if len(arr) < 2:
            continue
        # last two decision-ish events on same topic
        a, b = arr[-2], arr[-1]
        if a["memory_id"] == b["memory_id"]:
            continue
        if any(
            w in (b["snippet"] or "").lower()
            for w in ("instead", "revisit", "changed", "pivot", "rather")
        ):
            contradictions.append(
                {
                    "topic": t,
                    "earlier": a,
                    "later": b,
                    "note": "Later decision language may revise an earlier call — verify in MOM/transcript",
                }
            )
        if len(contradictions) >= 10:
            break

    return {
        "topic_filter": topic,
        "decision_count": len(events),
        "decisions": events,
        "possible_revisions": contradictions,
    }

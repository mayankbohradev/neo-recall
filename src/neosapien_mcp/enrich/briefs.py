"""Corpus synthesis: weekly brief + people digest."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from neosapien_mcp.models.memory import MemoryLight


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    raw = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def filter_window(
    memories: list[MemoryLight],
    *,
    start: str | None,
    end: str | None,
) -> list[MemoryLight]:
    out: list[MemoryLight] = []
    for m in memories:
        ts = m.created_at
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        out.append(m)
    return out


def default_week_bounds() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
    end = now.strftime("%Y-%m-%dT23:59:59Z")
    return start, end


def build_weekly_brief(memories: list[MemoryLight], *, start: str, end: str) -> str:
    """
    Deterministic narrative over a date window.

    Groups by top topics/domains/people; lists substantive titles.
    No remote LLM — reliable offline synthesis for the MCP host to refine.
    """
    if not memories:
        return f"# Weekly brief ({start[:10]} → {end[:10]})\n\nNo memories in this window."

    topic_c: Counter[str] = Counter()
    domain_c: Counter[str] = Counter()
    people_c: Counter[str] = Counter()
    for m in memories:
        topic_c.update(m.topics)
        domain_c.update(m.domains)
        people_c.update(m.participants)
        people_c.update(m.mentioned_entities)

    # Prefer longer / richer items as "main threads"
    ranked = sorted(
        memories,
        key=lambda m: (len(m.summary), m.duration_sec, len(m.topics)),
        reverse=True,
    )
    top = ranked[:8]

    lines = [
        f"# Weekly brief ({start[:10]} → {end[:10]})",
        "",
        f"**{len(memories)} memories** in window.",
        "",
        "## Main threads",
    ]
    for m in top:
        topics = ", ".join(m.topics[:3]) or "—"
        lines.append(f"- **{m.title or 'Untitled'}** ({m.created_at[:10]}) — {topics}")
        if m.summary:
            lines.append(f"  - {m.summary[:180]}{'…' if len(m.summary) > 180 else ''}")

    lines += ["", "## Top topics"]
    for t, n in topic_c.most_common(8):
        lines.append(f"- {t} ({n})")

    lines += ["", "## Domains"]
    for d, n in domain_c.most_common(6):
        lines.append(f"- {d} ({n})")

    lines += ["", "## People who showed up"]
    for p, n in people_c.most_common(10):
        lines.append(f"- {p} ({n})")

    lines += [
        "",
        "## Decisions / intentions (from summaries)",
    ]
    decisionish = [
        m
        for m in ranked
        if any(
            w in (m.summary or "").lower()
            for w in ("decid", "plan", "will ", "need to", "agree", "ship", "launch")
        )
    ][:6]
    if not decisionish:
        lines.append("- (none detected via keyword scan — open individual MOM for detail)")
    else:
        for m in decisionish:
            lines.append(f"- {m.title}: {m.summary[:160]}{'…' if len(m.summary) > 160 else ''}")

    return "\n".join(lines)


def build_people_digest(memories: list[MemoryLight], name: str, *, limit: int = 20) -> str:
    """
    Merge memories where `name` appears as participant OR mentioned entity OR title/summary.

    Owner-scoped filtering is the caller's job when multi-owner; for single-user Firestore
    reads, participant/entity match is the important fallback.
    """
    q = name.strip().lower()
    if not q:
        return "Provide a non-empty name."

    matched: list[MemoryLight] = []
    for m in memories:
        hay = " ".join(
            [
                " ".join(m.participants),
                " ".join(m.mentioned_entities),
                " ".join(m.present_entities),
                m.title,
                m.summary,
            ]
        ).lower()
        if q in hay:
            matched.append(m)

    matched.sort(key=lambda m: m.created_at, reverse=True)
    matched = matched[:limit]

    if not matched:
        return (
            f"# People digest: {name}\n\nNo memories matched as participant, "
            "mentioned entity, or text. Try a shorter name fragment."
        )

    topics: Counter[str] = Counter()
    for m in matched:
        topics.update(m.topics)

    lines = [
        f"# People digest: {name}",
        "",
        f"**{len(matched)} memories** (participant / entity / text match).",
        "",
        "## Recurring topics",
    ]
    for t, n in topics.most_common(8):
        lines.append(f"- {t} ({n})")

    lines += ["", "## Recent conversations"]
    for m in matched:
        role_bits = []
        if any(q in p.lower() for p in m.participants):
            role_bits.append("participant")
        if any(q in e.lower() for e in m.mentioned_entities):
            role_bits.append("mentioned")
        role = "+".join(role_bits) or "text"
        lines.append(
            f"- **{m.title or 'Untitled'}** ({m.created_at[:10]}, {role}) — "
            f"{(m.summary or '')[:140]}{'…' if len(m.summary) > 140 else ''}"
        )

    return "\n".join(lines)


def build_topic_timeline(
    memories: list[MemoryLight],
    topic: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> str:
    """Chronological synthesis of how a topic shows up across memories."""
    q = topic.strip().lower()
    if not q:
        return "Provide a non-empty topic."

    matched = [
        m
        for m in memories
        if any(q in t.lower() for t in m.topics)
        or q in (m.title or "").lower()
        or q in (m.summary or "").lower()
    ]
    if start or end:
        matched = filter_window(matched, start=start, end=end)

    matched.sort(key=lambda m: m.created_at)  # chronological ascending

    if not matched:
        return f"# Topic timeline: {topic}\n\nNo memories matched."

    people: Counter[str] = Counter()
    for m in matched:
        people.update(m.participants)
        people.update(m.mentioned_entities)

    lines = [
        f"# Topic timeline: {topic}",
        "",
        f"**{len(matched)} memories** from {matched[0].created_at[:10]} → {matched[-1].created_at[:10]}.",
        "",
        "## Chronology",
    ]
    for m in matched:
        lines.append(f"- **{m.created_at[:10]}** — {m.title or 'Untitled'}")
        if m.summary:
            lines.append(f"  - {m.summary[:160]}{'…' if len(m.summary) > 160 else ''}")
        if m.participants:
            lines.append(f"  - with: {', '.join(m.participants[:5])}")

    lines += ["", "## People around this topic"]
    for p, n in people.most_common(10):
        lines.append(f"- {p} ({n})")

    return "\n".join(lines)

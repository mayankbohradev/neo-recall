"""Period compare + habit signals over the light index."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from neosapien_mcp.models.memory import MemoryLight


def _parse(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window(memories: list[MemoryLight], start: str, end: str) -> list[MemoryLight]:
    out: list[MemoryLight] = []
    for m in memories:
        if m.created_at and start <= m.created_at <= end:
            out.append(m)
    return out


def _facet(memories: list[MemoryLight], attr: str, n: int = 8) -> list[dict[str, Any]]:
    c: Counter[str] = Counter()
    for m in memories:
        c.update(getattr(m, attr) or [])
    return [{"name": k, "count": v} for k, v in c.most_common(n)]


def _people(memories: list[MemoryLight], n: int = 8) -> list[dict[str, Any]]:
    c: Counter[str] = Counter()
    for m in memories:
        c.update(m.participants)
        c.update(m.mentioned_entities)
    return [{"name": k, "count": v} for k, v in c.most_common(n)]


def compare_periods(
    memories: list[MemoryLight],
    *,
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
) -> dict[str, Any]:
    a = _window(memories, period_a_start, period_a_end)
    b = _window(memories, period_b_start, period_b_end)

    def pack(label: str, items: list[MemoryLight], start: str, end: str) -> dict[str, Any]:
        dur = sum(m.duration_sec for m in items)
        return {
            "label": label,
            "start": start,
            "end": end,
            "count": len(items),
            "total_duration_sec": round(dur, 1),
            "avg_duration_sec": round(dur / len(items), 1) if items else 0.0,
            "top_topics": _facet(items, "topics"),
            "top_domains": _facet(items, "domains"),
            "top_people": _people(items),
        }

    pa = pack("period_A", a, period_a_start, period_a_end)
    pb = pack("period_B", b, period_b_start, period_b_end)
    topics_a = {x["name"] for x in pa["top_topics"]}
    topics_b = {x["name"] for x in pb["top_topics"]}
    return {
        "period_a": pa,
        "period_b": pb,
        "delta": {
            "count": pb["count"] - pa["count"],
            "total_duration_sec": round(pb["total_duration_sec"] - pa["total_duration_sec"], 1),
            "topics_new_in_b": sorted(topics_b - topics_a)[:12],
            "topics_gone_from_a": sorted(topics_a - topics_b)[:12],
        },
    }


def default_week_vs_prior() -> tuple[str, str, str, str]:
    now = datetime.now(timezone.utc)
    b_end = now.strftime("%Y-%m-%dT23:59:59Z")
    b_start = (now - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
    a_end = (now - timedelta(days=7)).strftime("%Y-%m-%dT23:59:59Z")
    a_start = (now - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z")
    return a_start, a_end, b_start, b_end


def habit_signals(
    memories: list[MemoryLight],
    *,
    start: str | None = None,
    end: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not end:
        end = now.strftime("%Y-%m-%dT23:59:59Z")
    if not start:
        start = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    window = _window(memories, start, end)

    by_hour: Counter[int] = Counter()
    by_dow: Counter[str] = Counter()
    health = 0
    travel = 0
    meetingish = 0
    for m in window:
        dt = _parse(m.created_at)
        if dt:
            by_hour[dt.hour] += 1
            by_dow[dt.strftime("%A")] += 1
        blob = m.searchable_text()
        if any(x in blob for x in ("sleep", "health", "wellness", "exercise", "gym")):
            health += 1
        if any(x in blob for x in ("travel", "flight", "airport", "trip", "packing")):
            travel += 1
        if any(x in blob for x in ("meeting", "standup", "sync", "call")) or m.duration_sec > 600:
            meetingish += 1

    peak_hours = [{"hour_utc": h, "count": c} for h, c in by_hour.most_common(5)]
    return {
        "start": start,
        "end": end,
        "memory_count": len(window),
        "total_duration_sec": round(sum(m.duration_sec for m in window), 1),
        "peak_hours_utc": peak_hours,
        "by_weekday": dict(by_dow),
        "signals": {
            "health_wellness_mentions": health,
            "travel_mentions": travel,
            "meeting_like": meetingish,
        },
        "top_domains": _facet(window, "domains", 10),
        "top_topics": _facet(window, "topics", 10),
        "top_people": _people(window, 10),
    }

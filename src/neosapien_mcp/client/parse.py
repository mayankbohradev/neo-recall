"""Firestore typed-field unwrappers — ported from neo-memory-manager/neosapien.rs."""

from __future__ import annotations

from typing import Any

from neosapien_mcp.models.memory import MemoryDetail, MemoryLight, TranscriptSegment


def _str(fields: dict[str, Any], key: str) -> str:
    node = fields.get(key) or {}
    return node.get("stringValue") or ""


def _num(fields: dict[str, Any], key: str) -> float:
    node = fields.get(key) or {}
    if "doubleValue" in node:
        return float(node["doubleValue"])
    if "integerValue" in node:
        # Firestore REST: integerValue is a STRING
        try:
            return float(node["integerValue"])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _bool(fields: dict[str, Any], key: str) -> bool:
    node = fields.get(key) or {}
    return bool(node.get("booleanValue", False))


def _ts(fields: dict[str, Any], key: str) -> str:
    node = fields.get(key) or {}
    return node.get("timestampValue") or ""


def _arr(fields: dict[str, Any], key: str) -> list[str]:
    node = fields.get(key) or {}
    values = (node.get("arrayValue") or {}).get("values") or []
    out: list[str] = []
    for item in values:
        if "stringValue" in item:
            out.append(item["stringValue"])
    return out


def _normalize_ts(raw: str) -> str:
    if not raw:
        return ""
    # Match desktop: truncate fractional seconds for stable sort, keep Z
    if "T" in raw:
        head = raw[:19]
        return head + "Z" if not head.endswith("Z") else head
    return raw


def _duration_from_bounds(started: str, finished: str) -> float:
    """Derive seconds from started_at/finished_at when duration_sec is absent."""
    if not started or not finished:
        return 0.0
    try:
        from datetime import datetime

        a = datetime.fromisoformat(started.replace("Z", "+00:00"))
        b = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        return max(0.0, (b - a).total_seconds())
    except ValueError:
        return 0.0


def doc_id_from_name(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def parse_light(doc: dict[str, Any]) -> MemoryLight | None:
    name = doc.get("name")
    if not name:
        return None
    fields = doc.get("fields") or {}
    created = _normalize_ts(_ts(fields, "created_at") or _ts(fields, "createdAt"))
    started = _normalize_ts(_ts(fields, "started_at") or _ts(fields, "startedAt"))
    finished = _normalize_ts(_ts(fields, "finished_at") or _ts(fields, "finishedAt"))
    # Official MCP "participants" == Firestore `entities` (participants array is often empty)
    participants = _arr(fields, "participants") or _arr(fields, "entities")
    domains = _arr(fields, "domains")
    singular = _str(fields, "domain")
    if singular and singular not in domains:
        domains = [singular, *domains]
    duration = _num(fields, "duration_sec") or _num(fields, "durationSec")
    if duration <= 0:
        duration = _duration_from_bounds(started, finished)
    return MemoryLight(
        id=doc_id_from_name(name),
        title=_str(fields, "title"),
        summary=_str(fields, "summary"),
        duration_sec=duration,
        source=_str(fields, "source"),
        created_at=created,
        updated_at=_normalize_ts(_ts(fields, "updated_at") or _ts(fields, "updatedAt")),
        started_at=started,
        finished_at=finished,
        participants=participants,
        domains=domains,
        topics=_arr(fields, "topics"),
        emotions=_arr(fields, "emotions"),
        tags=_arr(fields, "tags"),
        mentioned_entities=_arr(fields, "mentioned_entities") or _arr(fields, "mentionedEntities"),
        present_entities=_arr(fields, "present_entities") or _arr(fields, "presentEntities"),
        questions=_arr(fields, "questions"),
        tasks_count=int(_num(fields, "tasks_count") or _num(fields, "tasksCount") or 0),
        archived=_bool(fields, "archived"),
        user_id=_str(fields, "user_id") or _str(fields, "userId"),
    )


def _extract_mom(fields: dict[str, Any]) -> str | None:
    for key in ("mom", "MOM", "minutes_of_meeting", "minutesOfMeeting"):
        val = _str(fields, key)
        if val:
            return val
        # MOM might be a mapValue — flatten best-effort
        node = fields.get(key) or {}
        if "mapValue" in node:
            return str(node["mapValue"])
    return None


def _extract_transcript(fields: dict[str, Any]) -> list[TranscriptSegment]:
    """Best-effort until probe.py confirms the exact Firestore shape."""
    for key in ("transcript", "transcript_segments", "transcriptSegments", "segments"):
        node = fields.get(key) or {}
        values = (node.get("arrayValue") or {}).get("values") or []
        if not values:
            continue
        segs: list[TranscriptSegment] = []
        for item in values:
            if "mapValue" in item:
                mf = (item["mapValue"] or {}).get("fields") or {}
                segs.append(
                    TranscriptSegment(
                        text=_str(mf, "text") or _str(mf, "content"),
                        speaker=_str(mf, "speaker"),
                        speaker_id=int(_num(mf, "speaker_id") or _num(mf, "speakerId") or 0)
                        or None,
                        is_user=_bool(mf, "is_user") if "is_user" in mf or "isUser" in mf else None,
                        start=_num(mf, "start") or None,
                        end=_num(mf, "end") or None,
                    )
                )
            elif "stringValue" in item:
                segs.append(TranscriptSegment(text=item["stringValue"]))
        if segs:
            return segs
    # Plain string transcript
    text = _str(fields, "transcript")
    if text:
        return [TranscriptSegment(text=text)]
    return []


def parse_detail(doc: dict[str, Any], *, include_mom: bool = True) -> MemoryDetail | None:
    light = parse_light(doc)
    if not light:
        return None
    fields = doc.get("fields") or {}
    return MemoryDetail(
        **light.model_dump(),
        mom=_extract_mom(fields) if include_mom else None,
        raw_fields=fields,
    )


def parse_transcript(doc: dict[str, Any]) -> list[TranscriptSegment]:
    fields = doc.get("fields") or {}
    return _extract_transcript(fields)


def list_field_keys(doc: dict[str, Any]) -> list[str]:
    return sorted((doc.get("fields") or {}).keys())

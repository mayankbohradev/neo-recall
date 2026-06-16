"""Local enrichment: quality score + triage (ported from classifier.rs)."""

from __future__ import annotations

from neosapien_mcp.models.memory import MemoryLight, RankedMemory, TriageResult


def compute_quality_score(memory: MemoryLight) -> int:
    """Rule-based 0–100 richness score — no LLM. Port of classifier.rs."""
    score = 0.0
    d = memory.duration_sec
    if d > 300:
        score += 30
    elif d > 120:
        score += 25
    elif d > 60:
        score += 20
    elif d > 30:
        score += 15
    elif d > 10:
        score += 10
    else:
        score += 5

    score += min(len(memory.participants) * 10.0, 20.0)
    score += min(len(memory.topics) * 5.0, 20.0)
    score += min(len(memory.summary) / 15.0, 20.0)
    score += min(len(memory.emotions) * 3.3, 10.0)
    return int(min(score, 100.0))


def prefilter_triage(memory: MemoryLight) -> TriageResult | None:
    """Instant noise detection. Returns None if AI/heuristic layer should decide."""
    empty = (
        memory.duration_sec < 3.0
        and not memory.summary
        and not memory.title
        and not memory.participants
    )
    if empty:
        return TriageResult(
            id=memory.id,
            title=memory.title,
            label="noise",
            confidence=0.99,
            reason=(
                "Recording under 3 seconds with no title, summary, or participants "
                "— likely an accidental trigger"
            ),
            quality_score=compute_quality_score(memory),
        )
    return None


def heuristic_triage(memory: MemoryLight) -> TriageResult:
    """
    Deterministic fallback when use_llm=False / Ollama unavailable.

    Rules mirror the desktop classifier intent:
    - self-talk / journaling with any summary → keep
    - very short + vague summary → review
    - otherwise keep if summary shows intentional content
    """
    q = compute_quality_score(memory)
    summary = (memory.summary or "").strip()
    title = (memory.title or "").strip()

    if not summary and not title and memory.duration_sec < 15:
        return TriageResult(
            id=memory.id,
            title=title,
            label="noise",
            confidence=0.85,
            reason="Near-empty short recording with no usable title or summary",
            quality_score=q,
        )

    if summary and len(summary) < 40 and memory.duration_sec < 20 and not memory.participants:
        return TriageResult(
            id=memory.id,
            title=title,
            label="review",
            confidence=0.6,
            reason="Short recording with a thin summary — ambiguous value",
            quality_score=q,
        )

    return TriageResult(
        id=memory.id,
        title=title,
        label="keep",
        confidence=0.8 if summary else 0.55,
        reason=(
            "Summary/title indicates intentional speech or note"
            if summary or title
            else "Default keep — insufficient signal to discard"
        ),
        quality_score=q,
    )


def triage_batch(memories: list[MemoryLight], *, use_llm: bool = False) -> list[TriageResult]:
    """Rule prefilter + heuristic. Optional Ollama path stubbed (use_llm ignored if no server)."""
    _ = use_llm  # reserved for local Ollama gemma — default off for ship reliability
    results: list[TriageResult] = []
    for m in memories:
        hit = prefilter_triage(m)
        results.append(hit if hit else heuristic_triage(m))
    return results


def rank_by_quality(
    memories: list[MemoryLight],
    *,
    limit: int = 20,
) -> list[RankedMemory]:
    scored = [
        RankedMemory(
            id=m.id,
            title=m.title,
            summary=m.summary[:240],
            quality_score=compute_quality_score(m),
            created_at=m.created_at,
            duration_sec=m.duration_sec,
            participants=m.participants,
            topics=m.topics,
        )
        for m in memories
    ]
    scored.sort(key=lambda r: (r.quality_score, r.created_at), reverse=True)
    return scored[:limit]

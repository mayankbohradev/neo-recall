"""Pydantic models for light/detail memories and profile."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    text: str = ""
    speaker: str = ""
    speaker_id: int | None = None
    is_user: bool | None = None
    person_id: str | None = None
    start: float | None = None
    end: float | None = None


class MemoryLight(BaseModel):
    """List/search payload — never includes transcript or MOM."""

    id: str
    title: str = ""
    summary: str = ""
    duration_sec: float = 0.0
    source: str = ""
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    participants: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    mentioned_entities: list[str] = Field(default_factory=list)
    present_entities: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    tasks_count: int = 0
    archived: bool = False
    user_id: str = ""

    def searchable_text(self) -> str:
        parts = [
            self.title,
            self.summary,
            " ".join(self.topics),
            " ".join(self.domains),
            " ".join(self.tags),
            " ".join(self.participants),
            " ".join(self.mentioned_entities),
            " ".join(self.questions),
        ]
        return " ".join(parts).lower()


class MemoryDetail(MemoryLight):
    """Single-memory detail — MOM optional, transcript never bundled here by default."""

    mom: str | None = None
    raw_fields: dict[str, Any] = Field(default_factory=dict, exclude=True)


class Profile(BaseModel):
    """PII-minimized profile — audit-safe surface only."""

    display_name: str = ""
    email: str = ""
    subscription_status: str | None = None


class TriageResult(BaseModel):
    id: str
    title: str = ""
    label: str  # noise | review | keep
    confidence: float
    reason: str
    quality_score: int


class RankedMemory(BaseModel):
    id: str
    title: str = ""
    summary: str = ""
    quality_score: int
    created_at: str = ""
    duration_sec: float = 0.0
    participants: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)

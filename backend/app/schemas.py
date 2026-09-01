from typing import Literal

from pydantic import BaseModel, Field


class Attempt(BaseModel):
    action: str
    result: str
    at: str


class Hypothesis(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)


class Incident(BaseModel):
    id: str
    title: str
    service: str
    severity: Literal["SEV-1", "SEV-2", "SEV-3"]
    status: Literal["investigating", "monitoring", "resolved"]
    started_at: str
    impact: str
    observations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    attempted_actions: list[Attempt] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    demo_epoch: str


class Recommendation(BaseModel):
    action: str
    rationale: str
    confidence: float = Field(ge=0, le=1)
    blocked_actions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    tier: Literal["HOT", "WARM", "COLD"]
    label: str
    detail: str
    source: str


class JournalEvent(BaseModel):
    id: str
    timestamp: str
    kind: str
    summary: str
    outcome: str | None = None


class DemoState(BaseModel):
    incident: Incident
    recommendation: Recommendation
    stateless_recommendation: str
    memories: list[MemoryItem]
    journal: list[JournalEvent]
    session_id: str
    memory_backend: str
    is_fresh_session: bool


class EventCreate(BaseModel):
    kind: Literal["observation", "action", "constraint", "hypothesis"]
    summary: str = Field(min_length=3, max_length=280)
    outcome: str | None = Field(default=None, max_length=280)
    confidence: float | None = Field(default=None, ge=0, le=1)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    memory_backend: str


class ErrorResponse(BaseModel):
    detail: str


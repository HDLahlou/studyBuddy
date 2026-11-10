"""Models for engine-written files under derived/ (decision 003 C1).

Engine-internal for v0. They move to schema/ (a minor contract bump) when the GUI first reads
them over the API in step 5. metrics.json uses the contract's ic_schema.report.Metrics.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ic_schema.report import Metrics, Phase


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GapRange(_Model):
    first: int
    last: int


class AudioIngest(_Model):
    chunks: int
    chunk_gaps: list[GapRange]
    bytes: int
    joined: bool
    offset_s: float | None


class IngestReport(_Model):
    session_id: str
    schema_version: str
    compatible: bool
    ended: bool
    complete: bool
    events: int
    seq_gaps: list[GapRange]
    duplicates: int
    conflicts: int
    torn_tail: bool
    audio: AudioIngest | None
    warnings: list[str] = Field(default_factory=list)


class NormalizeReport(_Model):
    snapshots: int
    redundant_snapshots: list[str]
    diffs: int
    lines_added: int
    lines_deleted: int


class Span(_Model):
    start: float
    end: float
    evidence: list[str] = Field(default_factory=list)


class TypingSpan(Span):
    bursts: int
    keys: int


class ChurnWindow(_Model):
    start: float
    end: float
    added: int
    deleted: int
    churn: float
    high: bool


class FailStreak(Span):
    count: int


class FocusAway(Span):
    target: Literal["tab", "window"]


class Signals(_Model):
    idle_threshold_s: float
    idle: list[Span]
    typing: list[TypingSpan]
    churn_windows: list[ChurnWindow]
    fail_streaks: list[FailStreak]
    focus_away: list[FocusAway]
    pauses: list[Span]
    longest_gap_s: float


class SegmentSignals(_Model):
    runs: int
    fails: int
    churn: float | None
    longest_idle: float


class PhaseSegment(_Model):
    phase: Phase
    start: float
    end: float
    events: list[str]
    signals: SegmentSignals


class Phases(_Model):
    segments: list[PhaseSegment]
    tail: Span | None = Field(description="After the accepted submit; not counted in phase time.")
    rules: list[str] = Field(description="Which rule variants applied (e.g. no statement).")


class SessionFacts(_Model):
    session_id: str
    platform: str
    slug: str | None
    title: str | None
    difficulty: str | None
    mode: str
    session_language: str = Field(description="Capabilities.language: locked at the first action.")
    solution_language: str = Field(description="Language of the final code snapshot.")
    has_statement: bool
    has_audio: bool
    complete: bool
    accepted: bool
    final_verdict: str | None
    runs: int
    failed_runs: int
    submits: int
    failed_submits: int
    unknown_results: int


class Timeline(_Model):
    """derived/timeline.json: the design's list of phase segments, wrapped with session facts."""

    session_id: str
    facts: SessionFacts
    metrics: Metrics
    segments: list[PhaseSegment]
    tail: Span | None


StageStatus = Literal["ok", "skipped", "failed"]


class StageRun(_Model):
    status: StageStatus
    seconds: float
    message: str | None = None


class PipelineStatus(_Model):
    stages: dict[str, StageRun] = Field(default_factory=dict)

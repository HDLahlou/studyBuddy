"""Report schema (Component 3 output, `report/report.json`).

Numbers in `Metrics` and the verdict fields of `Correctness` are copied from the engine; the AI
only writes the prose and the evidence-cited findings. Model-level checks here cover what can be
checked without the timeline (spans, time lost, at least one citation); resolving cited ids
against real events is the AI layer's validation step.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ic_schema.events import Verdict
from ic_schema.version import SCHEMA_VERSION

Phase = Literal["read", "plan", "code", "debug", "test", "submit"]

TimeSinkCategory = Literal[
    "understanding",
    "input_parsing",
    "output_format",
    "algorithm_choice",
    "implementation",
    "debugging",
    "edge_cases",
    "syntax_api_recall",
    "communication",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Span(_Model):
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class Metrics(_Model):
    """Computed deterministically by the engine (pipeline step 7)."""

    total_time_s: float = Field(ge=0)
    time_per_phase_s: dict[Phase, float] = Field(default_factory=dict)
    time_to_first_run_s: float | None = Field(default=None, ge=0)
    time_to_first_passing_run_s: float | None = Field(default=None, ge=0)
    runs_before_accept: int | None = Field(default=None, ge=0)
    churn: float | None = Field(
        default=None, ge=0, description="Deleted / added lines, session-wide."
    )
    longest_idle_s: float = Field(default=0, ge=0)
    talk_ratio: float | None = Field(
        default=None, ge=0, le=1, description="Speech time / session time; null without audio."
    )


class Correctness(_Model):
    platform_verdict: Verdict | None = Field(
        description="Final submit verdict; null if never submitted."
    )
    accepted: bool
    runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    submits: int = Field(ge=0)
    explanation: str = Field(description="AI reasoning about failures and correctness.")
    evidence: list[str] = Field(default_factory=list)


class Complexity(_Model):
    time: str = Field(description='e.g. "O(n)"')
    space: str
    optimal: bool | None = None
    better_approach: str | None = None
    evidence: list[str] = Field(default_factory=list)


class Finding(_Span):
    title: str
    detail: str
    evidence: list[str] = Field(min_length=1, description="Cited event ids.")


class TimeSink(_Span):
    time_lost_s: float = Field(ge=0)
    category: TimeSinkCategory
    what_happened: str
    suggestion: str
    evidence: list[str] = Field(min_length=1, description="Cited event ids.")

    @model_validator(mode="after")
    def _check_time_lost(self) -> Self:
        if self.time_lost_s > self.end - self.start + 1e-9:
            raise ValueError("time_lost_s exceeds the span")
        return self


class Communication(_Model):
    thinking_aloud: str
    clarifying: str
    testing_out_loud: str
    evidence: list[str] = Field(default_factory=list)


class Report(_Model):
    schema_version: str = SCHEMA_VERSION
    session_id: str
    summary: str
    metrics: Metrics
    correctness: Correctness
    complexity: Complexity
    strengths: list[Finding]
    weaknesses: list[Finding]
    time_sinks: list[TimeSink]
    communication: Communication
    vs_self_assessment: str = Field(description="Where your read differs from the evidence.")
    vs_previous_attempts: str | None = Field(
        default=None, description="Most recent confirmed repeat only; null otherwise."
    )
    suggested_tests: list[str] = Field(
        default_factory=list, description="Edge cases to consider; never executed."
    )
    next_practice: list[str] = Field(default_factory=list)

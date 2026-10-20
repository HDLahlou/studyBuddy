"""Capability manifest and session manifest (`manifest.json`)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ic_schema.version import SCHEMA_VERSION

SessionMode = Literal["practice", "mock_interview", "assessment"]
StreamName = Literal["audio", "video"]

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Capabilities(_Model):
    """What this session's capture could record, so later stages know what to trust or skip."""

    platform: str = Field(description='"leetcode", "hackerrank", ...')
    adapter_version: str
    language: str = Field(description="Editor language as reported by the platform.")
    mode: SessionMode
    exact_code: bool
    run_events: bool
    keystrokes: Literal["none", "editor_scoped"]
    problem_statement: Literal["none", "scraped", "manual"]
    audio: bool
    video: bool


class ClockOrigin(_Model):
    wall_time_utc: datetime = Field(description="Wall-clock time of session_start (t = 0).")


class MediaStreamInfo(_Model):
    mime: str = Field(description='MediaRecorder mime type, e.g. "audio/webm;codecs=opus".')
    offset_s: float | None = Field(
        default=None, description="Start of the stream on the session clock (first chunk start)."
    )


class MediaInfo(_Model):
    audio: MediaStreamInfo | None = None
    video: MediaStreamInfo | None = None


class UserInputs(_Model):
    """Small inputs inline; larger ones are files under `inputs/`, referenced by relative path."""

    self_assessment: str | None = None
    target_time_s: float | None = Field(default=None, gt=0)
    reference_solution: str | None = Field(default=None, description="Path under inputs/.")
    tests: str | None = Field(default=None, description="Path under inputs/.")


class EndInfo(_Model):
    """Written when the extension sends `end`. Absent means the session never closed cleanly."""

    final_seq: int = Field(ge=0)
    final_chunk: dict[StreamName, int] = Field(default_factory=dict)


class Manifest(_Model):
    schema_version: str = SCHEMA_VERSION
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    capabilities: Capabilities
    clock_origin: ClockOrigin
    media: MediaInfo = Field(default_factory=MediaInfo)
    user_inputs: UserInputs = Field(default_factory=UserInputs)
    end: EndInfo | None = None

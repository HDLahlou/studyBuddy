"""Shared test helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ic_schema.manifest import Capabilities, ClockOrigin, Manifest, MediaInfo, MediaStreamInfo

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "fixtures"
GENERATED = REPO / "schema" / "generated"


def make_capabilities(**overrides: object) -> Capabilities:
    fields: dict[str, object] = {
        "platform": "leetcode",
        "adapter_version": "0.1.0",
        "language": "python3",
        "mode": "practice",
        "exact_code": True,
        "run_events": True,
        "keystrokes": "editor_scoped",
        "problem_statement": "scraped",
        "audio": True,
        "video": False,
        **overrides,
    }
    return Capabilities.model_validate(fields)


def make_manifest(session_id: str = "test_session", **overrides: object) -> Manifest:
    fields: dict[str, object] = {
        "session_id": session_id,
        "capabilities": make_capabilities(),
        "clock_origin": ClockOrigin(wall_time_utc=datetime(2026, 10, 19, 15, 0, tzinfo=UTC)),
        "media": MediaInfo(audio=MediaStreamInfo(mime="audio/webm;codecs=opus", offset_s=0.2)),
        **overrides,
    }
    return Manifest.model_validate(fields)

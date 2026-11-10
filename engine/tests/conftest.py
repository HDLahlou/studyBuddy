"""Engine tests replay fixtures/ bundles without a browser (CLAUDE.md). Stages write under
derived/, so every test works on a copy in tmp_path, never on fixtures/ itself."""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from engine.paths import SessionPaths
from engine.transcribe import RecordedTranscriber, Segment, WordTiming
from ic_schema.bundle import read_bundle
from ic_schema.events import SpeechEvent

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "fixtures"


@pytest.fixture
def bundle_copy(tmp_path: Path) -> Callable[[str], SessionPaths]:
    def copy(name: str) -> SessionPaths:
        dst = tmp_path / name
        shutil.copytree(FIXTURES / name, dst)
        return SessionPaths(dst)

    return copy


def recorded_from_fixture(name: str = "two_sum_basic") -> RecordedTranscriber:
    """What whisper would have returned for the fixture: its hand-written speech events, moved
    back onto the audio clock (minus the manifest audio offset)."""
    b = read_bundle(FIXTURES / name)
    audio = b.manifest.media.audio
    offset = audio.offset_s if audio and audio.offset_s is not None else 0.0
    segments = []
    for e in b.read_derived_events("transcript.jsonl"):
        if not isinstance(e, SpeechEvent):
            continue
        words = [
            WordTiming(w.w, w.start - offset, w.end - offset, w.p) for w in (e.data.words or [])
        ]
        avg_logprob = math.log(e.confidence)
        segments.append(Segment(e.t - offset, e.data.end - offset, e.data.text, words, avg_logprob))
    return RecordedTranscriber(segments)


@pytest.fixture
def recorded() -> RecordedTranscriber:
    return recorded_from_fixture()

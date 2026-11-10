from __future__ import annotations

import os
from collections.abc import Callable

import pytest

from engine import ingest, transcribe
from engine.cues import find_cues, find_markers
from engine.files import read_events
from engine.paths import SessionPaths
from engine.transcribe import RecordedTranscriber, Segment, WordTiming, build_events
from ic_schema.bundle import read_bundle
from ic_schema.events import MarkerEvent, SpeechEvent

from .conftest import FIXTURES


@pytest.mark.parametrize(
    "text, cues",
    [
        ("Wait. I put three in seen before I check.", ["wait"]),
        ("Why is it returning the same index twice?", ["why is"]),
        ("Let me think about duplicates.", ["let me think"]),
        ("Hmm, okay so the window shrinks.", ["hmm", "okay so"]),
        ("Waiting for the result", []),  # word boundaries: "waiting" is not "wait"
    ],
)
def test_cues(text: str, cues: list[str]) -> None:
    assert find_cues(text) == cues


@pytest.mark.parametrize(
    "text, labels",
    [
        ("Okay, I'm stuck. Let me trace example two.", ["stuck"]),
        ("I’m stuck", ["stuck"]),  # curly apostrophe
        ("Oh, I see, it finds itself.", ["idea"]),
        ("I'm done, submitting.", ["done"]),
        ("I'm not stuck anymore", []),  # conservative: no partial matches
        ("Stuck pixels are not a phrase", []),
    ],
)
def test_markers(text: str, labels: list[str]) -> None:
    assert [m[0] for m in find_markers(text)] == labels


def test_recorded_transcription_reproduces_fixture(
    bundle_copy: Callable[[str], SessionPaths], recorded: RecordedTranscriber
) -> None:
    paths = bundle_copy("two_sum_basic")
    expected = read_bundle(FIXTURES / "two_sum_basic").read_derived_events("transcript.jsonl")
    ingest.run(paths)
    msg = transcribe.run(paths, recorded)
    got = read_events(paths.d("transcript.jsonl"))
    assert msg.startswith("9 speech segments, 1 markers")

    exp_speech = [e for e in expected if isinstance(e, SpeechEvent)]
    got_speech = [e for e in got if isinstance(e, SpeechEvent)]
    assert [(e.id, e.t, e.data.end, e.data.text) for e in got_speech] == [
        (e.id, e.t, e.data.end, e.data.text) for e in exp_speech
    ]
    assert all(e.source == "whisper" and e.t_uncertainty == 0.2 for e in got_speech)
    assert [e.confidence for e in got_speech] == pytest.approx([e.confidence for e in exp_speech])

    (marker,) = [e for e in got if isinstance(e, MarkerEvent)]
    (exp_marker,) = [e for e in expected if isinstance(e, MarkerEvent)]
    assert (marker.t, marker.data.label, marker.data.origin) == (exp_marker.t, "stuck", "speech")
    assert marker.t == 111.02  # the word "I'm", not the segment start (110.6)


def test_offset_and_clamping() -> None:
    seg = Segment(
        1.0,
        3.0,
        "Wait, I'm stuck.",
        [WordTiming("Wait,", 1.0, 1.3), WordTiming(" I'm", 1.4, 1.6)],
        -0.1,
    )
    late = Segment(9.0, 12.0, "Done here.", [], None)
    events = build_events([seg, late], offset_s=0.5, end_t=10.0)
    speech = [e for e in events if isinstance(e, SpeechEvent)]
    assert (speech[0].t, speech[0].data.end) == (1.5, 3.5)
    assert speech[0].data.cues == ["wait"]
    assert speech[1].data.end == 10.0  # clamped to the session end
    marker = next(e for e in events if isinstance(e, MarkerEvent))
    assert marker.t == 1.9


def test_no_audio_means_no_transcript(bundle_copy: Callable[[str], SessionPaths]) -> None:
    paths = bundle_copy("two_sum_live_order")
    ingest.run(paths)
    assert transcribe.run(paths, RecordedTranscriber([])) == "skipped: no audio"
    assert not paths.d("transcript.jsonl").exists()


def test_no_transcriber_keeps_existing_transcript(
    bundle_copy: Callable[[str], SessionPaths],
) -> None:
    paths = bundle_copy("two_sum_basic")
    before = paths.d("transcript.jsonl").read_text()
    ingest.run(paths)
    msg = transcribe.run(paths, None)
    assert msg == "skipped: no transcriber (kept the existing transcript)"
    assert paths.d("transcript.jsonl").read_text() == before


@pytest.mark.whisper
@pytest.mark.skipif(
    os.environ.get("IC_WHISPER") != "1", reason="set IC_WHISPER=1 (needs the model)"
)
def test_real_whisper_on_silence_yields_nothing(bundle_copy: Callable[[str], SessionPaths]) -> None:
    from engine.transcribe import FasterWhisperTranscriber

    paths = bundle_copy("two_sum_basic")
    ingest.run(paths)
    msg = transcribe.run(paths, FasterWhisperTranscriber())
    assert msg.startswith("0 speech segments"), msg

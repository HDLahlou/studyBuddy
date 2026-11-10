"""Transcribe stage: faster-whisper on derived/audio.webm -> speech and marker events.

- Word timestamps on; the VAD filter on, so silence yields no (hallucinated) text.
- The audio is decoded from the joined stream (PyAV), never from the WebM header, which
  MediaRecorder leaves without a duration (decisions 002, carry-over 5).
- Times are shifted by manifest media.audio.offset_s onto the session clock and clamped to it.
- confidence = exp(avg_logprob) per segment; t_uncertainty 0.2 s.
- Cue phrases become `cues`; marker phrases become `marker` events (engine.cues).

The model is pluggable (Transcriber protocol): tests use RecordedTranscriber, never a live model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast

from engine.cues import find_cues, find_markers, normalize_words
from engine.files import write_events
from engine.paths import SessionPaths
from ic_schema.bundle import read_bundle
from ic_schema.events import Event, MarkerData, MarkerEvent, SpeechData, SpeechEvent, Word

T_UNCERTAINTY_S = 0.2
DEFAULT_MODEL = "small.en"


@dataclass(frozen=True)
class WordTiming:
    word: str
    start: float
    end: float
    probability: float | None = None


@dataclass(frozen=True)
class Segment:
    """One transcript segment, times in seconds from the start of the audio file."""

    start: float
    end: float
    text: str
    words: list[WordTiming] = field(default_factory=list)
    avg_logprob: float | None = None


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio: Path) -> list[Segment]: ...


class TranscriberUnavailable(RuntimeError):
    pass


class RecordedTranscriber:
    """Returns fixed segments (tests and replays; never calls a model)."""

    name = "recorded"

    def __init__(self, segments: list[Segment]) -> None:
        self.segments = segments

    def transcribe(self, audio: Path) -> list[Segment]:
        return list(self.segments)


class FasterWhisperTranscriber:
    def __init__(
        self, model: str = DEFAULT_MODEL, device: str = "auto", compute_type: str = "int8"
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise TranscriberUnavailable(
                "faster-whisper is not installed: "
                "run `uv sync --package ic-engine --extra transcribe`"
            ) from e
        self.name = f"faster-whisper:{model}"
        self._model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, audio: Path) -> list[Segment]:
        segments, _info = self._model.transcribe(
            str(audio),
            language="en",
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=5,
        )
        out: list[Segment] = []
        for s in segments:
            words = [
                WordTiming(w.word, float(w.start), float(w.end), float(w.probability))
                for w in (s.words or [])
            ]
            out.append(
                Segment(float(s.start), float(s.end), s.text.strip(), words, float(s.avg_logprob))
            )
        return out


def _confidence(seg: Segment) -> float:
    if seg.avg_logprob is None:
        return (
            1.0
            if not seg.words
            else min(1.0, sum(w.probability or 1.0 for w in seg.words) / len(seg.words))
        )
    return max(0.0, min(1.0, math.exp(seg.avg_logprob)))


def _word_start_for(seg: Segment, word_index: int) -> tuple[float, float | None]:
    """Start time (audio clock) and probability of the whisper word holding normalized word i."""
    seen = 0
    for w in seg.words:
        n = len(normalize_words(w.word))
        if word_index < seen + n:
            return w.start, w.probability
        seen += n
    return seg.start, None


def build_events(segments: list[Segment], offset_s: float, end_t: float) -> list[Event]:
    def clock(x: float) -> float:
        return round(min(max(0.0, x + offset_s), end_t), 3)

    events: list[Event] = []
    n_speech = n_marker = 0
    for seg in segments:
        if not seg.text.strip():
            continue
        start, end = clock(seg.start), clock(seg.end)
        if end <= start:
            continue
        conf = _confidence(seg)
        n_speech += 1
        words = [
            Word(w=w.word.strip(), start=clock(w.start), end=clock(w.end), p=w.probability)
            for w in seg.words
            if w.word.strip()
        ]
        events.append(
            SpeechEvent(
                id=f"sp_{n_speech}",
                t=start,
                source="whisper",
                confidence=round(conf, 3),
                t_uncertainty=T_UNCERTAINTY_S,
                kind="speech",
                data=SpeechData(
                    text=seg.text.strip(), end=end, words=words or None, cues=find_cues(seg.text)
                ),
            )
        )
        for label, phrase, idx in find_markers(seg.text):
            at, p = _word_start_for(seg, idx)
            n_marker += 1
            events.append(
                MarkerEvent(
                    id=f"mk_{n_marker}",
                    t=clock(at),
                    source="whisper",
                    confidence=round(p if p is not None else conf, 3),
                    t_uncertainty=T_UNCERTAINTY_S,
                    kind="marker",
                    data=MarkerData(
                        label=cast(Literal["stuck", "idea", "done"], label),
                        origin="speech",
                        text=phrase,
                    ),
                )
            )
    return sorted(events, key=lambda e: (e.t, e.id))


def run(paths: SessionPaths, transcriber: Transcriber | None) -> str:
    """Write derived/transcript.jsonl. Returns a one-line status message.

    Without audio there is no transcript (a stale one is removed). Without a transcriber an
    existing transcript is kept, never wiped, so `--no-transcribe` re-runs are safe.
    """
    b = read_bundle(paths.root)
    out = paths.d("transcript.jsonl")
    if not paths.audio.exists():
        out.unlink(missing_ok=True)
        return "skipped: no audio"
    if transcriber is None:
        kept = "kept the existing transcript" if out.exists() else "no transcript"
        return f"skipped: no transcriber ({kept})"
    audio = b.manifest.media.audio
    offset = audio.offset_s if audio and audio.offset_s is not None else 0.0
    end_t = max(e.t for e in b.events)
    events = build_events(transcriber.transcribe(paths.audio), offset, end_t)
    write_events(out, events)
    speech = sum(e.kind == "speech" for e in events)
    return f"{speech} speech segments, {len(events) - speech} markers ({transcriber.name})"

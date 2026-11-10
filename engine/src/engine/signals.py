"""Derive-signals stage (design pipeline step 4; decisions 003 E3, E4).

- idle: gaps over 45 s with no activity. Activity is a code change (code_diff), speech, a paste
  or undo, a run/submit click, or a result: waiting on the judge is not idle. The leading gap
  before the first activity is reading, not idle. Idle spans are also written as `idle` events.
- typing: keystroke bursts less than 5 s apart, merged into spans (no new keystroke events).
- churn windows: deleted/added lines over a sliding 2-minute window (30 s step).
- fail streaks: 2+ consecutive failed results (unknown results neither count nor break).
- focus away: tab/window away->back spans; editor focus changes are ignored as noise.
- pauses: gaps over 10 s between speech segments.
"""

from __future__ import annotations

from typing import Literal

from engine.files import write_events, write_model
from engine.models import ChurnWindow, FailStreak, FocusAway, Signals, Span, TypingSpan
from engine.paths import SessionPaths
from ic_schema.bundle import read_bundle
from ic_schema.events import (
    CodeDiffEvent,
    Event,
    FocusChangeEvent,
    IdleData,
    IdleEvent,
    KeystrokeEvent,
    RunResultEvent,
    SpeechEvent,
    SubmitResultEvent,
)

IDLE_THRESHOLD_S = 45.0
TYPING_MERGE_GAP_S = 5.0
CHURN_WINDOW_S = 120.0
CHURN_STEP_S = 30.0
CHURN_HIGH_RATIO = 0.5
CHURN_HIGH_MIN_DELETED = 5
FAIL_STREAK_MIN = 2
PAUSE_THRESHOLD_S = 10.0

OWN_OUTPUTS = {"idle.jsonl"}

ACTIVITY_KINDS = {"code_diff", "paste", "undo", "run", "submit", "run_result", "submit_result"}


def session_end_t(events: list[Event]) -> float:
    ends = [e.t for e in events if e.kind == "session_end"]
    return ends[0] if ends else max((e.t for e in events), default=0.0)


def activity_intervals(events: list[Event]) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    for e in events:
        if isinstance(e, SpeechEvent):
            out.append((e.t, e.data.end, e.id))
        elif e.kind in ACTIVITY_KINDS:
            out.append((e.t, e.t, e.id))
    return sorted(out)


def idle_gaps(events: list[Event], end_t: float) -> tuple[list[Span], float]:
    """All gaps between activity (and to the session end), excluding the leading reading gap."""
    acts = activity_intervals(events)
    gaps: list[Span] = []
    if not acts:
        return gaps, 0.0
    cursor_end, cursor_id = acts[0][1], acts[0][2]
    for start, end, eid in acts[1:]:
        if start > cursor_end:
            gaps.append(Span(start=cursor_end, end=start, evidence=[cursor_id, eid]))
        if end >= cursor_end:
            cursor_end, cursor_id = end, eid
    if end_t > cursor_end:
        gaps.append(Span(start=cursor_end, end=end_t, evidence=[cursor_id]))
    longest = max((g.end - g.start for g in gaps), default=0.0)
    return gaps, round(longest, 3)


def typing_spans(events: list[Event]) -> list[TypingSpan]:
    spans: list[TypingSpan] = []
    for e in events:
        if not isinstance(e, KeystrokeEvent):
            continue
        end = e.t + e.data.duration_s
        keys = sum(v or 0 for v in e.data.counts.model_dump().values())
        last = spans[-1] if spans else None
        if last and e.t - last.end < TYPING_MERGE_GAP_S:
            last.end = round(max(last.end, end), 3)
            last.bursts += 1
            last.keys += keys
            last.evidence.append(e.id)
        else:
            spans.append(
                TypingSpan(start=e.t, end=round(end, 3), bursts=1, keys=keys, evidence=[e.id])
            )
    return spans


def churn(added: int, deleted: int) -> float:
    return round(deleted / max(added, 1), 3)


def churn_windows(events: list[Event], end_t: float) -> list[ChurnWindow]:
    diffs = [e for e in events if isinstance(e, CodeDiffEvent)]
    windows: list[ChurnWindow] = []
    start = 0.0
    while start < max(end_t, CHURN_STEP_S):
        end = start + CHURN_WINDOW_S
        inside = [d for d in diffs if start <= d.t < end]
        added = sum(d.data.added_lines for d in inside)
        deleted = sum(d.data.deleted_lines for d in inside)
        if added or deleted:
            c = churn(added, deleted)
            windows.append(
                ChurnWindow(
                    start=start,
                    end=min(end, end_t),
                    added=added,
                    deleted=deleted,
                    churn=c,
                    high=deleted >= CHURN_HIGH_MIN_DELETED and c >= CHURN_HIGH_RATIO,
                )
            )
        start += CHURN_STEP_S
    return windows


def fail_streaks(events: list[Event]) -> list[FailStreak]:
    streaks: list[FailStreak] = []
    current: list[Event] = []

    def close() -> None:
        if len(current) >= FAIL_STREAK_MIN:
            streaks.append(
                FailStreak(
                    start=current[0].t,
                    end=current[-1].t,
                    count=len(current),
                    evidence=[e.id for e in current],
                )
            )
        current.clear()

    for e in events:
        if not isinstance(e, RunResultEvent | SubmitResultEvent) or e.data.verdict == "unknown":
            continue
        if e.data.verdict == "accepted":
            close()
        else:
            current.append(e)
    close()
    return streaks


def focus_away(events: list[Event], end_t: float) -> list[FocusAway]:
    spans: list[FocusAway] = []
    open_: dict[Literal["tab", "window"], FocusChangeEvent] = {}
    for e in events:
        if not isinstance(e, FocusChangeEvent):
            continue
        if e.data.target == "editor":
            continue
        target: Literal["tab", "window"] = e.data.target
        if e.data.state == "away":
            open_.setdefault(target, e)
        elif target in open_:
            start = open_.pop(target)
            spans.append(
                FocusAway(start=start.t, end=e.t, target=target, evidence=[start.id, e.id])
            )
    for still_away, start in open_.items():
        spans.append(FocusAway(start=start.t, end=end_t, target=still_away, evidence=[start.id]))
    return sorted(spans, key=lambda s: s.start)


def pauses(events: list[Event]) -> list[Span]:
    speech = [e for e in events if isinstance(e, SpeechEvent)]
    out: list[Span] = []
    for a, b in zip(speech, speech[1:], strict=False):
        if b.t - a.data.end > PAUSE_THRESHOLD_S:
            out.append(Span(start=a.data.end, end=b.t, evidence=[a.id, b.id]))
    return out


def run(paths: SessionPaths) -> Signals:
    b = read_bundle(paths.root)
    derived = [n for n in b.derived_event_files() if n not in OWN_OUTPUTS]
    events = b.timeline(derived=derived)
    end_t = session_end_t(events)

    gaps, longest = idle_gaps(events, end_t)
    idle = [g for g in gaps if g.end - g.start > IDLE_THRESHOLD_S]
    write_events(
        paths.d("idle.jsonl"),
        [
            IdleEvent(
                id=f"id_{i}",
                t=g.start,
                source="engine",
                kind="idle",
                data=IdleData(end=g.end, duration_s=round(g.end - g.start, 3)),
            )
            for i, g in enumerate(idle, 1)
        ],
    )
    signals = Signals(
        idle_threshold_s=IDLE_THRESHOLD_S,
        idle=idle,
        typing=typing_spans(events),
        churn_windows=churn_windows(events, end_t),
        fail_streaks=fail_streaks(events),
        focus_away=focus_away(events, end_t),
        pauses=pauses(events),
        longest_gap_s=longest,
    )
    write_model(paths.d("signals.json"), signals)
    return signals

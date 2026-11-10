"""Segment-phases stage: rule-based read -> plan -> code -> debug -> test -> submit (003 E2).

A state machine over the timeline (Bundle.timeline: ordered by t, never seq). Phases may recur
(a failed submit returns to debug). The AI refines boundaries later (design step 5).

- read starts at 0.
- plan starts at the first substantive speech segment that is not reading the problem aloud
  (content-word overlap with title/statement/examples/constraints below 0.5). Without a
  statement, the first substantive speech segment. Without speech, there is no plan phase.
- code starts at the first edit: a keystroke burst that inserts/deletes, a paste, or a
  run/submit click. A code change counts only when keystrokes weren't captured, and never
  when it comes from a language switch (the platform swaps in a new template).
- A failed run or submit result (any known non-accepted verdict) moves to debug; an accepted
  run moves code/debug to test; a submit click moves to submit; an accepted submit closes the
  timeline. Unknown results (failed scrapes) change nothing.
- Time after the accepted submit is a tail, excluded from time per phase.
"""

from __future__ import annotations

from engine.cues import normalize_words
from engine.files import read_model, write_model
from engine.models import NormalizeReport, Phases, PhaseSegment, SegmentSignals, Signals, Span
from engine.paths import SessionPaths
from engine.signals import churn, session_end_t
from ic_schema.bundle import read_bundle
from ic_schema.events import (
    CodeDiffEvent,
    CodeSnapshotEvent,
    Event,
    KeystrokeEvent,
    ProblemLoadedEvent,
    RunResultEvent,
    SpeechEvent,
    SubmitResultEvent,
)
from ic_schema.report import Phase

READING_OVERLAP = 0.5
MIN_CONTENT_WORDS = 3

STOPWORDS = frozenset(
    [
        "the",
        "and",
        "that",
        "this",
        "with",
        "for",
        "are",
        "you",
        "can",
        "from",
        "have",
        "has",
        "not",
        "but",
        "its",
        "it's",
        "was",
        "were",
        "will",
        "would",
        "what",
        "which",
        "when",
        "then",
        "than",
        "there",
        "their",
        "them",
        "they",
        "just",
        "like",
        "okay",
        "so",
        "let's",
        "lets",
        "let",
        "me",
        "ill",
        "i'll",
        "i'm",
        "im",
        "we",
        "our",
        "your",
        "all",
        "any",
        "one",
        "also",
        "into",
        "out",
        "about",
        "been",
        "being",
        "does",
        "did",
        "how",
        "why",
        "who",
    ]
)


def content_words(text: str) -> set[str]:
    return {
        w for w in normalize_words(text) if len(w) > 2 and w not in STOPWORDS and not w.isdigit()
    }


def problem_corpus(events: list[Event]) -> set[str] | None:
    problems = [e for e in events if isinstance(e, ProblemLoadedEvent)]
    if not problems:
        return None
    p = problems[-1].data  # the most complete one is the latest (design open question)
    if not p.statement:
        return None
    parts = [p.title, p.statement, *p.constraints]
    for ex in p.examples:
        parts += [ex.input, ex.output, ex.explanation or ""]
    return content_words(" ".join(parts))


def is_reading(text: str, corpus: set[str]) -> bool:
    words = content_words(text)
    return bool(words) and len(words & corpus) / len(words) >= READING_OVERLAP


def language_switches(events: list[Event], default_language: str) -> set[str]:
    """Ids of code_diff events whose two snapshots are in different languages: switching
    language replaces the editor template, which is not the user editing."""
    lang = {
        e.id: e.data.language or default_language
        for e in events
        if isinstance(e, CodeSnapshotEvent)
    }
    return {
        e.id
        for e in events
        if isinstance(e, CodeDiffEvent)
        and lang.get(e.data.from_id, default_language) != lang.get(e.data.to_id, default_language)
    }


def first_edit_t(
    events: list[Event], *, keystrokes_captured: bool = True, default_language: str = ""
) -> float | None:
    """The first thing the user did to the code: an inserting/deleting keystroke burst, a
    paste, or a run/submit click. Code changes count only when keystrokes weren't captured,
    and never when they come from a language switch (which swaps the template)."""
    switches = language_switches(events, default_language)
    for e in events:
        if isinstance(e, KeystrokeEvent):
            c = e.data.counts
            if (c.insert or 0) + (c.delete or 0) + (c.newline or 0) > 0:
                return e.t
        elif (
            e.kind in ("paste", "run", "submit")
            or isinstance(e, CodeDiffEvent)
            and not keystrokes_captured
            and e.id not in switches
        ):
            return e.t
    return None


def plan_start_t(
    events: list[Event], corpus: set[str] | None, before: float | None
) -> float | None:
    for e in events:
        if before is not None and e.t >= before:
            return None
        if not isinstance(e, SpeechEvent) or len(content_words(e.data.text)) < MIN_CONTENT_WORDS:
            continue
        if corpus is None or not is_reading(e.data.text, corpus):
            return e.t
    return None


def boundaries(
    events: list[Event], *, keystrokes_captured: bool = True, default_language: str = ""
) -> tuple[list[tuple[Phase, float]], float | None, list[str]]:
    """(phase, start) changes, the accepted-submit time, and which rule variants applied."""
    rules: list[str] = []
    corpus = problem_corpus(events)
    has_speech = any(isinstance(e, SpeechEvent) for e in events)
    rules.append(
        "statement overlap splits read/plan" if corpus else "no statement: plan at first speech"
    )
    if not has_speech:
        rules.append("no speech: no plan phase")

    edit = first_edit_t(
        events, keystrokes_captured=keystrokes_captured, default_language=default_language
    )
    plan = plan_start_t(events, corpus, edit)
    changes: list[tuple[Phase, float]] = [("read", 0.0)]
    if plan is not None:
        changes.append(("plan", plan))
    if edit is None:
        rules.append("no edit: read/plan only")
        return changes, None, rules
    changes.append(("code", edit))

    def switch(phase: Phase, t: float) -> None:
        if changes[-1][0] != phase:
            changes.append((phase, t))

    accepted: float | None = None
    for e in events:
        if e.t < edit:
            continue
        if isinstance(e, RunResultEvent):
            v = e.data.verdict
            if v == "unknown":
                continue
            if v == "accepted":
                if changes[-1][0] in ("code", "debug"):
                    switch("test", e.t)
            else:
                switch("debug", e.t)
        elif e.kind == "submit":
            switch("submit", e.t)
        elif isinstance(e, SubmitResultEvent):
            v = e.data.verdict
            if v == "unknown":
                continue
            if v == "accepted":
                accepted = e.t
                break
            switch("debug", e.t)
    return changes, accepted, rules


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def run(paths: SessionPaths) -> Phases:
    b = read_bundle(paths.root)
    events = b.timeline()
    end_t = session_end_t(events)
    redundant = set(read_model(paths.d("normalize.json"), NormalizeReport).redundant_snapshots)
    idle = read_model(paths.d("signals.json"), Signals).idle
    listed = [e for e in events if e.id not in redundant]

    caps = b.manifest.capabilities
    changes, accepted, rules = boundaries(
        events, keystrokes_captured=caps.keystrokes != "none", default_language=caps.language
    )
    close = accepted if accepted is not None else end_t
    segments: list[PhaseSegment] = []
    for i, (phase, start) in enumerate(changes):
        end = changes[i + 1][1] if i + 1 < len(changes) else close
        if end <= start:
            continue
        last = i + 1 == len(changes)
        inside = [e for e in listed if start <= e.t < end or (last and e.t == end)]
        diffs = [e for e in inside if isinstance(e, CodeDiffEvent)]
        added = sum(d.data.added_lines for d in diffs)
        deleted = sum(d.data.deleted_lines for d in diffs)
        segments.append(
            PhaseSegment(
                phase=phase,
                start=start,
                end=end,
                events=[e.id for e in inside],
                signals=SegmentSignals(
                    runs=sum(e.kind == "run" for e in inside),
                    fails=sum(
                        isinstance(e, RunResultEvent | SubmitResultEvent)
                        and e.data.verdict not in ("accepted", "unknown")
                        for e in inside
                    ),
                    churn=churn(added, deleted) if diffs else None,
                    longest_idle=round(
                        max((_overlap(start, end, s.start, s.end) for s in idle), default=0.0), 3
                    ),
                ),
            )
        )
    tail = None
    if accepted is not None and end_t > accepted:
        tail = Span(
            start=accepted, end=end_t, evidence=[e.id for e in listed if accepted < e.t <= end_t]
        )
    phases = Phases(segments=segments, tail=tail, rules=rules)
    write_model(paths.d("phases.json"), phases)
    return phases

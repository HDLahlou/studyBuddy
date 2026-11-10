"""Signals, phases, metrics and timeline on the fixtures. Expected values are worked out by
hand from fixtures/two_sum_basic (see fixtures/README.md for the session story)."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from engine import pipeline
from engine.files import read_events, read_model
from engine.models import Phases, SessionFacts, Signals, Timeline
from engine.paths import SessionPaths
from engine.signals import idle_gaps
from engine.transcribe import RecordedTranscriber
from ic_schema.events import IdleEvent, RunEvent, SessionEndEvent, SpeechEvent
from ic_schema.report import Metrics

Copy = Callable[[str], SessionPaths]


def process(paths: SessionPaths, transcriber: RecordedTranscriber | None = None) -> None:
    pipeline.run(paths, pipeline.Options(transcriber=transcriber))


def segments(paths: SessionPaths) -> list[tuple[str, float, float]]:
    return [(s.phase, s.start, s.end) for s in read_model(paths.d("phases.json"), Phases).segments]


# --- signals ----------------------------------------------------------------------------------


def test_basic_signals(bundle_copy: Copy, recorded: RecordedTranscriber) -> None:
    paths = bundle_copy("two_sum_basic")
    process(paths, recorded)
    s = read_model(paths.d("signals.json"), Signals)
    assert s.idle == [] and read_events(paths.d("idle.jsonl")) == []
    assert s.longest_gap_s == pytest.approx(18.4)  # sp_4 ends 92.2, sp_5 starts 110.6
    assert [(f.target, f.start, f.end) for f in s.focus_away] == [("tab", 97.0, 109.5)]
    assert [(p.start, p.end) for p in s.pauses] == [(39.6, 85.4), (92.2, 110.6), (129.8, 144.5)]
    assert [(t.start, t.end, t.bursts) for t in s.typing] == [
        (41.8, 75.2, 4),
        (112.4, 115.5, 1),
        (131.0, 137.7, 2),
    ]
    assert s.fail_streaks == []
    assert s.churn_windows and all(w.added + w.deleted > 0 for w in s.churn_windows)


def test_idle_gaps_skip_the_reading_gap_and_count_waiting_as_activity() -> None:
    def run(t: float, seq: int) -> RunEvent:
        return RunEvent(id=f"ev_{seq}", t=t, seq=seq, source="extension", kind="run")

    speech = SpeechEvent(
        id="sp_1", t=100.0, source="whisper", kind="speech", data={"text": "hm", "end": 110.0}
    )
    end = SessionEndEvent(
        id="ev_9",
        t=300.0,
        seq=9,
        source="extension",
        kind="session_end",
        data={"reason": "user_stop"},
    )
    gaps, longest = idle_gaps([run(60.0, 1), speech, run(170.0, 2), end], 300.0)
    # 0-60 is reading (not a gap); 60-100, 110-170, then 170-300 to the session end.
    assert [(g.start, g.end) for g in gaps] == [(60.0, 100.0), (110.0, 170.0), (170.0, 300.0)]
    assert longest == 130.0


def test_idle_events_written_and_rerunnable(bundle_copy: Copy) -> None:
    paths = bundle_copy("two_sum_seq_gap")
    process(paths)
    # seq 18-20 are missing and there is no audio: nothing happens between the failed run
    # result (84.62) and the undo (133.4). The snapshot at 134.0 repeats the buggy code.
    idle = [e for e in read_events(paths.d("idle.jsonl")) if isinstance(e, IdleEvent)]
    assert [(e.id, e.t, e.data.end) for e in idle] == [("id_1", 84.62, 133.4)]
    assert idle[0].data.duration_s == pytest.approx(48.78)
    first = paths.d("idle.jsonl").read_text()
    pipeline.run(paths, only="signals")
    assert paths.d("idle.jsonl").read_text() == first  # its own output is not re-read as input
    debug = next(
        seg for seg in read_model(paths.d("phases.json"), Phases).segments if seg.phase == "debug"
    )
    assert debug.signals.longest_idle == pytest.approx(48.78)
    assert "id_1" in debug.events


# --- phases -----------------------------------------------------------------------------------

BASIC_PHASES = [
    ("read", 0.0, 17.5),  # sp_1 reads the statement aloud; sp_2 starts planning
    ("plan", 17.5, 41.8),  # first edit: keystroke burst at 41.8
    ("code", 41.8, 84.62),  # first failed run result
    ("debug", 84.62, 152.71),  # accepted run
    ("test", 152.71, 168.0),  # submit click
    ("submit", 168.0, 171.93),  # accepted submit closes the timeline
]


def test_basic_phases(bundle_copy: Copy, recorded: RecordedTranscriber) -> None:
    paths = bundle_copy("two_sum_basic")
    process(paths, recorded)
    assert segments(paths) == BASIC_PHASES
    phases = read_model(paths.d("phases.json"), Phases)
    assert phases.tail is not None and (phases.tail.start, phases.tail.end) == (171.93, 176.2)
    assert "statement overlap splits read/plan" in phases.rules
    debug = next(s for s in phases.segments if s.phase == "debug")
    # The failed result that opens debug (84.62) is inside it, as is the rerun at 150.
    assert (debug.signals.runs, debug.signals.fails) == (1, 1)
    assert "mk_1" in debug.events and "ev_15" in debug.events and "ev_27" not in debug.events


def test_live_order_phases_match_basic(bundle_copy: Copy) -> None:
    a, b = bundle_copy("two_sum_basic"), bundle_copy("two_sum_live_order")
    # Same captures, different seq order; without a transcript there is no plan phase.
    a.d("transcript.jsonl").unlink()
    process(a)
    process(b)
    assert segments(a) == segments(b)
    assert segments(b)[0] == ("read", 0.0, 41.8)


def test_failed_scrape_does_not_start_debugging(bundle_copy: Copy) -> None:
    paths = bundle_copy("two_sum_failed_scrape")
    process(paths)
    assert segments(paths) == [
        ("read", 0.0, 41.8),
        ("code", 41.8, 152.71),  # the unknown result at 112.0 changes nothing
        ("test", 152.71, 168.0),
        ("submit", 168.0, 171.93),
    ]
    facts = read_model(paths.d("facts.json"), SessionFacts)
    assert (facts.unknown_results, facts.failed_runs) == (1, 0)


def test_seq_gap_still_segments(bundle_copy: Copy) -> None:
    paths = bundle_copy("two_sum_seq_gap")
    process(paths)
    assert [p for p, _, _ in segments(paths)] == ["read", "code", "debug", "test", "submit"]
    assert read_model(paths.d("facts.json"), SessionFacts).complete is False


def test_without_statement_plan_starts_at_first_speech(
    bundle_copy: Copy, recorded: RecordedTranscriber
) -> None:
    paths = bundle_copy("two_sum_basic")
    lines = (paths.root / "events.jsonl").read_text().splitlines()
    problem = json.loads(lines[1])
    problem["data"].update(statement=None, examples=[], constraints=[])
    lines[1] = json.dumps(problem)
    (paths.root / "events.jsonl").write_text("\n".join(lines) + "\n")
    process(paths, recorded)
    assert segments(paths)[:2] == [("read", 0.0, 3.1), ("plan", 3.1, 41.8)]
    assert "no statement: plan at first speech" in read_model(paths.d("phases.json"), Phases).rules


def test_failed_submit_returns_to_debug(bundle_copy: Copy) -> None:
    paths = bundle_copy("two_sum_live_order")
    lines = [json.loads(ln) for ln in (paths.root / "events.jsonl").read_text().splitlines()]
    first_run_result = next(
        e for e in lines if e["kind"] == "run_result" and e["data"]["verdict"] == "accepted"
    )
    submit_result = next(e for e in lines if e["kind"] == "submit_result")
    # Make the only submit fail: debug again after it, and no accepted submit means no tail.
    submit_result["data"].update(verdict="wrong_answer", verdict_raw="Wrong Answer")
    (paths.root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in lines))
    process(paths)
    phases = [p for p, _, _ in segments(paths)]
    assert phases == ["read", "code", "debug", "test", "submit", "debug"]
    assert read_model(paths.d("phases.json"), Phases).tail is None
    assert first_run_result["t"] == 152.71


# --- metrics and timeline ---------------------------------------------------------------------


def test_basic_metrics(bundle_copy: Copy, recorded: RecordedTranscriber) -> None:
    paths = bundle_copy("two_sum_basic")
    process(paths, recorded)
    m = read_model(paths.d("metrics.json"), Metrics)
    assert m.total_time_s == 176.2
    assert m.time_per_phase_s == {
        "read": 17.5,
        "plan": 24.3,
        "code": 42.82,
        "debug": 68.09,
        "test": 15.29,
        "submit": 3.93,
    }
    assert (m.time_to_first_run_s, m.time_to_first_passing_run_s, m.runs_before_accept) == (
        82.0,
        152.71,
        2,
    )
    assert m.longest_idle_s == pytest.approx(18.4)
    assert m.talk_ratio == pytest.approx(66.2 / 176.2, abs=1e-3)  # nine segments, 66.2 s of speech
    assert m.churn is not None and 0 < m.churn < 1

    f = read_model(paths.d("facts.json"), SessionFacts)
    assert (f.title, f.slug, f.difficulty, f.platform, f.mode) == (
        "Two Sum",
        "two-sum",
        "easy",
        "leetcode",
        "practice",
    )
    assert (f.session_language, f.solution_language) == ("python3", "python3")
    assert (f.accepted, f.final_verdict, f.runs, f.failed_runs, f.submits) == (
        True,
        "accepted",
        2,
        1,
        1,
    )
    assert f.has_statement and f.has_audio and f.complete


def test_talk_ratio_unknown_without_transcript(bundle_copy: Copy) -> None:
    paths = bundle_copy("two_sum_basic")
    paths.d("transcript.jsonl").unlink()
    process(paths)  # audio, but no transcriber and no transcript
    assert read_model(paths.d("metrics.json"), Metrics).talk_ratio is None


def test_timeline_bundles_facts_metrics_segments(
    bundle_copy: Copy, recorded: RecordedTranscriber
) -> None:
    paths = bundle_copy("two_sum_basic")
    process(paths, recorded)
    tl = read_model(paths.d("timeline.json"), Timeline)
    assert [(s.phase, s.start, s.end) for s in tl.segments] == BASIC_PHASES
    assert tl.metrics == read_model(paths.d("metrics.json"), Metrics)
    assert tl.facts.session_id == "fx_two_sum_basic"
    # Every listed event id resolves (evidence integrity), and each appears in one segment only.
    from ic_schema.bundle import read_bundle

    ids = {e.id for e in read_bundle(paths.root).timeline()}
    listed = [i for s in tl.segments for i in s.events] + (tl.tail.evidence if tl.tail else [])
    assert set(listed) <= ids and len(listed) == len(set(listed))


def test_language_switch_is_not_the_first_edit() -> None:
    """The real Valid Parentheses session: switching C++ -> Java at 7.3 s swapped the template
    (a code change) before the first keystroke at 11.5 s."""
    from engine.phases import first_edit_t
    from ic_schema.events import CodeDiffEvent, CodeSnapshotEvent, KeystrokeEvent

    def snap(seq: int, t: float, code: str, lang: str | None) -> CodeSnapshotEvent:
        data = {"code": code, "reason": "debounce", **({"language": lang} if lang else {})}
        return CodeSnapshotEvent(
            id=f"ev_{seq}", t=t, seq=seq, source="extension", kind="code_snapshot", data=data
        )

    cpp, java = snap(1, 0.4, "class Solution {};", "cpp"), snap(2, 7.3, "class Solution {}", None)
    switch = CodeDiffEvent(
        id="df_1",
        t=7.3,
        source="engine",
        kind="code_diff",
        data={
            "from_id": "ev_1",
            "to_id": "ev_2",
            "added_lines": 1,
            "deleted_lines": 1,
            "unified_diff": "",
        },
    )
    key = KeystrokeEvent(
        id="ev_3",
        t=11.5,
        seq=3,
        source="extension",
        kind="keystroke",
        data={"duration_s": 0.2, "counts": {"newline": 1}},
    )
    events = [cpp, java, switch, key]
    assert first_edit_t(events, default_language="java") == 11.5
    # Without keystroke capture a code change counts, but still not the language switch.
    assert first_edit_t(events, keystrokes_captured=False, default_language="java") == 11.5
    assert (
        first_edit_t([cpp, java, switch], keystrokes_captured=False, default_language="java")
        is None
    )

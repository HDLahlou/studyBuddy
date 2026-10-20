"""One populated instance of every contract model, for round-trip and schema tests."""

from __future__ import annotations

from typing import Any

from ic_schema import events as ev
from ic_schema import protocol as pr
from ic_schema import report as rp
from ic_schema.manifest import EndInfo, UserInputs

from .helpers import make_capabilities, make_manifest


def x(seq: int, t: float, **kw: Any) -> dict[str, Any]:
    """Envelope for an extension event."""
    return {"id": f"ev_{seq}", "t": t, "seq": seq, "source": "extension", **kw}


RESULT = {
    "verdict": "wrong_answer",
    "verdict_raw": "Wrong Answer",
    "passed_cases": 1,
    "total_cases": 3,
    "failing_input": "nums = [3,2,4]\ntarget = 6",
    "expected_output": "[1,2]",
    "actual_output": "[0,0]",
    "stdout": "",
    "error_message": None,
    "runtime_ms": 0.0,
    "memory_mb": 16.4,
}

EVENTS: list[ev.Event] = [
    ev.SessionStartEvent(**x(1, 0.0, kind="session_start", data={"url": "https://leetcode.com/"})),
    ev.ProblemLoadedEvent(
        **x(
            2,
            0.4,
            kind="problem_loaded",
            data=ev.ProblemLoadedData(
                platform="leetcode",
                slug="two-sum",
                url="https://leetcode.com/problems/two-sum/",
                title="Two Sum",
                difficulty="easy",
                statement="Find two indices.",
                examples=[ev.Example(input="[2,7], 9", output="[0,1]", explanation="2 + 7")],
                constraints=["2 <= n"],
            ),
        )
    ),
    ev.CodeSnapshotEvent(
        **x(
            3,
            1.0,
            kind="code_snapshot",
            data={"code": "x = 1\n", "language": "python3", "reason": "initial"},
        )
    ),
    ev.CodeDiffEvent(
        id="df_1",
        t=1.0,
        source="engine",
        kind="code_diff",
        data=ev.CodeDiffData(
            from_id="ev_3", to_id="ev_5", added_lines=2, deleted_lines=1, unified_diff="@@"
        ),
    ),
    ev.KeystrokeEvent(
        **x(
            4,
            2.0,
            kind="keystroke",
            data=ev.KeystrokeData(
                duration_s=3.5,
                counts=ev.KeyCounts(insert=10, delete=2, newline=1, navigation=4, shortcut=1),
            ),
        )
    ),
    ev.PasteEvent(**x(5, 3.0, kind="paste", data={"chars": 28, "lines": 1})),
    ev.UndoEvent(**x(6, 4.0, kind="undo", data={"count": 2})),
    ev.RunEvent(**x(7, 5.0, kind="run", data={"trigger": "click"})),
    ev.RunResultEvent(
        **x(8, 7.0, kind="run_result", t_uncertainty=0.3, data={**RESULT, "run_id": "ev_7"})
    ),
    ev.SubmitEvent(**x(9, 8.0, kind="submit", data={"trigger": "shortcut"})),
    ev.SubmitResultEvent(
        **x(
            10,
            9.5,
            kind="submit_result",
            data={**RESULT, "verdict": "accepted", "submit_id": "ev_9"},
        )
    ),
    ev.FocusChangeEvent(
        **x(11, 10.0, kind="focus_change", data={"target": "tab", "state": "away"})
    ),
    ev.SpeechEvent(
        id="sp_1",
        t=11.0,
        source="whisper",
        confidence=0.9,
        t_uncertainty=0.2,
        kind="speech",
        data=ev.SpeechData(
            text="I'm stuck",
            end=12.0,
            words=[
                ev.Word(w="I'm", start=11.0, end=11.3, p=0.9),
                ev.Word(w="stuck", start=11.3, end=12.0),
            ],
            cues=["i'm stuck"],
        ),
    ),
    ev.IdleEvent(
        id="id_1", t=12.0, source="engine", kind="idle", data={"end": 60.0, "duration_s": 48.0}
    ),
    ev.MarkerEvent(
        id="mk_1",
        t=11.0,
        source="whisper",
        confidence=0.9,
        kind="marker",
        data={"label": "stuck", "origin": "speech", "text": "I'm stuck"},
    ),
    ev.MarkerEvent(
        id="mk_2", t=30.0, source="user", kind="marker", data={"label": "idea", "origin": "review"}
    ),
    ev.SessionEndEvent(**x(12, 61.0, kind="session_end", data={"reason": "user_stop"})),
]

REPORT = rp.Report(
    session_id="test_session",
    summary="Solid hash-map solution; an ordering bug cost about a minute.",
    metrics=rp.Metrics(
        total_time_s=176.2,
        time_per_phase_s={"read": 41.8, "code": 40.2, "debug": 68.0, "submit": 26.2},
        time_to_first_run_s=82.0,
        time_to_first_passing_run_s=152.7,
        runs_before_accept=2,
        churn=0.12,
        longest_idle_s=12.5,
        talk_ratio=0.38,
    ),
    correctness=rp.Correctness(
        platform_verdict="accepted",
        accepted=True,
        runs=2,
        failed_runs=1,
        submits=1,
        explanation="First run inserted before checking, so an element matched itself.",
        evidence=["ev_15"],
    ),
    complexity=rp.Complexity(time="O(n)", space="O(n)", optimal=True, evidence=["ev_29"]),
    strengths=[
        rp.Finding(
            start=17.5,
            end=29.9,
            title="Named the optimal approach early",
            detail="...",
            evidence=["sp_2"],
        )
    ],
    weaknesses=[
        rp.Finding(
            start=84.6,
            end=138.3,
            title="Slow to trace the failing case",
            detail="...",
            evidence=["ev_15", "mk_1"],
        )
    ],
    time_sinks=[
        rp.TimeSink(
            start=84.6,
            end=138.3,
            time_lost_s=40.0,
            category="implementation",
            what_happened="Inserted into the map before the lookup.",
            suggestion="Trace the smallest failing example by hand before rereading code.",
            evidence=["ev_15", "ev_24"],
        )
    ],
    communication=rp.Communication(
        thinking_aloud="Narrated the plan clearly.",
        clarifying="Did not ask about duplicates.",
        testing_out_loud="Walked through example three before submitting.",
        evidence=["sp_8"],
    ),
    vs_self_assessment="Matches: the ordering bug was the main cost.",
    vs_previous_attempts=None,
    suggested_tests=["nums with negative numbers", "target formed by duplicate values"],
    next_practice=["Three Sum"],
)

HELLO = pr.Hello(
    session_id="test_session",
    schema_version="1.0",
    adapter="leetcode",
    capabilities=make_capabilities(),
    clock_origin=make_manifest().clock_origin,
    media=make_manifest().media,
    resume_from=18,
)

MESSAGES: list[Any] = [
    HELLO,
    pr.EventMessage(event=EVENTS[7]),
    pr.Ping(),
    pr.Pong(),
    pr.End(final_seq=31, final_chunk={"audio": 17}),
    pr.Welcome(session_id="test_session", last_seq=17, last_chunk={"audio": 4}),
    pr.Ack(seq=20),
    pr.Ack(chunk=pr.ChunkRef(stream="audio", index=5)),
    pr.ErrorMessage(code="schema_mismatch", retryable=False, message="expected 1.x"),
]

FULL_MANIFEST = make_manifest(
    user_inputs=UserInputs(
        self_assessment="ok", target_time_s=600, reference_solution="ref.py", tests="tests.json"
    ),
    end=EndInfo(final_seq=31, final_chunk={"audio": 17}),
)

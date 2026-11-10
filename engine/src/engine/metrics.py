"""Metrics stage (design pipeline step 7): deterministic numbers and session facts.

Writes derived/metrics.json (the contract's Metrics, copied verbatim into the report by the AI
layer) and derived/facts.json. Correctness comes from platform verdicts only.
"""

from __future__ import annotations

from engine.files import read_model, write_model
from engine.models import NormalizeReport, Phases, SessionFacts, Signals
from engine.paths import SessionPaths
from engine.signals import churn, session_end_t
from ic_schema.bundle import read_bundle
from ic_schema.events import (
    CodeSnapshotEvent,
    Event,
    ProblemLoadedEvent,
    RunResultEvent,
    SpeechEvent,
    SubmitResultEvent,
)
from ic_schema.report import Metrics, Phase


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


def facts(paths: SessionPaths, events: list[Event]) -> SessionFacts:
    b = read_bundle(paths.root)
    caps = b.manifest.capabilities
    problems = [e for e in events if isinstance(e, ProblemLoadedEvent)]
    p = problems[-1].data if problems else None
    snaps = [e for e in events if isinstance(e, CodeSnapshotEvent)]
    run_results = [e for e in events if isinstance(e, RunResultEvent)]
    submit_results = [e for e in events if isinstance(e, SubmitResultEvent)]
    known_submits = [e for e in submit_results if e.data.verdict != "unknown"]
    return SessionFacts(
        session_id=b.manifest.session_id,
        platform=caps.platform,
        slug=p.slug if p else None,
        title=p.title if p else None,
        difficulty=p.difficulty if p else None,
        mode=caps.mode,
        session_language=caps.language,
        solution_language=(snaps[-1].data.language or caps.language) if snaps else caps.language,
        has_statement=bool(p and p.statement),
        has_audio=paths.audio.exists(),
        complete=b.complete,
        accepted=any(e.data.verdict == "accepted" for e in submit_results),
        final_verdict=known_submits[-1].data.verdict if known_submits else None,
        runs=sum(e.kind == "run" for e in events),
        failed_runs=sum(e.data.verdict not in ("accepted", "unknown") for e in run_results),
        submits=sum(e.kind == "submit" for e in events),
        failed_submits=sum(e.data.verdict not in ("accepted", "unknown") for e in submit_results),
        unknown_results=sum(e.data.verdict == "unknown" for e in run_results)
        + sum(e.data.verdict == "unknown" for e in submit_results),
    )


def compute(paths: SessionPaths, events: list[Event]) -> Metrics:
    end_t = session_end_t(events)
    phases = read_model(paths.d("phases.json"), Phases)
    signals = read_model(paths.d("signals.json"), Signals)
    norm = read_model(paths.d("normalize.json"), NormalizeReport)

    per_phase: dict[Phase, float] = {}
    for seg in phases.segments:
        per_phase[seg.phase] = round(per_phase.get(seg.phase, 0.0) + seg.end - seg.start, 3)

    runs = [e for e in events if e.kind == "run"]
    passing = [e for e in events if isinstance(e, RunResultEvent) and e.data.verdict == "accepted"]
    accepted = next(
        (e for e in events if isinstance(e, SubmitResultEvent) and e.data.verdict == "accepted"),
        None,
    )
    runs_before_accept = None
    if accepted is not None:
        submit_click = next(e for e in events if e.id == accepted.data.submit_id)
        runs_before_accept = sum(r.t < submit_click.t for r in runs)

    # Only when there is audio and a transcript (fresh or kept); otherwise unknown, not 0.
    talk_ratio = None
    if paths.audio.exists() and paths.d("transcript.jsonl").exists() and end_t > 0:
        speech = sum(e.data.end - e.t for e in events if isinstance(e, SpeechEvent))
        talk_ratio = round(min(1.0, speech / end_t), 3)

    has_code_changes = norm.lines_added or norm.lines_deleted
    return Metrics(
        total_time_s=round(end_t, 3),
        time_per_phase_s=per_phase,
        time_to_first_run_s=_r(runs[0].t) if runs else None,
        time_to_first_passing_run_s=_r(passing[0].t) if passing else None,
        runs_before_accept=runs_before_accept,
        churn=churn(norm.lines_added, norm.lines_deleted) if has_code_changes else None,
        longest_idle_s=signals.longest_gap_s,
        talk_ratio=talk_ratio,
    )


def run(paths: SessionPaths) -> tuple[Metrics, SessionFacts]:
    events = read_bundle(paths.root).timeline()
    m = compute(paths, events)
    f = facts(paths, events)
    write_model(paths.d("metrics.json"), m)
    write_model(paths.d("facts.json"), f)
    return m, f

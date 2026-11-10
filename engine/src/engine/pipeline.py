"""Stage registry and runner. Each stage reads the bundle and earlier derived files and writes
its own derived files, so any stage can be re-run alone (CLAUDE.md)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from engine import ingest, metrics, normalize, phases, signals, timeline, transcribe
from engine.files import write_model
from engine.models import PipelineStatus, StageRun, StageStatus
from engine.paths import SessionPaths
from engine.transcribe import Transcriber

STAGES = ("ingest", "normalize", "transcribe", "signals", "phases", "metrics", "timeline")


@dataclass
class Options:
    transcriber: Transcriber | None = None
    transcriber_error: str | None = None  # why no transcriber is available, if none
    skip: set[str] = field(default_factory=set)


class StageFailed(RuntimeError):
    def __init__(self, stage: str, cause: BaseException) -> None:
        super().__init__(f"stage {stage!r} failed: {cause}")
        self.stage = stage


def _run_stage(name: str, paths: SessionPaths, opts: Options) -> tuple[StageStatus, str | None]:
    if name == "ingest":
        r = ingest.run(paths)
        return "ok", "; ".join(r.warnings) or None
    if name == "normalize":
        n = normalize.run(paths)
        return "ok", f"{n.diffs} diffs, {len(n.redundant_snapshots)} redundant snapshots"
    if name == "transcribe":
        msg = transcribe.run(paths, opts.transcriber)
        if opts.transcriber is None and paths.audio.exists() and opts.transcriber_error:
            msg = f"{msg}: {opts.transcriber_error}"
        return ("skipped" if msg.startswith("skipped") else "ok"), msg
    if name == "signals":
        s = signals.run(paths)
        return "ok", f"{len(s.idle)} idle spans, {len(s.fail_streaks)} fail streaks"
    if name == "phases":
        p = phases.run(paths)
        return "ok", " ".join(f"{seg.phase}:{seg.end - seg.start:.0f}s" for seg in p.segments)
    if name == "metrics":
        metrics.run(paths)
        return "ok", None
    if name == "timeline":
        timeline.run(paths)
        return "ok", None
    raise ValueError(f"unknown stage {name!r}")


def select(from_: str | None = None, only: str | None = None) -> list[str]:
    for s in (from_, only):
        if s is not None and s not in STAGES:
            raise ValueError(f"unknown stage {s!r}; stages: {', '.join(STAGES)}")
    if only:
        return [only]
    return list(STAGES[STAGES.index(from_) :]) if from_ else list(STAGES)


def run(
    paths: SessionPaths,
    opts: Options | None = None,
    *,
    from_: str | None = None,
    only: str | None = None,
    on_stage: Callable[[str, StageRun], None] | None = None,
) -> PipelineStatus:
    opts = opts or Options()
    paths.derived.mkdir(parents=True, exist_ok=True)
    status = (
        PipelineStatus.model_validate_json(paths.pipeline.read_text())
        if paths.pipeline.exists()
        else PipelineStatus()
    )
    for name in select(from_, only):
        started = time.monotonic()
        if name in opts.skip:
            result = StageRun(status="skipped", seconds=0.0, message="skipped by request")
        else:
            try:
                st, msg = _run_stage(name, paths, opts)
                result = StageRun(
                    status=st, seconds=round(time.monotonic() - started, 3), message=msg
                )
            except Exception as e:
                result = StageRun(
                    status="failed", seconds=round(time.monotonic() - started, 3), message=str(e)
                )
                status.stages[name] = result
                write_model(paths.pipeline, status)
                if on_stage:
                    on_stage(name, result)
                raise StageFailed(name, e) from e
        status.stages[name] = result
        write_model(paths.pipeline, status)
        if on_stage:
            on_stage(name, result)
    return status

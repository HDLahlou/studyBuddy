"""interview-coach: Engine v0 command line.

    interview-coach import SESSION.zip [--replace]       extract into the data dir
    interview-coach process SESSION [--from S | --only S] [--skip S ...] [--no-transcribe]
    interview-coach run SESSION.zip                       import + process
    interview-coach show SESSION                          facts, phases, metrics, warnings

SESSION is a bundle folder or a session id under <data dir>/sessions. The data dir defaults to
~/Library/Application Support/InterviewCoach (IC_DATA_DIR or --data-dir to override).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine import pipeline
from engine.files import read_model
from engine.ingest import IngestError, import_zip
from engine.models import IngestReport, PipelineStatus, StageRun, Timeline
from engine.paths import SessionPaths, default_data_dir, resolve_session
from engine.transcribe import DEFAULT_MODEL, FasterWhisperTranscriber, TranscriberUnavailable


def _fmt(t: float | None) -> str:
    return "-" if t is None else f"{int(t // 60)}:{t % 60:05.2f}"


def _options(args: argparse.Namespace) -> pipeline.Options:
    opts = pipeline.Options(skip=set(args.skip or []))
    if args.no_transcribe:
        opts.transcriber_error = "transcription disabled (--no-transcribe)"
        return opts
    try:
        opts.transcriber = FasterWhisperTranscriber(model=args.model)
    except TranscriberUnavailable as e:
        opts.transcriber_error = str(e)
    return opts


def _print_stage(name: str, r: StageRun) -> None:
    msg = f"  {r.message}" if r.message else ""
    print(f"{name:<10} {r.status:<7} {r.seconds:6.2f}s{msg}")


def _process(root: Path, args: argparse.Namespace) -> int:
    paths = SessionPaths(root)
    stages = pipeline.select(args.from_stage, args.only)
    opts = _options(args) if "transcribe" in stages else pipeline.Options(skip=set(args.skip or []))
    try:
        pipeline.run(paths, opts, from_=args.from_stage, only=args.only, on_stage=_print_stage)
    except pipeline.StageFailed as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"done: {paths.derived}")
    return 0


def _show(root: Path) -> int:
    paths = SessionPaths(root)
    tl = read_model(paths.d("timeline.json"), Timeline)
    f, m = tl.facts, tl.metrics
    title = f.title or f.slug or "?"
    print(f"{title} ({f.difficulty or '?'}) · {f.platform} · {f.mode} · {f.solution_language}")
    verdict = f.final_verdict or "not submitted"
    print(
        f"verdict: {verdict} · runs {f.runs} ({f.failed_runs} failed) · "
        f"submits {f.submits} ({f.failed_submits} failed)"
    )
    print(
        f"total {_fmt(m.total_time_s)} · first run {_fmt(m.time_to_first_run_s)} · "
        f"first pass {_fmt(m.time_to_first_passing_run_s)} · "
        f"runs before accept {m.runs_before_accept}"
    )
    talk = "-" if m.talk_ratio is None else f"{m.talk_ratio:.0%}"
    churn = "-" if m.churn is None else f"{m.churn:.2f}"
    print(f"churn {churn} · longest idle {m.longest_idle_s:.0f}s · talk {talk}")
    print("phases:")
    for seg in tl.segments:
        s = seg.signals
        print(
            f"  {seg.phase:<7} {_fmt(seg.start)} - {_fmt(seg.end)}  {seg.end - seg.start:6.1f}s  "
            f"runs {s.runs} fails {s.fails} events {len(seg.events)}"
        )
    if tl.tail:
        print(f"  (tail)  {_fmt(tl.tail.start)} - {_fmt(tl.tail.end)}  after accept, not counted")
    ingest = read_model(paths.d("ingest.json"), IngestReport)
    status = read_model(paths.pipeline, PipelineStatus)
    notes = list(ingest.warnings) + [
        f"{name}: {r.message}"
        for name, r in status.stages.items()
        if r.status != "ok" and r.message
    ]
    for w in notes:
        print(f"warning: {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="interview-coach", description=__doc__.split("\n\n")[0] if __doc__ else None
    )
    ap.add_argument(
        "--data-dir", type=Path, default=None, help="default: %(default)s → platform data dir"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_process_args(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group()
        g.add_argument("--from", dest="from_stage", choices=pipeline.STAGES)
        g.add_argument("--only", choices=pipeline.STAGES)
        p.add_argument("--skip", action="append", choices=pipeline.STAGES)
        p.add_argument("--no-transcribe", action="store_true", help="skip transcription")
        p.add_argument(
            "--model", default=DEFAULT_MODEL, help="faster-whisper model (default %(default)s)"
        )

    p_import = sub.add_parser("import", help="extract a session zip into the data dir")
    p_import.add_argument("zip", type=Path)
    p_import.add_argument("--replace", action="store_true")
    p_process = sub.add_parser("process", help="run the pipeline on a session")
    p_process.add_argument("session")
    add_process_args(p_process)
    p_run = sub.add_parser("run", help="import a zip, then process it")
    p_run.add_argument("zip", type=Path)
    p_run.add_argument("--replace", action="store_true")
    add_process_args(p_run)
    p_show = sub.add_parser("show", help="summarize a processed session")
    p_show.add_argument("session")

    args = ap.parse_args(argv)
    data_dir: Path = args.data_dir or default_data_dir()
    try:
        if args.cmd in ("import", "run"):
            root = import_zip(args.zip, data_dir, replace=args.replace)
            print(f"imported: {root}")
            return _process(root, args) if args.cmd == "run" else 0
        root = resolve_session(args.session, data_dir)
        return _process(root, args) if args.cmd == "process" else _show(root)
    except (IngestError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

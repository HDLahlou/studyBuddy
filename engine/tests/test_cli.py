from __future__ import annotations

from pathlib import Path

import pytest

from engine import pipeline
from engine.cli import main
from engine.files import read_model
from engine.models import PipelineStatus, Timeline

from .test_ingest import make_zip


def test_run_imports_processes_and_shows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    zp = make_zip(tmp_path, "two_sum_basic")
    # --no-transcribe keeps the fixture's recorded transcript, so the plan phase still appears.
    assert main(["--data-dir", str(data), "run", str(zp), "--no-transcribe"]) == 0
    out = capsys.readouterr().out
    assert "imported:" in out and "timeline   ok" in out and "transcribe skipped" in out

    root = data / "sessions" / "session_fx_two_sum_basic"
    tl = read_model(root / "derived" / "timeline.json", Timeline)
    assert [s.phase for s in tl.segments] == ["read", "plan", "code", "debug", "test", "submit"]

    assert main(["--data-dir", str(data), "show", "fx_two_sum_basic"]) == 0
    shown = capsys.readouterr().out
    assert (
        "Two Sum (easy)" in shown and "verdict: accepted" in shown and "first pass 2:32.71" in shown
    )
    assert "debug" in shown and "(tail)" in shown


def test_process_only_one_stage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    main(
        [
            "--data-dir",
            str(data),
            "run",
            str(make_zip(tmp_path, "two_sum_live_order")),
            "--no-transcribe",
        ]
    )
    capsys.readouterr()
    assert (
        main(["--data-dir", str(data), "process", "fx_two_sum_live_order", "--only", "metrics"])
        == 0
    )
    out = capsys.readouterr().out
    assert out.startswith("metrics") and "normalize" not in out
    status = read_model(
        data / "sessions" / "session_fx_two_sum_live_order" / "derived" / "pipeline.json",
        PipelineStatus,
    )
    assert list(status.stages) == list(pipeline.STAGES)
    assert status.stages["transcribe"].message == "skipped: no audio"


def test_stage_missing_inputs_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert (
        main(["--data-dir", str(data), "import", str(make_zip(tmp_path, "two_sum_live_order"))])
        == 0
    )
    assert (
        main(["--data-dir", str(data), "process", "fx_two_sum_live_order", "--only", "phases"]) == 1
    )
    err = capsys.readouterr().err
    assert "stage 'phases' failed" in err and "run the stage that writes it first" in err


def test_errors_are_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--data-dir", str(tmp_path), "show", "nope"]) == 1
    assert "no session bundle" in capsys.readouterr().err
    bad = tmp_path / "bad.zip"
    import zipfile

    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../x", "x")
    assert main(["--data-dir", str(tmp_path), "import", str(bad)]) == 1
    assert "unsafe path" in capsys.readouterr().err

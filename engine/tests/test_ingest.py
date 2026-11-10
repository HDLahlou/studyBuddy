from __future__ import annotations

import json
import shutil
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from engine import ingest
from engine.ingest import IngestError, import_zip
from engine.paths import SessionPaths, resolve_session
from ic_schema.bundle import read_bundle

from .conftest import FIXTURES


def make_zip(tmp_path: Path, fixture: str = "two_sum_basic", top: str | None = None) -> Path:
    src = FIXTURES / fixture
    sid = json.loads((src / "manifest.json").read_text())["session_id"]
    top = top or f"session_{sid}"
    zp = tmp_path / f"{fixture}.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, f"{top}/{p.relative_to(src)}")
    return zp


def write_zip(tmp_path: Path, entries: dict[str, bytes], name: str = "bad.zip") -> Path:
    zp = tmp_path / name
    with zipfile.ZipFile(zp, "w") as zf:
        for n, data in entries.items():
            zf.writestr(n, data)
    return zp


MANIFEST = json.dumps({"session_id": "x"}).encode()


def test_import_extracts_atomically_and_resolves(tmp_path: Path) -> None:
    data = tmp_path / "data"
    root = import_zip(make_zip(tmp_path), data)
    assert root == data / "sessions" / "session_fx_two_sum_basic"
    assert read_bundle(root).complete
    assert not list((data / "sessions").glob(".importing-*"))
    assert resolve_session("fx_two_sum_basic", data) == root
    assert resolve_session("session_fx_two_sum_basic", data) == root
    assert resolve_session(str(root), data) == root


def test_import_refuses_existing_unless_replace(tmp_path: Path) -> None:
    data = tmp_path / "data"
    zp = make_zip(tmp_path)
    import_zip(zp, data)
    with pytest.raises(IngestError, match="already exists"):
        import_zip(zp, data)
    root = import_zip(zp, data, replace=True)
    assert read_bundle(root).complete


@pytest.mark.parametrize(
    "entries, match",
    [
        ({"session_x/../evil.txt": b"x", "session_x/manifest.json": MANIFEST}, "unsafe path"),
        ({"/abs/manifest.json": MANIFEST}, "unsafe path"),
        ({"session_x/manifest.json": MANIFEST, "other/file": b"x"}, "exactly one"),
        ({"not_a_session/manifest.json": MANIFEST}, "session_<id>"),
        ({"session_x/events.jsonl": b""}, "no manifest"),
        ({"session_y/manifest.json": MANIFEST}, "does not match"),
        ({}, "empty"),
    ],
)
def test_import_rejects_unsafe_zips(tmp_path: Path, entries: dict[str, bytes], match: str) -> None:
    with pytest.raises(IngestError, match=match):
        import_zip(write_zip(tmp_path, entries), tmp_path / "data")
    assert not (tmp_path / "data" / "sessions" / "session_x").exists()


def test_import_rejects_symlinks(tmp_path: Path) -> None:
    zp = tmp_path / "link.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("session_x/manifest.json", MANIFEST)
        info = zipfile.ZipInfo("session_x/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(IngestError, match="symlink"):
        import_zip(zp, tmp_path / "data")


def test_ingest_basic_joins_audio(bundle_copy: Callable[[str], SessionPaths]) -> None:
    paths = bundle_copy("two_sum_basic")
    report = ingest.run(paths)
    b = read_bundle(paths.root)
    assert report.complete and report.ended and report.compatible and not report.warnings
    assert report.events == 31 and report.seq_gaps == []
    assert report.audio is not None and report.audio.chunks == 18 and report.audio.offset_s == 0.35
    assert paths.audio.read_bytes() == b.media["audio"].join()
    assert paths.audio.read_bytes()[:4] == b"\x1a\x45\xdf\xa3"
    assert (paths.derived / "ingest.json").exists()


def test_ingest_reports_gaps(bundle_copy: Callable[[str], SessionPaths]) -> None:
    paths = bundle_copy("two_sum_seq_gap")
    report = ingest.run(paths)
    assert not report.complete and report.duplicates == 2
    assert [(g.first, g.last) for g in report.seq_gaps] == [(18, 20)]
    assert report.audio is None and not paths.audio.exists()
    assert any("missing events: seq 18-20" in w for w in report.warnings)


def test_ingest_rejects_incompatible_schema(bundle_copy: Callable[[str], SessionPaths]) -> None:
    paths = bundle_copy("two_sum_live_order")
    m = json.loads((paths.root / "manifest.json").read_text())
    m["schema_version"] = "2.0"
    (paths.root / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(IngestError, match="not compatible"):
        ingest.run(paths)


def test_ingest_warns_when_audio_claimed_but_missing(
    bundle_copy: Callable[[str], SessionPaths],
) -> None:
    paths = bundle_copy("two_sum_basic")
    shutil.rmtree(paths.root / "media")
    report = ingest.run(paths)
    assert report.audio is None
    assert any("no audio chunks" in w for w in report.warnings)


def test_ingest_warns_when_timestamps_collapse_at_zero(
    bundle_copy: Callable[[str], SessionPaths],
) -> None:
    # The pre-E16 clock bug: every capture clamped to t=0, without confidence 0.
    paths = bundle_copy("two_sum_live_order")
    lines = [json.loads(ln) for ln in (paths.root / "events.jsonl").read_text().splitlines()]
    for e in lines:
        if e["kind"] not in ("session_start", "session_end"):
            e["t"] = 0.0
    (paths.root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in lines))
    report = ingest.run(paths)
    assert any("stamped at t=0" in w and "unreliable" in w for w in report.warnings)
    assert not ingest.run(bundle_copy("two_sum_basic")).warnings  # a healthy session stays quiet

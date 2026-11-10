"""Fixtures validate against the generated JSON Schema, read cleanly, and replay through ingest."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from ic_schema import export
from ic_schema.bundle import AppendResult, Gap, read_bundle
from ic_schema.events import Event
from ic_schema.replay import bundle_frames, ingest_frames

from .helpers import FIXTURES, GENERATED

BASIC = FIXTURES / "two_sum_basic"
SEQ_GAP = FIXTURES / "two_sum_seq_gap"
LIVE_ORDER = FIXTURES / "two_sum_live_order"
FAILED_SCRAPE = FIXTURES / "two_sum_failed_scrape"
ALL = [BASIC, SEQ_GAP, LIVE_ORDER, FAILED_SCRAPE]


def validator(name: str) -> Draft202012Validator:
    schema = json.loads((GENERATED / f"{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def jsonl(path: Path) -> Iterator[dict[str, Any]]:
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def assert_valid(v: Draft202012Validator, doc: Any, where: str) -> None:
    errors = sorted(v.iter_errors(doc), key=str)
    assert not errors, f"{where}: " + "; ".join(e.message for e in errors[:3])


# --- generated schema -----------------------------------------------------------------------


def test_generated_schemas_are_up_to_date() -> None:
    for name, text in export.render().items():
        on_disk = (GENERATED / name).read_text()
        assert on_disk == text, f"{name} is stale: run `make schema`"


def test_contract_schema_is_valid_and_covers_all_documents() -> None:
    v = validator("contract")
    defs = v.schema["$defs"]
    for _, title in export.DOCUMENTS.values():
        assert title in defs


# --- fixtures vs JSON Schema ----------------------------------------------------------------


@pytest.mark.parametrize("root", ALL, ids=lambda p: p.name)
def test_fixture_validates_against_json_schema(root: Path) -> None:
    assert_valid(
        validator("manifest"), json.loads((root / "manifest.json").read_text()), "manifest"
    )
    ev = validator("event")
    files = [root / "events.jsonl", *sorted((root / "derived").glob("*.jsonl"))]
    for f in files:
        if f.exists():
            for i, doc in enumerate(jsonl(f), 1):
                assert_valid(ev, doc, f"{f.name}:{i}")


def test_json_schema_rejects_what_pydantic_rejects() -> None:
    ev = validator("event")
    good = next(jsonl(BASIC / "events.jsonl"))
    assert ev.is_valid(good)
    assert not ev.is_valid({**good, "kind": "hint_shown"})
    assert not ev.is_valid({**good, "data": {"url": 1}})
    assert not ev.is_valid({**good, "surprise": True})
    assert not ev.is_valid({k: v for k, v in good.items() if k != "kind"})


# --- fixtures through the reader ------------------------------------------------------------


def test_basic_fixture_reads_complete() -> None:
    b = read_bundle(BASIC)
    assert b.complete and b.gaps == [] and b.duplicates == 0 and not b.conflicts
    assert len(b.events) == 31 and b.events[0].kind == "session_start"
    assert b.events[-1].kind == "session_end"
    assert len(b.media["audio"].records) == 18 and b.media["audio"].gaps == []
    assert b.manifest.capabilities.audio and not b.manifest.capabilities.video


def test_basic_fixture_story() -> None:
    b = read_bundle(BASIC)
    derived = b.read_derived_events("transcript.jsonl")
    kinds = [e.kind for e in b.events]
    assert len(b.events) + len(derived) == 41
    assert kinds.count("run") == 2 and kinds.count("submit") == 1
    verdicts = [e.data.verdict for e in b.events if e.kind in ("run_result", "submit_result")]  # type: ignore[union-attr]
    assert verdicts == ["wrong_answer", "accepted", "accepted"]
    markers = [e for e in derived if e.kind == "marker"]
    assert len(markers) == 1 and markers[0].data.label == "stuck"  # type: ignore[union-attr]
    assert sum(e.kind == "speech" for e in derived) == 9


def _check_consistency(events: list[Event], derived: list[Event]) -> None:
    """What the contract guarantees. Seq is delivery order, not time order (001 D1, 002 E2)."""
    ids = [e.id for e in events + derived]
    assert len(ids) == len(set(ids)), "event ids must be unique within a session"
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "read_bundle returns unique seqs"
    by_id = {e.id: e for e in events}
    start = next(e for e in events if e.kind == "session_start")
    ends = [e for e in events if e.kind == "session_end"]
    end_t = ends[0].t if ends else max(e.t for e in events)
    assert start.t == 0
    for e in events + derived:
        assert 0 <= e.t <= end_t, f"{e.id} outside the session"
        if e.kind == "run_result":
            assert by_id[e.data.run_id].kind == "run" and by_id[e.data.run_id].t < e.t
        if e.kind == "submit_result":
            assert by_id[e.data.submit_id].kind == "submit" and by_id[e.data.submit_id].t < e.t
        if e.kind == "speech":
            assert e.t < e.data.end <= end_t


@pytest.mark.parametrize("root", ALL, ids=lambda p: p.name)
def test_fixture_internal_consistency(root: Path) -> None:
    b = read_bundle(root)
    derived = b.read_derived_events("transcript.jsonl") if (root / "derived").exists() else []
    _check_consistency(b.events, derived)


def test_basic_audio_covers_the_session() -> None:
    b = read_bundle(BASIC)
    audio = b.manifest.media.audio
    assert audio is not None and audio.offset_s is not None
    first = b.media["audio"].records[0]
    assert first.start_ms == round(audio.offset_s * 1000)
    assert b.media["audio"].join()[:4] == b"\x1a\x45\xdf\xa3"  # EBML / WebM magic


def test_seq_gap_fixture() -> None:
    b = read_bundle(SEQ_GAP)
    assert b.gaps == [Gap(18, 20)]
    assert b.duplicates == 2 and not b.conflicts
    assert b.ended and not b.complete
    assert "audio" not in b.media and not b.manifest.capabilities.audio


# --- replay harness -------------------------------------------------------------------------


@pytest.mark.parametrize("root", ALL, ids=lambda p: p.name)
def test_replay_reproduces_bundle(root: Path, tmp_path: Path) -> None:
    original = read_bundle(root)
    frames = list(bundle_frames(root))
    assert isinstance(frames[0], str) and '"type":"hello"' in frames[0]
    assert isinstance(frames[-1], str) and '"type":"end"' in frames[-1]

    counts = ingest_frames(tmp_path / "replayed", frames)
    copy = read_bundle(tmp_path / "replayed")
    assert copy.events == original.events
    assert copy.gaps == original.gaps
    assert copy.complete == original.complete
    assert copy.manifest.model_dump(exclude={"user_inputs"}) == original.manifest.model_dump(
        exclude={"user_inputs"}
    )
    for stream, chunks in original.media.items():
        assert copy.media[stream].join() == chunks.join()
    assert counts[AppendResult.CONFLICT] == 0


def test_replaying_twice_is_safe(tmp_path: Path) -> None:
    frames = list(bundle_frames(BASIC))
    body = frames[1:-1]
    counts = ingest_frames(tmp_path / "s", [frames[0], *body, *body, frames[-1]])
    assert counts[AppendResult.DUPLICATE] == len(body)
    assert read_bundle(tmp_path / "s").complete


# --- timeline order -------------------------------------------------------------------------


def test_live_order_fixture_is_out_of_time_order_by_seq() -> None:
    b = read_bundle(LIVE_ORDER)
    assert any(c.t < a.t for a, c in zip(b.events, b.events[1:], strict=False))
    assert b.complete and not b.gaps


@pytest.mark.parametrize("root", ALL, ids=lambda p: p.name)
def test_timeline_orders_by_time(root: Path) -> None:
    b = read_bundle(root)
    tl = b.timeline()
    assert [e.t for e in tl] == sorted(e.t for e in tl)
    assert {e.id for e in tl} == {e.id for e in b.events} | {
        e.id for n in b.derived_event_files() for e in b.read_derived_events(n)
    }


def test_timeline_merges_derived_and_breaks_ties() -> None:
    b = read_bundle(BASIC)
    tl = b.timeline()
    kinds = {e.kind for e in tl}
    assert {"speech", "marker", "run", "code_snapshot"} <= kinds
    # At equal t, captured (seq) sorts before derived (no seq), then by seq.
    for a, c in zip(tl, tl[1:], strict=False):
        if a.t == c.t and a.seq is not None and c.seq is not None:
            assert a.seq < c.seq
        if a.t == c.t and a.seq is None:
            assert c.seq is None
    assert b.timeline(derived=[]) == sorted(b.events, key=lambda e: (e.t, e.seq or 0))


def test_live_order_timeline_matches_basic() -> None:
    def shape(root: Path) -> list[tuple[float, str]]:
        return [(e.t, e.kind) for e in read_bundle(root).timeline(derived=[])]

    assert shape(LIVE_ORDER) == shape(BASIC)


def test_failed_scrape_fixture() -> None:
    b = read_bundle(FAILED_SCRAPE)
    unknown = [e for e in b.events if e.kind == "run_result" and e.data.verdict == "unknown"]
    assert len(unknown) == 1 and unknown[0].confidence == 0
    run = next(e for e in b.events if e.id == unknown[0].data.run_id)
    assert unknown[0].t == pytest.approx(run.t + 30)


def test_timeline_rejects_duplicate_ids(tmp_path: Path) -> None:
    import shutil

    from ic_schema.bundle import BundleError

    root = tmp_path / "b"
    shutil.copytree(BASIC, root)
    (root / "derived" / "dupe.jsonl").write_text(
        (root / "derived" / "transcript.jsonl").read_text()
    )
    with pytest.raises(BundleError, match="duplicate event id"):
        read_bundle(root).timeline()

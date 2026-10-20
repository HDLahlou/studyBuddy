"""Bundle read/write, seq dedupe, gap detection, media chunks."""

from __future__ import annotations

from pathlib import Path

import pytest

from ic_schema.bundle import (
    CONFLICTS,
    EVENTS,
    AppendResult,
    BundleError,
    BundleWriter,
    Gap,
    contiguous_prefix,
    find_gaps,
    read_bundle,
)
from ic_schema.events import UndoEvent
from ic_schema.manifest import Manifest
from ic_schema.protocol import MediaChunkHeader, pack_chunk

from .samples import EVENTS as SAMPLE_EVENTS


def undo(seq: int, t: float | None = None, count: int = 1) -> UndoEvent:
    return UndoEvent(
        id=f"ev_{seq}",
        t=t if t is not None else float(seq),
        seq=seq,
        source="extension",
        kind="undo",
        data={"count": count},
    )


def chunk(index: int, stream: str = "audio") -> MediaChunkHeader:
    return MediaChunkHeader(stream=stream, chunk_index=index, start_ms=200 + index * 10_000)  # type: ignore[arg-type]


@pytest.fixture
def writer(tmp_path: Path, manifest: Manifest) -> BundleWriter:
    return BundleWriter.create(tmp_path / "session_test", manifest)


# --- gap helpers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "present, last, gaps",
    [
        (set(), None, []),
        (set(), 3, [Gap(1, 3)]),
        ({1, 2, 3}, None, []),
        ({1, 2, 3}, 5, [Gap(4, 5)]),
        ({1, 4, 5, 9}, None, [Gap(2, 3), Gap(6, 8)]),
        ({2}, None, [Gap(1, 1)]),
    ],
)
def test_find_gaps(present: set[int], last: int | None, gaps: list[Gap]) -> None:
    assert find_gaps(present, 1, last) == gaps


def test_contiguous_prefix() -> None:
    assert contiguous_prefix(set(), 1) == 0
    assert contiguous_prefix({1, 2, 3, 5}, 1) == 3
    assert contiguous_prefix({0, 1}, 0) == 1
    assert contiguous_prefix({1}, 0) == -1


# --- events ---------------------------------------------------------------------------------


def test_create_lays_out_folders(writer: BundleWriter) -> None:
    for name in ("manifest.json", "inputs", "derived", "report"):
        assert (writer.root / name).exists()


def test_create_refuses_existing(writer: BundleWriter, manifest: Manifest) -> None:
    with pytest.raises(BundleError, match="already exists"):
        BundleWriter.create(writer.root, manifest)


def test_write_then_read_sorts_by_seq(writer: BundleWriter) -> None:
    for seq in (1, 3, 2, 4):
        assert writer.append(undo(seq)) is AppendResult.APPENDED
    b = read_bundle(writer.root)
    assert [e.seq for e in b.events] == [1, 2, 3, 4]
    assert b.gaps == [] and b.duplicates == 0 and not b.ended and not b.complete
    assert b.manifest == writer.manifest


def test_all_extension_sample_events_roundtrip_through_bundle(writer: BundleWriter) -> None:
    captured = [e for e in SAMPLE_EVENTS if e.source == "extension"]
    for e in captured:
        writer.append(e)
    assert read_bundle(writer.root).events == sorted(captured, key=lambda e: e.seq or 0)


def test_events_file_is_append_only_arrival_order(writer: BundleWriter) -> None:
    for seq in (2, 1):
        writer.append(undo(seq))
    lines = (writer.root / EVENTS).read_text().splitlines()
    assert [line.split('"seq":')[1].split(",")[0] for line in lines] == ["2", "1"]


def test_duplicate_seq_is_dropped(writer: BundleWriter) -> None:
    writer.append(undo(1))
    assert writer.append(undo(1)) is AppendResult.DUPLICATE
    assert len((writer.root / EVENTS).read_text().splitlines()) == 1


def test_conflicting_seq_keeps_first_and_logs(writer: BundleWriter) -> None:
    writer.append(undo(1, count=1))
    assert writer.append(undo(1, count=5)) is AppendResult.CONFLICT
    b = read_bundle(writer.root)
    assert len(b.events) == 1 and b.events[0].data.count == 1  # type: ignore[union-attr]
    assert len(b.conflicts) == 1 and b.conflicts[0].data.count == 5  # type: ignore[union-attr]
    assert (writer.root / CONFLICTS).exists()


def test_reader_dedupes_raw_duplicate_lines(writer: BundleWriter) -> None:
    writer.append(undo(1))
    path = writer.root / EVENTS
    path.write_text(path.read_text() * 3)
    b = read_bundle(writer.root)
    assert len(b.events) == 1 and b.duplicates == 2


def test_rejects_derived_events(writer: BundleWriter) -> None:
    speech = next(e for e in SAMPLE_EVENTS if e.kind == "speech")
    with pytest.raises(BundleError, match="captured events only"):
        writer.append(speech)


def test_gap_detection_and_position(writer: BundleWriter) -> None:
    for seq in (1, 2, 3, 7, 8):
        writer.append(undo(seq))
    b = read_bundle(writer.root)
    assert b.gaps == [Gap(4, 6)]
    assert writer.position().last_seq == 3


def test_trailing_gap_found_once_end_is_known(writer: BundleWriter) -> None:
    for seq in (1, 2, 3):
        writer.append(undo(seq))
    writer.close(final_seq=5)
    b = read_bundle(writer.root)
    assert b.gaps == [Gap(4, 5)] and b.ended and not b.complete


def test_complete_after_end_without_gaps(writer: BundleWriter) -> None:
    for seq in (1, 2):
        writer.append(undo(seq))
    writer.close(final_seq=2)
    b = read_bundle(writer.root)
    assert b.complete and b.manifest.end is not None and b.manifest.end.final_seq == 2


def test_resume_reopens_and_still_dedupes(writer: BundleWriter) -> None:
    for seq in (1, 2, 3):
        writer.append(undo(seq))
    reopened = BundleWriter.open(writer.root)
    assert reopened.position().last_seq == 3
    assert reopened.append(undo(2)) is AppendResult.DUPLICATE
    assert reopened.append(undo(4)) is AppendResult.APPENDED
    assert [e.seq for e in read_bundle(writer.root).events] == [1, 2, 3, 4]


def test_torn_tail_ignored_by_reader_and_dropped_on_resume(writer: BundleWriter) -> None:
    writer.append(undo(1))
    with (writer.root / EVENTS).open("a") as f:
        f.write('{"id":"ev_2","t":2.0,"se')
    b = read_bundle(writer.root)
    assert b.torn_tail and [e.seq for e in b.events] == [1]
    reopened = BundleWriter.open(writer.root)
    assert reopened.append(undo(2)) is AppendResult.APPENDED
    b = read_bundle(writer.root)
    assert not b.torn_tail and [e.seq for e in b.events] == [1, 2]


# --- media ----------------------------------------------------------------------------------


def test_chunks_write_read_join(writer: BundleWriter) -> None:
    payloads = [b"HEADER+aaa", b"bbb", b"cc"]
    for i, p in enumerate(payloads):
        assert writer.write_chunk(chunk(i), p) is AppendResult.APPENDED
    writer.close(final_seq=0, final_chunk={"audio": 2})
    b = read_bundle(writer.root)
    audio = b.media["audio"]
    assert [r.index for r in audio.records] == [0, 1, 2]
    assert [r.start_ms for r in audio.records] == [200, 10_200, 20_200]
    assert audio.paths[0].name == "000000.webm"
    assert audio.join() == b"".join(payloads)
    assert audio.gaps == [] and b.complete


def test_write_frame_parses_header(writer: BundleWriter) -> None:
    header, result = writer.write_frame(pack_chunk(chunk(0, "video"), b"v"))
    assert result is AppendResult.APPENDED and header.stream == "video"
    assert read_bundle(writer.root).media["video"].paths[0].read_bytes() == b"v"


def test_chunk_dedupe_and_conflict(writer: BundleWriter) -> None:
    writer.write_chunk(chunk(0), b"abc")
    assert writer.write_chunk(chunk(0), b"abc") is AppendResult.DUPLICATE
    assert writer.write_chunk(chunk(0), b"xyz") is AppendResult.CONFLICT
    assert read_bundle(writer.root).media["audio"].join() == b"abc"


def test_chunk_gaps_per_stream_and_position(writer: BundleWriter) -> None:
    for i in (0, 1, 3):
        writer.write_chunk(chunk(i), b"a")
    writer.write_chunk(chunk(0, "video"), b"v")
    assert writer.position().last_chunk == {"audio": 1, "video": 0}
    writer.close(final_seq=0, final_chunk={"audio": 4, "video": 0})
    b = read_bundle(writer.root)
    assert b.media["audio"].gaps == [Gap(2, 2), Gap(4, 4)]
    assert b.media["video"].gaps == []
    assert not b.complete


def test_chunk_index_survives_resume(writer: BundleWriter) -> None:
    writer.write_chunk(chunk(0), b"a")
    reopened = BundleWriter.open(writer.root)
    assert reopened.write_chunk(chunk(0), b"a") is AppendResult.DUPLICATE
    assert reopened.position().last_chunk == {"audio": 0}

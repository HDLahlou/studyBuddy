"""Replay harness: turn a saved bundle back into the frames the extension would send.

`bundle_frames` yields `hello`, then event messages and binary media frames interleaved by time
(a chunk is sent when its timeslice ends), then `end`. `ingest_frames` is a minimal reference
consumer that writes frames into a `BundleWriter`; engine ingest tests replay fixtures through
the real handler the same way, without a browser.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from ic_schema.bundle import STREAMS, AppendResult, BundleWriter, read_bundle
from ic_schema.manifest import Manifest
from ic_schema.protocol import (
    End,
    EventMessage,
    Hello,
    MediaChunkHeader,
    pack_chunk,
    parse_client_message,
)

Frame = str | bytes


def bundle_frames(root: Path, *, adapter: str | None = None) -> Iterator[Frame]:
    bundle = read_bundle(root)
    m = bundle.manifest
    yield Hello(
        session_id=m.session_id,
        schema_version=m.schema_version,
        adapter=adapter or m.capabilities.platform,
        capabilities=m.capabilities,
        clock_origin=m.clock_origin,
        media=m.media,
    ).model_dump_json()

    timed: list[tuple[float, int, Frame]] = []
    for ev in bundle.events:
        timed.append((ev.t, 0, EventMessage(event=ev).model_dump_json()))
    for stream in STREAMS:
        chunks = bundle.media.get(stream)
        if chunks is None:
            continue
        records = chunks.records
        for i, (rec, path) in enumerate(zip(records, chunks.paths, strict=True)):
            sent_at = (records[i + 1].start_ms if i + 1 < len(records) else rec.start_ms) / 1000
            header = MediaChunkHeader(stream=stream, chunk_index=rec.index, start_ms=rec.start_ms)
            timed.append((sent_at, 1, pack_chunk(header, path.read_bytes())))
    timed.sort(key=lambda x: (x[0], x[1]))
    yield from (frame for _, _, frame in timed)

    if m.end is not None:
        yield End(final_seq=m.end.final_seq, final_chunk=m.end.final_chunk).model_dump_json()


def ingest_frames(root: Path, frames: Iterable[Frame]) -> dict[AppendResult, int]:
    """Write a frame stream into a new bundle at `root`. Returns counts per append outcome."""
    counts = dict.fromkeys(AppendResult, 0)
    writer: BundleWriter | None = None
    for frame in frames:
        if isinstance(frame, bytes):
            assert writer is not None, "media frame before hello"
            counts[writer.write_frame(frame)[1]] += 1
            continue
        msg = parse_client_message(frame)
        if isinstance(msg, Hello):
            manifest = Manifest(
                schema_version=msg.schema_version,
                session_id=msg.session_id,
                capabilities=msg.capabilities,
                clock_origin=msg.clock_origin,
                media=msg.media,
            )
            writer = BundleWriter.create(root, manifest)
        elif isinstance(msg, EventMessage):
            assert writer is not None, "event before hello"
            counts[writer.append(msg.event)] += 1
        elif isinstance(msg, End):
            assert writer is not None, "end before hello"
            writer.close(msg.final_seq, msg.final_chunk)
    return counts

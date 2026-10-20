"""Session bundle I/O.

Layout::

    session_<id>/
      manifest.json
      events.jsonl               # captured (extension) events only, append-only, arrival order
      events.conflicts.jsonl     # same seq, different content: rejected copies, for audit
      media/<stream>/000000.webm # raw MediaRecorder payloads, one file per chunk
      media/<stream>/chunks.jsonl# chunk index: {index, start_ms, bytes}
      inputs/  derived/  report/

`BundleWriter` is what ingest uses: it dedupes by `seq` (and chunk index), so replays are safe.
`read_bundle` returns events sorted by seq, deduped, with gaps and completeness reported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ic_schema.events import Event, dump_event, parse_event
from ic_schema.manifest import EndInfo, Manifest, StreamName
from ic_schema.protocol import MediaChunkHeader, Welcome, unpack_chunk

MANIFEST = "manifest.json"
EVENTS = "events.jsonl"
CONFLICTS = "events.conflicts.jsonl"
MEDIA = "media"
CHUNK_INDEX = "chunks.jsonl"
SUBDIRS = ("inputs", "derived", "report")
STREAMS: tuple[StreamName, ...] = ("audio", "video")

_MIME_EXT = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "wav": "wav"}


class BundleError(Exception):
    pass


class AppendResult(Enum):
    APPENDED = "appended"
    DUPLICATE = "duplicate"  # same seq, identical content: dropped
    CONFLICT = "conflict"  # same seq, different content: first copy kept, this one logged


class ChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    bytes: int = Field(ge=0)


@dataclass(frozen=True)
class Gap:
    """Inclusive range of missing sequence numbers (or chunk indexes)."""

    first: int
    last: int


def find_gaps(present: set[int], start: int, last: int | None = None) -> list[Gap]:
    """Missing numbers in [start, last]. `last` defaults to max(present) (no trailing gap known)."""
    top = last if last is not None else max(present, default=start - 1)
    gaps: list[Gap] = []
    run_start: int | None = None
    for n in range(start, top + 1):
        if n not in present:
            if run_start is None:
                run_start = n
        elif run_start is not None:
            gaps.append(Gap(run_start, n - 1))
            run_start = None
    if run_start is not None:
        gaps.append(Gap(run_start, top))
    return gaps


def contiguous_prefix(present: set[int], start: int) -> int:
    """Highest n such that every number in [start, n] is present; start - 1 if none."""
    n = start
    while n in present:
        n += 1
    return n - 1


def chunk_extension(mime: str | None) -> str:
    if mime:
        subtype = mime.split("/", 1)[-1].split(";", 1)[0].strip()
        return _MIME_EXT.get(subtype, "bin")
    return "webm"


def chunk_filename(index: int, ext: str) -> str:
    return f"{index:06d}.{ext}"


def _write_json_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_jsonl_lines(path: Path) -> tuple[list[str], bool]:
    """Complete lines, plus whether a torn (unterminated) last line was ignored."""
    if not path.exists():
        return [], False
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    torn = lines[-1] != ""
    return [ln for ln in lines[:-1] if ln.strip()], torn


def _drop_torn_tail(path: Path) -> None:
    """Truncate an unterminated last line left by a crash mid-append."""
    if not path.exists():
        return
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n") + 1
        with path.open("r+b") as f:
            f.truncate(cut)


def read_manifest(root: Path) -> Manifest:
    return Manifest.model_validate_json((root / MANIFEST).read_text(encoding="utf-8"))


def write_manifest(root: Path, manifest: Manifest) -> None:
    _write_json_atomic(root / MANIFEST, manifest.model_dump_json(indent=2) + "\n")


# --- writer ---------------------------------------------------------------------------------


class BundleWriter:
    """Append-only writer for a live or replayed session. Not thread-safe; one per session."""

    def __init__(self, root: Path, manifest: Manifest, *, fsync: bool = False) -> None:
        self.root = root
        self.manifest = manifest
        self._fsync = fsync
        self._events: dict[int, str] = {}  # seq -> canonical JSON
        self._chunks: dict[StreamName, dict[int, ChunkRecord]] = {s: {} for s in STREAMS}
        self._load_existing()

    @classmethod
    def create(cls, root: Path, manifest: Manifest, *, fsync: bool = False) -> BundleWriter:
        if (root / MANIFEST).exists():
            raise BundleError(f"bundle already exists: {root}")
        root.mkdir(parents=True, exist_ok=True)
        for sub in SUBDIRS:
            (root / sub).mkdir(exist_ok=True)
        write_manifest(root, manifest)
        return cls(root, manifest, fsync=fsync)

    @classmethod
    def open(cls, root: Path, *, fsync: bool = False) -> BundleWriter:
        """Resume an existing bundle (e.g. after the extension reconnects)."""
        return cls(root, read_manifest(root), fsync=fsync)

    def _load_existing(self) -> None:
        _drop_torn_tail(self.root / EVENTS)
        lines, _ = _read_jsonl_lines(self.root / EVENTS)
        for line in lines:
            ev = parse_event(line)
            assert ev.seq is not None
            self._events.setdefault(ev.seq, dump_event(ev))
        for stream in STREAMS:
            idx_path = self.root / MEDIA / stream / CHUNK_INDEX
            _drop_torn_tail(idx_path)
            for line in _read_jsonl_lines(idx_path)[0]:
                rec = ChunkRecord.model_validate_json(line)
                self._chunks[stream].setdefault(rec.index, rec)

    def _append_line(self, path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            if self._fsync:
                os.fsync(f.fileno())

    def append(self, event: Event) -> AppendResult:
        if event.source != "extension" or event.seq is None:
            raise BundleError(
                "events.jsonl holds captured events only; write derived events to derived/"
            )
        line = dump_event(event)
        existing = self._events.get(event.seq)
        if existing is not None:
            if existing == line:
                return AppendResult.DUPLICATE
            self._append_line(self.root / CONFLICTS, line)
            return AppendResult.CONFLICT
        self._append_line(self.root / EVENTS, line)
        self._events[event.seq] = line
        return AppendResult.APPENDED

    def write_chunk(self, header: MediaChunkHeader, payload: bytes) -> AppendResult:
        known = self._chunks[header.stream].get(header.chunk_index)
        stream_dir = self.root / MEDIA / header.stream
        path = stream_dir / chunk_filename(header.chunk_index, self._ext(header.stream))
        if known is not None:
            same = known.bytes == len(payload) and path.read_bytes() == payload
            return AppendResult.DUPLICATE if same else AppendResult.CONFLICT
        stream_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, path)
        rec = ChunkRecord(index=header.chunk_index, start_ms=header.start_ms, bytes=len(payload))
        self._append_line(stream_dir / CHUNK_INDEX, rec.model_dump_json())
        self._chunks[header.stream][header.chunk_index] = rec
        return AppendResult.APPENDED

    def write_frame(self, frame: bytes) -> tuple[MediaChunkHeader, AppendResult]:
        """Store a binary WebSocket frame (header + payload)."""
        header, payload = unpack_chunk(frame)
        return header, self.write_chunk(header, payload)

    def _ext(self, stream: StreamName) -> str:
        info = getattr(self.manifest.media, stream)
        return chunk_extension(info.mime if info else None)

    def close(self, final_seq: int, final_chunk: dict[StreamName, int] | None = None) -> None:
        """Record the extension's `end` message in the manifest."""
        self.manifest = self.manifest.model_copy(
            update={"end": EndInfo(final_seq=final_seq, final_chunk=final_chunk or {})}
        )
        write_manifest(self.root, self.manifest)

    def position(self) -> Welcome:
        """Highest seq / chunk index with nothing missing below it, for `welcome`."""
        last_chunk: dict[StreamName, int] = {}
        for stream in STREAMS:
            top = contiguous_prefix(set(self._chunks[stream]), 0)
            if top >= 0:
                last_chunk[stream] = top
        return Welcome(
            session_id=self.manifest.session_id,
            last_seq=contiguous_prefix(set(self._events), 1),
            last_chunk=last_chunk,
        )


# --- reader ---------------------------------------------------------------------------------


@dataclass
class StreamChunks:
    stream: StreamName
    records: list[ChunkRecord]  # sorted by index, deduped
    paths: list[Path]
    gaps: list[Gap]

    def join(self) -> bytes:
        """Concatenate payloads in index order (only meaningful when there are no gaps)."""
        return b"".join(p.read_bytes() for p in self.paths)


@dataclass
class Bundle:
    root: Path
    manifest: Manifest
    events: list[Event]  # captured events, sorted by seq, one per seq
    duplicates: int = 0
    conflicts: list[Event] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    torn_tail: bool = False
    media: dict[StreamName, StreamChunks] = field(default_factory=dict)

    @property
    def ended(self) -> bool:
        return self.manifest.end is not None

    @property
    def complete(self) -> bool:
        """`end` received, and every seq and chunk up to the declared finals is present."""
        if self.manifest.end is None or self.gaps:
            return False
        return all(not chunks.gaps for chunks in self.media.values())

    def event(self, event_id: str) -> Event | None:
        return next((e for e in self.events if e.id == event_id), None)

    def read_derived_events(self, name: str) -> list[Event]:
        """Events in derived/<name> (JSONL), sorted by t."""
        lines, _ = _read_jsonl_lines(self.root / "derived" / name)
        return sorted((parse_event(ln) for ln in lines), key=lambda e: e.t)


def read_bundle(root: Path) -> Bundle:
    manifest = read_manifest(root)
    lines, torn = _read_jsonl_lines(root / EVENTS)

    by_seq: dict[int, Event] = {}
    canonical: dict[int, str] = {}
    duplicates = 0
    conflicts: list[Event] = []
    for line in lines:
        ev = parse_event(line)
        if ev.source != "extension" or ev.seq is None:
            raise BundleError(f"non-captured event in {EVENTS}: {ev.id}")
        dumped = dump_event(ev)
        if ev.seq in by_seq:
            if canonical[ev.seq] == dumped:
                duplicates += 1
            else:
                conflicts.append(ev)
            continue
        by_seq[ev.seq] = ev
        canonical[ev.seq] = dumped

    conflict_lines, _ = _read_jsonl_lines(root / CONFLICTS)
    conflicts.extend(parse_event(ln) for ln in conflict_lines)

    end = manifest.end
    gaps = find_gaps(set(by_seq), 1, end.final_seq if end else None)

    media: dict[StreamName, StreamChunks] = {}
    for stream in STREAMS:
        stream_dir = root / MEDIA / stream
        if not stream_dir.exists():
            continue
        recs: dict[int, ChunkRecord] = {}
        for line in _read_jsonl_lines(stream_dir / CHUNK_INDEX)[0]:
            rec = ChunkRecord.model_validate_json(line)
            recs.setdefault(rec.index, rec)
        info = getattr(manifest.media, stream)
        ext = chunk_extension(info.mime if info else None)
        ordered = [recs[i] for i in sorted(recs)]
        final = end.final_chunk.get(stream) if end else None
        media[stream] = StreamChunks(
            stream=stream,
            records=ordered,
            paths=[stream_dir / chunk_filename(r.index, ext) for r in ordered],
            gaps=find_gaps(set(recs), 0, final),
        )

    return Bundle(
        root=root,
        manifest=manifest,
        events=[by_seq[s] for s in sorted(by_seq)],
        duplicates=duplicates,
        conflicts=conflicts,
        gaps=gaps,
        torn_tail=torn,
        media=media,
    )


def dumps_jsonl(events: list[Event]) -> str:
    return "".join(dump_event(e) + "\n" for e in events)


def loads_jsonl(text: str) -> list[Event]:
    return [parse_event(ln) for ln in text.splitlines() if ln.strip()]


__all__ = [
    "AppendResult",
    "Bundle",
    "BundleError",
    "BundleWriter",
    "ChunkRecord",
    "Gap",
    "StreamChunks",
    "contiguous_prefix",
    "dumps_jsonl",
    "find_gaps",
    "loads_jsonl",
    "read_bundle",
    "read_manifest",
    "write_manifest",
]

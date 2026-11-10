"""Import a bundle zip, and the ingest stage (validate, report gaps, join media chunks).

Live WebSocket ingest is build-plan step 6; v0 imports the extension's exported zip.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path

from engine.files import write_bytes_atomic, write_model
from engine.models import AudioIngest, GapRange, IngestReport
from engine.paths import SessionPaths, sessions_dir
from ic_schema.bundle import Bundle, read_bundle
from ic_schema.manifest import SESSION_ID_PATTERN
from ic_schema.version import SCHEMA_VERSION, is_compatible

MAX_ENTRIES = 20_000
MAX_TOTAL_BYTES = 4 * 1024**3
MAX_RATIO = 200  # uncompressed / compressed, checked for entries over 1 MiB
COLLAPSED_AT_ZERO = 3  # this many captured events at exactly t=0 means a clock problem


class IngestError(Exception):
    pass


def _check_entries(zf: zipfile.ZipFile) -> str:
    """Validate every entry; return the single top-level folder name."""
    infos = zf.infolist()
    if not infos:
        raise IngestError("zip is empty")
    if len(infos) > MAX_ENTRIES:
        raise IngestError(f"zip has {len(infos)} entries (limit {MAX_ENTRIES})")
    total = 0
    tops: set[str] = set()
    for info in infos:
        name = info.filename
        parts = name.replace("\\", "/").split("/")
        if name.startswith(("/", "\\")) or ":" in parts[0] or ".." in parts:
            raise IngestError(f"unsafe path in zip: {name!r}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise IngestError(f"symlink in zip: {name!r}")
        total += info.file_size
        if (
            info.file_size > 1024**2
            and info.compress_size
            and info.file_size / info.compress_size > MAX_RATIO
        ):
            raise IngestError(f"suspicious compression ratio for {name!r}")
        tops.add(parts[0])
    if total > MAX_TOTAL_BYTES:
        raise IngestError(f"zip expands to {total} bytes (limit {MAX_TOTAL_BYTES})")
    if len(tops) != 1:
        raise IngestError(f"zip must hold exactly one session_<id>/ folder, found {sorted(tops)}")
    return tops.pop()


def import_zip(zip_path: Path, data_dir: Path, *, replace: bool = False) -> Path:
    """Extract a session zip into <data_dir>/sessions/session_<id>/ atomically."""
    with zipfile.ZipFile(zip_path) as zf:
        top = _check_entries(zf)
        if not top.startswith("session_") or not re.fullmatch(
            SESSION_ID_PATTERN, top[len("session_") :]
        ):
            raise IngestError(f"top-level folder must be session_<id>, got {top!r}")
        try:
            manifest = json.loads(zf.read(f"{top}/manifest.json"))
        except KeyError as e:
            raise IngestError("zip has no manifest.json") from e
        if f"session_{manifest.get('session_id')}" != top:
            raise IngestError("manifest session_id does not match the folder name")

        base = sessions_dir(data_dir)
        base.mkdir(parents=True, exist_ok=True)
        target = base / top
        if target.exists() and not replace:
            raise IngestError(f"{target} already exists (use --replace to overwrite)")
        staging = base / f".importing-{top}"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        try:
            zf.extractall(staging)
            if target.exists():
                shutil.rmtree(target)
            os.replace(staging / top, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return target


def _warnings(b: Bundle, audio: AudioIngest | None) -> list[str]:
    w: list[str] = []
    if not b.ended:
        w.append("session never ended cleanly (no end record): treated as incomplete")
    if b.gaps:
        w.append(f"missing events: seq {', '.join(f'{g.first}-{g.last}' for g in b.gaps)}")
    if b.conflicts:
        w.append(f"{len(b.conflicts)} conflicting duplicate event(s) were rejected")
    if b.torn_tail:
        w.append("events.jsonl ends with a partial line (ignored)")
    caps = b.manifest.capabilities
    if caps.audio and audio is None:
        w.append("capabilities.audio is true but the bundle has no audio chunks")
    if audio and audio.chunk_gaps:
        w.append("audio has missing chunks: the joined file may not decode past the first gap")
    # Captures stamped before t0 are clamped to t=0. Extensions since decision 002 E16 also set
    # confidence 0; older ones did not, so a pile-up at exactly t=0 is the other tell.
    at_zero = [e for e in b.events if e.t == 0 and e.kind != "session_start"]
    flagged = [e for e in at_zero if e.confidence == 0]
    if flagged or len(at_zero) >= COLLAPSED_AT_ZERO:
        w.append(
            f"{len(at_zero)} event(s) stamped at t=0: capture clock problem, timings in this "
            "session are unreliable (fixed in extension decision 002 E16)"
        )
    return w


def run(paths: SessionPaths) -> IngestReport:
    b = read_bundle(paths.root)
    m = b.manifest
    if not is_compatible(m.schema_version):
        raise IngestError(
            f"schema_version {m.schema_version} is not compatible with {SCHEMA_VERSION}"
        )

    audio: AudioIngest | None = None
    chunks = b.media.get("audio")
    if chunks and chunks.records:
        data = chunks.join()
        write_bytes_atomic(paths.audio, data)
        audio = AudioIngest(
            chunks=len(chunks.records),
            chunk_gaps=[GapRange(first=g.first, last=g.last) for g in chunks.gaps],
            bytes=len(data),
            joined=True,
            offset_s=m.media.audio.offset_s if m.media.audio else None,
        )
    elif paths.audio.exists():
        paths.audio.unlink()

    report = IngestReport(
        session_id=m.session_id,
        schema_version=m.schema_version,
        compatible=True,
        ended=b.ended,
        complete=b.complete,
        events=len(b.events),
        seq_gaps=[GapRange(first=g.first, last=g.last) for g in b.gaps],
        duplicates=b.duplicates,
        conflicts=len(b.conflicts),
        torn_tail=b.torn_tail,
        audio=audio,
    )
    report.warnings = _warnings(b, audio)
    write_model(paths.d("ingest.json"), report)
    return report

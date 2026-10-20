"""Write silent audio chunks into a fixture bundle, the way the extension would.

Encodes silence with ffmpeg as one WebM/Opus stream covering the manifest's audio span
(offset_s to the session_end event), then cuts it into byte slices, one per 10 s timeslice.
That matches MediaRecorder: chunks are opaque slices of one stream, only chunk 0 has the
container header, and concatenating them in order reproduces the file.

    make fixtures-audio
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ic_schema.bundle import MEDIA, BundleWriter, read_bundle, write_manifest
from ic_schema.manifest import EndInfo
from ic_schema.protocol import MediaChunkHeader

TIMESLICE_S = 10.0


def encode_silence(duration_s: float) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "silence.webm"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                "-t", f"{duration_s:.3f}",
                "-c:a", "libopus", "-b:a", "12k",
                "-fflags", "+bitexact", "-flags:a", "+bitexact",
                str(out),
            ],
            check=True,
        )  # fmt: skip
        return out.read_bytes()


def main(root: Path) -> None:
    bundle = read_bundle(root)
    audio = bundle.manifest.media.audio
    if audio is None or audio.offset_s is None:
        raise SystemExit("manifest has no audio stream with offset_s")
    end_t = next(e.t for e in bundle.events if e.kind == "session_end")
    duration = end_t - audio.offset_s
    n = math.ceil(duration / TIMESLICE_S)

    data = encode_silence(duration)
    shutil.rmtree(root / MEDIA / "audio", ignore_errors=True)
    writer = BundleWriter.open(root)
    step = math.ceil(len(data) / n)
    for i in range(n):
        start_ms = round((audio.offset_s + i * TIMESLICE_S) * 1000)
        header = MediaChunkHeader(stream="audio", chunk_index=i, start_ms=start_ms)
        writer.write_chunk(header, data[i * step : (i + 1) * step])

    end = bundle.manifest.end or EndInfo(final_seq=bundle.events[-1].seq or 0)
    manifest = bundle.manifest.model_copy(
        update={"end": end.model_copy(update={"final_chunk": {**end.final_chunk, "audio": n - 1}})}
    )
    write_manifest(root, manifest)
    print(f"wrote {n} chunks ({len(data)} bytes, {duration:.2f} s) to {root / MEDIA / 'audio'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

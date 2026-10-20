"""WebSocket protocol for `WS /ingest`.

Text frames are JSON objects tagged by `type`. Binary frames are media chunks: a fixed 16-byte
header (`MediaChunkHeader`) followed by the raw MediaRecorder bytes.

The pairing token travels in the connection URL (`/ingest?token=...`), checked together with the
`Origin` header before the socket is accepted; it is never part of a message.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, TypeAdapter

from ic_schema.events import Event
from ic_schema.manifest import SESSION_ID_PATTERN, Capabilities, ClockOrigin, MediaInfo, StreamName


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChunkRef(_Msg):
    stream: StreamName
    index: int = Field(ge=0)


# --- extension -> engine --------------------------------------------------------------------


class Hello(_Msg):
    """Open or resume a session. Carries what the engine needs to write manifest.json."""

    type: Literal["hello"] = "hello"
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    schema_version: str
    adapter: str = Field(description="Site adapter module name, e.g. 'leetcode'.")
    capabilities: Capabilities
    clock_origin: ClockOrigin
    media: MediaInfo = Field(default_factory=MediaInfo)
    resume_from: int | None = Field(
        default=None,
        ge=1,
        description="First seq the extension will (re)send; null on a new session.",
    )


class EventMessage(_Msg):
    type: Literal["event"] = "event"
    event: Event


class Ping(_Msg):
    type: Literal["ping"] = "ping"


class Pong(_Msg):
    type: Literal["pong"] = "pong"


class End(_Msg):
    type: Literal["end"] = "end"
    final_seq: int = Field(ge=0)
    final_chunk: dict[StreamName, int] = Field(
        default_factory=dict, description="Last chunk index per stream; omit streams not recorded."
    )


# --- engine -> extension --------------------------------------------------------------------


class Welcome(_Msg):
    """What the engine already holds: the highest seq / chunk index with no gaps below it."""

    type: Literal["welcome"] = "welcome"
    session_id: str
    last_seq: int = Field(ge=0, description="0 when nothing has been received.")
    last_chunk: dict[StreamName, int] = Field(default_factory=dict)


class Ack(_Msg):
    type: Literal["ack"] = "ack"
    seq: int | None = Field(
        default=None, ge=0, description="Every event with seq <= this is stored."
    )
    chunk: ChunkRef | None = None


ErrorCode = Literal[
    "bad_message",
    "schema_mismatch",
    "session_mismatch",
    "frame_too_large",
    "rate_limited",
    "disk_full",
    "internal",
]


class ErrorMessage(_Msg):
    """Origin and token failures close the socket with code 4403 instead of sending an error."""

    type: Literal["error"] = "error"
    code: ErrorCode
    retryable: bool
    message: str | None = None


ClientMessage = Annotated[Hello | EventMessage | Ping | Pong | End, Field(discriminator="type")]
ServerMessage = Annotated[Welcome | Ack | Ping | Pong | ErrorMessage, Field(discriminator="type")]


class AnyClientMessage(RootModel[ClientMessage]):
    """Text frame sent by the extension."""


class AnyServerMessage(RootModel[ServerMessage]):
    """Text frame sent by the engine."""


CLIENT_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
SERVER_ADAPTER: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)


def parse_client_message(raw: str | bytes) -> ClientMessage:
    return CLIENT_ADAPTER.validate_json(raw)


def parse_server_message(raw: str | bytes) -> ServerMessage:
    return SERVER_ADAPTER.validate_json(raw)


# --- binary media frames --------------------------------------------------------------------

STREAM_IDS: dict[StreamName, int] = {"audio": 0, "video": 1}
STREAM_NAMES: dict[int, StreamName] = {v: k for k, v in STREAM_IDS.items()}


class HeaderError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MediaChunkHeader:
    """16-byte header that prefixes every binary frame. All fields big-endian.

    ======  ====  ===========  ====================================================
    offset  size  field        meaning
    ======  ====  ===========  ====================================================
    0       1     version      header layout version, currently 1
    1       1     stream       0 = audio, 1 = video
    2       2     reserved     must be 0
    4       4     chunk_index  u32, per stream, starting at 0, contiguous
    8       8     start_ms     u64, chunk start in ms from session_start
    ======  ====  ===========  ====================================================

    The payload is the MediaRecorder blob as emitted. Only chunk 0 carries the container header;
    concatenating payloads in index order reproduces the stream.
    """

    FORMAT: ClassVar[str] = ">BBHIQ"
    SIZE: ClassVar[int] = 16
    VERSION: ClassVar[int] = 1

    stream: StreamName
    chunk_index: int
    start_ms: int

    def pack(self) -> bytes:
        if not 0 <= self.chunk_index < 2**32:
            raise HeaderError(f"chunk_index out of range: {self.chunk_index}")
        if not 0 <= self.start_ms < 2**64:
            raise HeaderError(f"start_ms out of range: {self.start_ms}")
        return struct.pack(
            self.FORMAT, self.VERSION, STREAM_IDS[self.stream], 0, self.chunk_index, self.start_ms
        )

    @classmethod
    def unpack(cls, data: bytes) -> MediaChunkHeader:
        if len(data) < cls.SIZE:
            raise HeaderError(f"frame shorter than {cls.SIZE}-byte header: {len(data)} bytes")
        version, stream_id, reserved, index, start_ms = struct.unpack(cls.FORMAT, data[: cls.SIZE])
        if version != cls.VERSION:
            raise HeaderError(f"unsupported header version {version}")
        if reserved != 0:
            raise HeaderError("reserved header bytes must be 0")
        if stream_id not in STREAM_NAMES:
            raise HeaderError(f"unknown stream id {stream_id}")
        return cls(stream=STREAM_NAMES[stream_id], chunk_index=index, start_ms=start_ms)


assert struct.calcsize(MediaChunkHeader.FORMAT) == MediaChunkHeader.SIZE


def pack_chunk(header: MediaChunkHeader, payload: bytes) -> bytes:
    return header.pack() + payload


def unpack_chunk(frame: bytes) -> tuple[MediaChunkHeader, bytes]:
    return MediaChunkHeader.unpack(frame), frame[MediaChunkHeader.SIZE :]

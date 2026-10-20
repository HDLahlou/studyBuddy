"""Text-frame parsing and the 16-byte media chunk header."""

from __future__ import annotations

import struct

import pytest
from pydantic import ValidationError

from ic_schema.protocol import (
    EventMessage,
    HeaderError,
    MediaChunkHeader,
    pack_chunk,
    parse_client_message,
    parse_server_message,
    unpack_chunk,
)

from .samples import EVENTS


def test_header_layout_is_16_bytes_big_endian() -> None:
    h = MediaChunkHeader(stream="video", chunk_index=0x01020304, start_ms=0x0A0B0C0D0E0F)
    packed = h.pack()
    assert len(packed) == MediaChunkHeader.SIZE == 16
    assert packed == bytes(
        [1, 1, 0, 0, 0x01, 0x02, 0x03, 0x04, 0, 0, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
    )
    assert MediaChunkHeader.unpack(packed) == h


@pytest.mark.parametrize("stream", ["audio", "video"])
@pytest.mark.parametrize("index, start_ms", [(0, 0), (17, 170_350), (2**32 - 1, 2**64 - 1)])
def test_header_roundtrip(stream: str, index: int, start_ms: int) -> None:
    h = MediaChunkHeader(stream=stream, chunk_index=index, start_ms=start_ms)  # type: ignore[arg-type]
    assert MediaChunkHeader.unpack(h.pack()) == h


def test_chunk_frame_roundtrip() -> None:
    h = MediaChunkHeader(stream="audio", chunk_index=3, start_ms=30_350)
    payload = b"\x1a\x45\xdf\xa3 opaque webm bytes"
    header, body = unpack_chunk(pack_chunk(h, payload))
    assert header == h and body == payload


def test_empty_payload_allowed() -> None:
    h = MediaChunkHeader(stream="audio", chunk_index=0, start_ms=0)
    assert unpack_chunk(h.pack()) == (h, b"")


@pytest.mark.parametrize(
    "frame, match",
    [
        (b"\x01\x00", "shorter than 16"),
        (struct.pack(">BBHIQ", 2, 0, 0, 0, 0), "unsupported header version"),
        (struct.pack(">BBHIQ", 1, 0, 7, 0, 0), "reserved"),
        (struct.pack(">BBHIQ", 1, 9, 0, 0, 0), "unknown stream"),
    ],
)
def test_header_rejects_bad_frames(frame: bytes, match: str) -> None:
    with pytest.raises(HeaderError, match=match):
        MediaChunkHeader.unpack(frame)


def test_header_rejects_out_of_range() -> None:
    with pytest.raises(HeaderError):
        MediaChunkHeader(stream="audio", chunk_index=2**32, start_ms=0).pack()
    with pytest.raises(HeaderError):
        MediaChunkHeader(stream="audio", chunk_index=0, start_ms=-1).pack()


def test_event_message_nests_the_event() -> None:
    raw = EventMessage(event=EVENTS[7]).model_dump_json()
    assert raw.startswith('{"type":"event","event":{')
    msg = parse_client_message(raw)
    assert isinstance(msg, EventMessage) and msg.event == EVENTS[7]


def test_ack_carries_seq_or_chunk() -> None:
    ack = parse_server_message('{"type":"ack","chunk":{"stream":"audio","index":4}}')
    assert ack.type == "ack" and ack.seq is None and ack.chunk is not None  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "raw",
    [
        '{"type":"nudge"}',
        '{"type":"hello"}',
        '{"type":"end"}',
        '{"type":"end","final_seq":3,"final_chunk":{"screen":1}}',
        '{"type":"welcome","session_id":"s","last_seq":0}',  # server message on client channel
        '{"type":"event","event":{"id":"ev_1","t":0,"source":"extension","kind":"run"}}',  # no seq
    ],
)
def test_client_rejects(raw: str) -> None:
    with pytest.raises(ValidationError):
        parse_client_message(raw)


def test_server_rejects_bad_error_code() -> None:
    with pytest.raises(ValidationError):
        parse_server_message('{"type":"error","code":"oops","retryable":true}')

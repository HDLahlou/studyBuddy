"""Every contract model survives a JSON round trip, and invalid shapes are rejected."""

from __future__ import annotations

from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from ic_schema import events as ev
from ic_schema import report as rp
from ic_schema.events import EVENT_ADAPTER, dump_event, parse_event
from ic_schema.manifest import Manifest
from ic_schema.protocol import parse_client_message, parse_server_message
from ic_schema.version import is_compatible

from .samples import EVENTS, FULL_MANIFEST, MESSAGES, REPORT


def _event_classes() -> set[type]:
    union, _ = get_args(ev.Event)
    return set(get_args(union))


def test_samples_cover_every_event_kind() -> None:
    assert {type(e) for e in EVENTS} == _event_classes()
    assert {e.kind for e in EVENTS} == set(get_args(ev.EventKind))


@pytest.mark.parametrize("event", EVENTS, ids=lambda e: e.kind)
def test_event_roundtrip(event: ev.Event) -> None:
    raw = dump_event(event)
    back = parse_event(raw)
    assert back == event
    assert type(back) is type(event)
    assert dump_event(back) == raw


@pytest.mark.parametrize("event", EVENTS, ids=lambda e: e.kind)
def test_event_roundtrip_via_python_dict(event: ev.Event) -> None:
    assert EVENT_ADAPTER.validate_python(event.model_dump(mode="json")) == event


def test_event_defaults_fill_in() -> None:
    e = parse_event('{"id":"ev_7","t":5,"seq":7,"source":"extension","kind":"run"}')
    assert isinstance(e, ev.RunEvent)
    assert e.confidence == 1.0 and e.t_uncertainty == 0.0 and e.data.trigger is None


@pytest.mark.parametrize(
    "model",
    [FULL_MANIFEST, REPORT, *REPORT.time_sinks, REPORT.metrics, REPORT.correctness],
    ids=lambda m: type(m).__name__,
)
def test_model_roundtrip(model: BaseModel) -> None:
    back = type(model).model_validate_json(model.model_dump_json())
    assert back == model


def test_manifest_minimal_defaults(manifest: Manifest) -> None:
    back = Manifest.model_validate_json(manifest.model_dump_json())
    assert back == manifest
    assert back.end is None and back.schema_version == "1.0"


@pytest.mark.parametrize("msg", MESSAGES, ids=lambda m: f"{type(m).__name__}")
def test_protocol_message_roundtrip(msg: BaseModel) -> None:
    raw = msg.model_dump_json()
    client = msg.type in {"hello", "event", "ping", "pong", "end"}  # type: ignore[attr-defined]
    server = msg.type in {"welcome", "ack", "ping", "pong", "error"}  # type: ignore[attr-defined]
    assert client or server
    if client:
        assert parse_client_message(raw) == msg
    if server:
        assert parse_server_message(raw) == msg


# --- rejections -----------------------------------------------------------------------------


def _ext(**kw: Any) -> dict[str, Any]:
    return {"id": "ev_1", "t": 0.0, "seq": 1, "source": "extension", "kind": "undo", **kw}


@pytest.mark.parametrize(
    "raw, match",
    [
        (_ext(seq=None), "require seq"),
        (_ext(id="ev_2"), "must be 'ev_1'"),
        (_ext(source="engine"), "only extension events carry seq"),
        (_ext(t=-1), "greater than or equal"),
        (_ext(confidence=1.5), "less than or equal"),
        (_ext(kind="hint_shown"), "does not match any of the expected tags"),
        (_ext(extra=1), "Extra inputs"),
        (_ext(data={"count": 1, "raw_text": "x"}), "Extra inputs"),
        (
            _ext(kind="keystroke", data={"duration_s": 1, "counts": {"chars": "abc"}}),
            "Extra inputs",
        ),
    ],
)
def test_event_rejections(raw: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        EVENT_ADAPTER.validate_python(raw)


def test_time_sink_cannot_lose_more_than_its_span() -> None:
    sink = REPORT.time_sinks[0].model_dump()
    with pytest.raises(ValidationError, match="exceeds the span"):
        rp.TimeSink.model_validate({**sink, "time_lost_s": 1000})
    with pytest.raises(ValidationError, match="end must be >= start"):
        rp.TimeSink.model_validate({**sink, "start": 200, "end": 100, "time_lost_s": 0})


@pytest.mark.parametrize("model", [rp.TimeSink, rp.Finding])
def test_findings_require_evidence(model: type[BaseModel]) -> None:
    base = REPORT.time_sinks[0] if model is rp.TimeSink else REPORT.strengths[0]
    with pytest.raises(ValidationError, match="at least 1 item"):
        model.model_validate({**base.model_dump(), "evidence": []})


def test_manifest_rejects_unsafe_session_id(manifest: Manifest) -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({**manifest.model_dump(), "session_id": "../etc"})


def test_schema_version_compatibility() -> None:
    assert is_compatible("1.0") and is_compatible("1.7")
    assert not is_compatible("2.0") and not is_compatible("garbage")

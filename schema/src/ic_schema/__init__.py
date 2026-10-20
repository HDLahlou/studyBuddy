"""Interview Coach shared contract. Source of truth for every generated type."""

from ic_schema.events import EVENT_ADAPTER, AnyEvent, Event, EventKind, dump_event, parse_event
from ic_schema.manifest import Capabilities, ClockOrigin, Manifest, SessionMode, UserInputs
from ic_schema.protocol import MediaChunkHeader, pack_chunk, unpack_chunk
from ic_schema.report import Report, TimeSink
from ic_schema.version import SCHEMA_VERSION

__all__ = [
    "EVENT_ADAPTER",
    "SCHEMA_VERSION",
    "AnyEvent",
    "Capabilities",
    "ClockOrigin",
    "Event",
    "EventKind",
    "Manifest",
    "MediaChunkHeader",
    "Report",
    "SessionMode",
    "TimeSink",
    "UserInputs",
    "dump_event",
    "pack_chunk",
    "parse_event",
    "unpack_chunk",
]

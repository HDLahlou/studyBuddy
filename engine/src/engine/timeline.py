"""Timeline stage: derived/timeline.json, the prepared view the AI layer and GUI read.

The design's list of phase segments (each with events, signals and evidence ids), wrapped
with the session facts and metrics so it is self-contained (003 E6).
"""

from __future__ import annotations

from engine.files import read_model, write_model
from engine.models import Phases, SessionFacts, Timeline
from engine.paths import SessionPaths
from ic_schema.bundle import read_bundle
from ic_schema.report import Metrics


def run(paths: SessionPaths) -> Timeline:
    phases = read_model(paths.d("phases.json"), Phases)
    tl = Timeline(
        session_id=read_bundle(paths.root).manifest.session_id,
        facts=read_model(paths.d("facts.json"), SessionFacts),
        metrics=read_model(paths.d("metrics.json"), Metrics),
        segments=phases.segments,
        tail=phases.tail,
    )
    write_model(paths.d("timeline.json"), tl)
    return tl

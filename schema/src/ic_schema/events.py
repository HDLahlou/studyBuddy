"""Canonical event.

Every event shares the envelope fields in `_EventBase`; `kind` selects a typed `data` payload.
Times are float seconds from `session_start` on the extension's single clock.

Extension events carry a contiguous `seq` (starting at 1) and the id `ev_<seq>`. Events produced
later by the engine or Whisper have no `seq` and live under `derived/`, never in `events.jsonl`.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, RootModel, TypeAdapter, model_validator

Source = Literal["extension", "engine", "whisper", "user"]

Verdict = Literal[
    "accepted",
    "wrong_answer",
    "runtime_error",
    "compile_error",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "output_limit_exceeded",
    "unknown",
]
"""Normalized platform verdict. For a `run`, "accepted" means every example case passed."""


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- payloads -------------------------------------------------------------------------------


class SessionStartData(_Data):
    url: str | None = None


class SessionEndData(_Data):
    reason: Literal["user_stop", "tab_closed", "navigated_away", "timeout"]


class Example(_Data):
    input: str
    output: str
    explanation: str | None = None


class ProblemLoadedData(_Data):
    platform: str
    slug: str = Field(description="Platform problem slug; platform + slug keys repeat attempts.")
    url: str
    title: str
    difficulty: Literal["easy", "medium", "hard", "unknown"] = "unknown"
    statement: str | None = None
    examples: list[Example] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class CodeSnapshotData(_Data):
    code: str = Field(description="Full editor text.")
    language: str | None = Field(
        default=None,
        description=(
            "Editor language of this snapshot. Set when it differs from Capabilities.language, "
            "and on every snapshot taken before the session language is locked (at the first "
            "edit, run or submit). Absent means Capabilities.language."
        ),
    )
    reason: Literal["initial", "debounce", "periodic", "run", "submit"]


class CodeDiffData(_Data):
    from_id: str
    to_id: str
    added_lines: int = Field(ge=0)
    deleted_lines: int = Field(ge=0)
    unified_diff: str


class KeyCounts(_Data):
    insert: int = Field(default=0, ge=0)
    delete: int = Field(default=0, ge=0)
    newline: int = Field(default=0, ge=0)
    navigation: int = Field(default=0, ge=0)
    shortcut: int = Field(default=0, ge=0)


class KeystrokeData(_Data):
    """One burst of editor-scoped keys. `t` is the burst start. Never raw characters."""

    duration_s: float = Field(ge=0)
    counts: KeyCounts


class PasteData(_Data):
    """Size only; the pasted text is visible in the next code snapshot."""

    chars: int = Field(ge=0)
    lines: int = Field(ge=0)


class UndoData(_Data):
    count: int = Field(default=1, ge=1)


class RunData(_Data):
    trigger: Literal["click", "shortcut"] | None = None


class SubmitData(_Data):
    trigger: Literal["click", "shortcut"] | None = None


class _ResultFields(_Data):
    verdict: Verdict
    verdict_raw: str | None = Field(
        default=None, description="Verdict text as the platform shows it."
    )
    passed_cases: int | None = Field(default=None, ge=0)
    total_cases: int | None = Field(default=None, ge=0)
    failing_input: str | None = None
    expected_output: str | None = None
    actual_output: str | None = None
    stdout: str | None = None
    error_message: str | None = None
    runtime_ms: float | None = Field(default=None, ge=0)
    memory_mb: float | None = Field(default=None, ge=0)


class RunResultData(_ResultFields):
    run_id: str = Field(description="Id of the `run` event this result answers.")


class SubmitResultData(_ResultFields):
    submit_id: str = Field(description="Id of the `submit` event this result answers.")


class FocusChangeData(_Data):
    target: Literal["tab", "window", "editor"]
    state: Literal["away", "back"]


class Word(_Data):
    w: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    p: float | None = Field(default=None, ge=0, le=1)


class SpeechData(_Data):
    """Transcript segment. `t` is the segment start; `end` is on the same session clock."""

    text: str
    end: float = Field(ge=0)
    words: list[Word] | None = None
    cues: list[str] = Field(default_factory=list, description='Cue phrases, e.g. "wait".')


class IdleData(_Data):
    end: float = Field(ge=0)
    duration_s: float = Field(ge=0)


class MarkerData(_Data):
    label: Literal["stuck", "idea", "done"]
    origin: Literal["hotkey", "speech", "review"]
    text: str | None = Field(default=None, description="Spoken phrase, for origin=speech.")


# --- envelope -------------------------------------------------------------------------------


class _EventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    t: float = Field(ge=0, description="Seconds from session_start.")
    seq: int | None = Field(
        default=None, ge=1, description="Capture sequence number; required for source=extension."
    )
    source: Source
    confidence: float = Field(default=1.0, ge=0, le=1, description="1.0 = exact.")
    t_uncertainty: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _check_seq(self) -> Self:
        if self.source == "extension":
            if self.seq is None:
                raise ValueError("extension events require seq")
            if self.id != f"ev_{self.seq}":
                raise ValueError(f"extension event id must be 'ev_{self.seq}', got {self.id!r}")
        elif self.seq is not None:
            raise ValueError("only extension events carry seq")
        return self


class SessionStartEvent(_EventBase):
    kind: Literal["session_start"]
    data: SessionStartData = Field(default_factory=SessionStartData)


class SessionEndEvent(_EventBase):
    kind: Literal["session_end"]
    data: SessionEndData


class ProblemLoadedEvent(_EventBase):
    kind: Literal["problem_loaded"]
    data: ProblemLoadedData


class CodeSnapshotEvent(_EventBase):
    kind: Literal["code_snapshot"]
    data: CodeSnapshotData


class CodeDiffEvent(_EventBase):
    kind: Literal["code_diff"]
    data: CodeDiffData


class KeystrokeEvent(_EventBase):
    kind: Literal["keystroke"]
    data: KeystrokeData


class PasteEvent(_EventBase):
    kind: Literal["paste"]
    data: PasteData


class UndoEvent(_EventBase):
    kind: Literal["undo"]
    data: UndoData = Field(default_factory=UndoData)


class RunEvent(_EventBase):
    kind: Literal["run"]
    data: RunData = Field(default_factory=RunData)


class SubmitEvent(_EventBase):
    kind: Literal["submit"]
    data: SubmitData = Field(default_factory=SubmitData)


class RunResultEvent(_EventBase):
    kind: Literal["run_result"]
    data: RunResultData


class SubmitResultEvent(_EventBase):
    kind: Literal["submit_result"]
    data: SubmitResultData


class FocusChangeEvent(_EventBase):
    kind: Literal["focus_change"]
    data: FocusChangeData


class SpeechEvent(_EventBase):
    kind: Literal["speech"]
    data: SpeechData


class IdleEvent(_EventBase):
    kind: Literal["idle"]
    data: IdleData


class MarkerEvent(_EventBase):
    kind: Literal["marker"]
    data: MarkerData


Event = Annotated[
    SessionStartEvent
    | SessionEndEvent
    | ProblemLoadedEvent
    | CodeSnapshotEvent
    | CodeDiffEvent
    | KeystrokeEvent
    | PasteEvent
    | UndoEvent
    | RunEvent
    | SubmitEvent
    | RunResultEvent
    | SubmitResultEvent
    | FocusChangeEvent
    | SpeechEvent
    | IdleEvent
    | MarkerEvent,
    Field(discriminator="kind"),
]

EventKind = Literal[
    "session_start",
    "session_end",
    "problem_loaded",
    "code_snapshot",
    "code_diff",
    "keystroke",
    "paste",
    "undo",
    "run",
    "submit",
    "run_result",
    "submit_result",
    "focus_change",
    "speech",
    "idle",
    "marker",
]


class AnyEvent(RootModel[Event]):
    """Root wrapper so the union gets a named JSON Schema / generated type."""


EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(raw: str | bytes) -> Event:
    return EVENT_ADAPTER.validate_json(raw)


def dump_event(event: Event) -> str:
    """Canonical one-line JSON for events.jsonl (defaults included, stable key order)."""
    return event.model_dump_json()

"""Atomic writes for derived files, so a crashed stage never leaves a half-written output."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

from ic_schema.bundle import loads_jsonl
from ic_schema.events import Event, dump_event


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_model(path: Path, model: BaseModel) -> None:
    write_text_atomic(path, model.model_dump_json(indent=2) + "\n")


def read_model[M: BaseModel](path: Path, cls: type[M]) -> M:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run the stage that writes it first")
    return cls.model_validate_json(path.read_text(encoding="utf-8"))


def write_events(path: Path, events: Iterable[Event]) -> None:
    write_text_atomic(path, "".join(dump_event(e) + "\n" for e in events))


def read_events(path: Path) -> list[Event]:
    return loads_jsonl(path.read_text(encoding="utf-8")) if path.exists() else []

"""Where sessions live, and the files each pipeline stage reads and writes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_DATA_DIR = "IC_DATA_DIR"


def default_data_dir() -> Path:
    """~/Library/Application Support/InterviewCoach on macOS; platform equivalents elsewhere."""
    env = os.environ.get(ENV_DATA_DIR)
    if env:
        return Path(env).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "InterviewCoach"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", home)) / "InterviewCoach"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "interview-coach"


def sessions_dir(data_dir: Path) -> Path:
    return data_dir / "sessions"


class SessionPaths:
    """Files under one session bundle. Stages write only under derived/ (CLAUDE.md)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.derived = root / "derived"

    def d(self, name: str) -> Path:
        return self.derived / name

    @property
    def audio(self) -> Path:
        return self.d("audio.webm")

    @property
    def pipeline(self) -> Path:
        return self.d("pipeline.json")


def resolve_session(arg: str, data_dir: Path) -> Path:
    """A session folder path, or a session id / folder name under the data dir."""
    p = Path(arg).expanduser()
    if (p / "manifest.json").exists():
        return p
    base = sessions_dir(data_dir)
    for candidate in (base / arg, base / f"session_{arg}"):
        if (candidate / "manifest.json").exists():
            return candidate
    raise FileNotFoundError(f"no session bundle at {arg!r} or under {base}")

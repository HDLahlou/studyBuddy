"""Spoken cue phrases and marker phrases (decision 003 E5).

Cues are tags on a speech segment ("wait", "why is"). Marker phrases are a deliberately small,
conservative set: a match creates a `marker` event, the hands-free way to flag a moment, so a
false positive is worse than a miss. Edit these lists to tune.
"""

from __future__ import annotations

import re

CUE_PHRASES: tuple[str, ...] = (
    "wait",
    "hold on",
    "hmm",
    "why is",
    "why does",
    "let me think",
    "let me trace",
    "what if",
    "okay so",
)

MARKER_PHRASES: dict[str, tuple[str, ...]] = {
    "stuck": ("i'm stuck", "i am stuck", "i don't know how", "i have no idea how"),
    "idea": ("oh i see", "i got it", "i know what to do", "that's it"),
    "done": ("i'm done", "i am done"),
}

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})


def normalize_words(text: str) -> list[str]:
    """Lowercase words, keeping in-word apostrophes, without punctuation."""
    text = text.translate(_APOSTROPHES).lower()
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)


def _find(words: list[str], phrase: str) -> int | None:
    target = normalize_words(phrase)
    n = len(target)
    for i in range(len(words) - n + 1):
        if words[i : i + n] == target:
            return i
    return None


def find_cues(text: str) -> list[str]:
    words = normalize_words(text)
    return [p for p in CUE_PHRASES if _find(words, p) is not None]


def find_markers(text: str) -> list[tuple[str, str, int]]:
    """(label, phrase, index of the phrase's first word) for each marker phrase present."""
    words = normalize_words(text)
    found: list[tuple[str, str, int]] = []
    for label, phrases in MARKER_PHRASES.items():
        for phrase in phrases:
            i = _find(words, phrase)
            if i is not None:
                found.append((label, phrase, i))
                break  # one marker per label per segment
    return sorted(found, key=lambda f: f[2])

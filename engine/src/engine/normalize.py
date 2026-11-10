"""Normalize stage: code diffs and redundant snapshots (decision 003 E1).

- A `code_diff` event (source "engine", id df_<n>) for each pair of consecutive snapshots whose
  code differs, in timeline order. Line-level, with difflib. Language-agnostic: code is text.
- Snapshots identical to the previous one are listed as redundant when they were taken by the
  timer (debounce/periodic). They stay in the bundle, so evidence ids always resolve, but
  timeline segments leave them out. Forced snapshots (initial/run/submit) are never redundant:
  they tie exact code to a run.

Keystroke bursts are merged into typing spans by the signals stage, not here, so no new
keystroke events double-count keys.
"""

from __future__ import annotations

import difflib

from engine.files import write_events, write_model
from engine.models import NormalizeReport
from engine.paths import SessionPaths
from ic_schema.bundle import read_bundle
from ic_schema.events import CodeDiffData, CodeDiffEvent, CodeSnapshotEvent

DIFF_CONTEXT_LINES = 1


def line_diff(before: str, after: str) -> tuple[int, int, str]:
    a, b = before.splitlines(), after.splitlines()
    added = deleted = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            deleted += i2 - i1
        if op in ("replace", "insert"):
            added += j2 - j1
    text = "\n".join(difflib.unified_diff(a, b, lineterm="", n=DIFF_CONTEXT_LINES))
    return added, deleted, text


def run(paths: SessionPaths) -> NormalizeReport:
    b = read_bundle(paths.root)
    snapshots = [e for e in b.timeline(derived=[]) if isinstance(e, CodeSnapshotEvent)]
    diffs: list[CodeDiffEvent] = []
    redundant: list[str] = []
    prev: CodeSnapshotEvent | None = None
    total_added = total_deleted = 0
    for snap in snapshots:
        if prev is not None and snap.data.code == prev.data.code:
            if snap.data.reason in ("debounce", "periodic"):
                redundant.append(snap.id)
            continue
        if prev is not None:
            added, deleted, text = line_diff(prev.data.code, snap.data.code)
            total_added += added
            total_deleted += deleted
            diffs.append(
                CodeDiffEvent(
                    id=f"df_{len(diffs) + 1}",
                    t=snap.t,
                    source="engine",
                    confidence=snap.confidence,
                    t_uncertainty=snap.t_uncertainty,
                    kind="code_diff",
                    data=CodeDiffData(
                        from_id=prev.id,
                        to_id=snap.id,
                        added_lines=added,
                        deleted_lines=deleted,
                        unified_diff=text,
                    ),
                )
            )
        prev = snap

    write_events(paths.d("diffs.jsonl"), diffs)
    report = NormalizeReport(
        snapshots=len(snapshots),
        redundant_snapshots=redundant,
        diffs=len(diffs),
        lines_added=total_added,
        lines_deleted=total_deleted,
    )
    write_model(paths.d("normalize.json"), report)
    return report

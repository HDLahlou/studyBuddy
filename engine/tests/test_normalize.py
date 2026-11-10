from __future__ import annotations

import json
from collections.abc import Callable

from engine import normalize
from engine.files import read_events
from engine.normalize import line_diff
from engine.paths import SessionPaths
from ic_schema.events import CodeDiffEvent


def test_line_diff_counts() -> None:
    before = "a\nb\nc\n"
    after = "a\nc\nd\ne\n"
    added, deleted, text = line_diff(before, after)
    assert (added, deleted) == (2, 1)
    assert "-b" in text and "+d" in text and "+e" in text
    assert line_diff("x", "x")[:2] == (0, 0)


def test_basic_diffs(bundle_copy: Callable[[str], SessionPaths]) -> None:
    paths = bundle_copy("two_sum_basic")
    report = normalize.run(paths)
    diffs = [e for e in read_events(paths.d("diffs.jsonl")) if isinstance(e, CodeDiffEvent)]
    # 11 snapshots; the 3 run/submit snapshots repeat the code before them: 7 distinct changes.
    assert report.snapshots == 11 and report.diffs == len(diffs) == 7
    assert report.redundant_snapshots == []
    assert [d.id for d in diffs] == [f"df_{i}" for i in range(1, 8)]
    assert all(d.source == "engine" and d.seq is None for d in diffs)
    # The fix moved `seen[n] = i` below the check: one line deleted, one added.
    fix = next(d for d in diffs if d.data.to_id == "ev_24")
    assert (fix.data.from_id, fix.data.added_lines, fix.data.deleted_lines) == ("ev_22", 1, 1)
    assert fix.t == 138.3
    assert report.lines_added == sum(d.data.added_lines for d in diffs)


def test_timer_duplicates_are_redundant_but_forced_ones_are_not(
    bundle_copy: Callable[[str], SessionPaths],
) -> None:
    paths = bundle_copy("two_sum_basic")
    lines = (paths.root / "events.jsonl").read_text().splitlines()
    ev12 = json.loads(lines[11])  # debounce snapshot of the buggy code at t=75.8
    dup = {
        **ev12,
        "id": "ev_32",
        "seq": 32,
        "t": 76.5,
        "data": {**ev12["data"], "reason": "periodic"},
    }
    end = json.loads(lines[-1])
    end.update(id="ev_33", seq=33)
    (paths.root / "events.jsonl").write_text(
        "\n".join([*lines[:-1], json.dumps(dup), json.dumps(end)]) + "\n"
    )
    m = json.loads((paths.root / "manifest.json").read_text())
    m["end"]["final_seq"] = 33
    (paths.root / "manifest.json").write_text(json.dumps(m))

    report = normalize.run(paths)
    assert report.redundant_snapshots == ["ev_32"]  # ev_14 (run, identical) is kept
    assert (report.snapshots, report.diffs) == (12, 7)


def test_normalize_is_rerunnable(bundle_copy: Callable[[str], SessionPaths]) -> None:
    paths = bundle_copy("two_sum_live_order")
    first = normalize.run(paths)
    text = paths.d("diffs.jsonl").read_text()
    assert normalize.run(paths) == first
    assert paths.d("diffs.jsonl").read_text() == text

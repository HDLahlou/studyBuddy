"""Generate fixture variants of two_sum_basic in the shape the real extension writes.

The extension numbers events in *arrival* order (decisions 002 E2): a keystroke burst is stamped
with its start but stored about 1 s after its last key, and a run/submit result is stored after
its panel settles. two_sum_basic is ordered by time; these variants renumber seq (and ids, and
result references) by arrival:

  two_sum_live_order     same session, arrival-ordered seq
  two_sum_failed_scrape  the first run's result never settled: verdict "unknown", confidence 0,
                         recorded at the 30 s timeout (bug class "failed result scrape")

Both have no audio and no derived files. Re-run after changing two_sum_basic:

    cd schema && uv run python ../fixtures/tools/make_variant_fixtures.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1]
BASE = FIXTURES / "two_sum_basic"

BURST_QUIET_S = 1.0  # extension burst flush delay (002 E5)
RESULT_SETTLE_S = 0.25  # one poll after the verdict appears (002 E6)
RESULT_TIMEOUT_S = 30.0  # failed scrape (002 E6)


def load_events() -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in (BASE / "events.jsonl").read_text().splitlines() if ln.strip()]


def arrival(e: dict[str, Any]) -> float:
    t = float(e["t"])
    if e["kind"] == "keystroke":
        return t + float(e["data"]["duration_s"]) + BURST_QUIET_S
    if e["kind"] in ("run_result", "submit_result"):
        return t + RESULT_SETTLE_S
    return t


def renumber(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda e: (arrival(e), e["seq"]))
    new_id = {e["id"]: f"ev_{i}" for i, e in enumerate(ordered, 1)}
    out = []
    for i, e in enumerate(ordered, 1):
        e = json.loads(json.dumps(e))
        e["seq"], e["id"] = i, f"ev_{i}"
        for ref in ("run_id", "submit_id"):
            if ref in e["data"]:
                e["data"][ref] = new_id[e["data"][ref]]
        out.append(e)
    return out


def write(name: str, events: list[dict[str, Any]]) -> None:
    root = FIXTURES / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir()
    manifest = json.loads((BASE / "manifest.json").read_text())
    manifest["session_id"] = f"fx_{name}"
    manifest["capabilities"]["audio"] = False
    manifest["media"] = {"audio": None, "video": None}
    manifest["end"] = {"final_seq": len(events), "final_chunk": {}}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lines = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events)
    (root / "events.jsonl").write_text(lines)
    print(f"wrote {root} ({len(events)} events)")


def failed_scrape(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = json.loads(json.dumps(events))
    first_result = next(e for e in events if e["kind"] == "run_result")
    run = next(e for e in events if e["id"] == first_result["data"]["run_id"])
    first_result.update(
        t=round(run["t"] + RESULT_TIMEOUT_S, 3),
        confidence=0.0,
        t_uncertainty=RESULT_SETTLE_S,
        data={"run_id": run["id"], "verdict": "unknown"},
    )
    return events


def main() -> None:
    base = load_events()
    write("two_sum_live_order", renumber(base))
    write("two_sum_failed_scrape", renumber(failed_scrape(base)))


if __name__ == "__main__":
    main()

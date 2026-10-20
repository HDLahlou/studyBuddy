import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BurstAggregator, categorize, isUndo, pasteSize, type Burst } from "../src/content/keystrokes";
import { SnapshotScheduler, type Snapshot } from "../src/probe/snapshots";
import { epochNow, isSkewed, toSessionT } from "../src/shared/clock";
import { newSessionId, SESSION_ID_RE } from "../src/shared/ids";

const key = (k: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }> = {}) => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...mods,
});

describe("categorize", () => {
  it.each([
    ["a", {}, "insert"],
    [" ", {}, "insert"],
    ["Tab", {}, "insert"],
    ["(", {}, "insert"],
    ["Backspace", {}, "delete"],
    ["Delete", {}, "delete"],
    ["Enter", {}, "newline"],
    ["ArrowUp", {}, "navigation"],
    ["End", {}, "navigation"],
    ["z", { metaKey: true }, "shortcut"],
    ["c", { ctrlKey: true }, "shortcut"],
    ["ArrowDown", { altKey: true }, "shortcut"],
    ["ø", { altKey: true }, "insert"],
    ["Shift", {}, null],
    ["Escape", {}, null],
    ["F5", {}, null],
  ] as const)("%s %o -> %s", (k, mods, expected) => {
    expect(categorize(key(k, mods))).toBe(expected);
  });

  it("detects undo but not redo", () => {
    expect(isUndo(key("z", { metaKey: true }))).toBe(true);
    expect(isUndo(key("Z", { ctrlKey: true }))).toBe(true);
    expect(isUndo(key("z", { metaKey: true, shiftKey: true }))).toBe(false);
    expect(isUndo(key("y", { ctrlKey: true }))).toBe(false);
    expect(isUndo(key("z"))).toBe(false);
  });

  it("measures pastes without keeping text", () => {
    expect(pasteSize("")).toEqual({ chars: 0, lines: 0 });
    expect(pasteSize("for i, n in enumerate(nums):")).toEqual({ chars: 28, lines: 1 });
    expect(pasteSize("a\nb\r\nc")).toEqual({ chars: 6, lines: 3 });
  });
});

describe("BurstAggregator", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("groups keys until a quiet gap and reports the burst start", () => {
    const bursts: Burst[] = [];
    const agg = new BurstAggregator((b) => bursts.push(b));
    agg.add("insert", 1000);
    agg.add("insert", 1200);
    agg.add("newline", 1500);
    vi.advanceTimersByTime(999);
    expect(bursts).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(bursts).toEqual([{ at: 1000, durationS: 0.5, counts: { insert: 2, newline: 1 } }]);
  });

  it("splits bursts that run past the maximum length", () => {
    const bursts: Burst[] = [];
    const agg = new BurstAggregator((b) => bursts.push(b), { quietMs: 1000, maxMs: 2000 });
    agg.add("insert", 0);
    agg.add("insert", 1500);
    agg.add("delete", 2100);
    agg.flush();
    expect(bursts.map((b) => [b.at, b.counts])).toEqual([
      [0, { insert: 2 }],
      [2100, { delete: 1 }],
    ]);
  });

  it("flush is a no-op without keys and cancels the pending timer", () => {
    const onBurst = vi.fn();
    const agg = new BurstAggregator(onBurst);
    agg.flush();
    agg.add("navigation", 10);
    agg.flush();
    vi.advanceTimersByTime(5000);
    expect(onBurst).toHaveBeenCalledTimes(1);
  });
});

describe("SnapshotScheduler", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function setup() {
    let code = "class Solution:\n";
    const snaps: Snapshot[] = [];
    const sched = new SnapshotScheduler(() => code, (s) => snaps.push(s), () => Date.now());
    return { snaps, sched, set: (c: string) => (code = c) };
  }

  it("takes an initial snapshot, then debounces changes by 500 ms", () => {
    const { snaps, sched, set } = setup();
    sched.start();
    expect(snaps.map((s) => s.reason)).toEqual(["initial"]);
    set("a");
    sched.onChange();
    vi.advanceTimersByTime(300);
    set("ab");
    sched.onChange();
    vi.advanceTimersByTime(499);
    expect(snaps).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(snaps.map((s) => [s.reason, s.code])).toEqual([
      ["initial", "class Solution:\n"],
      ["debounce", "ab"],
    ]);
    sched.stop();
  });

  it("periodic snapshots fire every 15 s during continuous typing, only when the code changed", () => {
    const { snaps, sched, set } = setup();
    sched.start();
    // Type every 400 ms for 31 s: the debounce never gets 500 ms of quiet.
    for (let i = 1; i <= 77; i++) {
      vi.advanceTimersByTime(400);
      set(`code ${i}`);
      sched.onChange();
    }
    expect(snaps.filter((s) => s.reason === "periodic")).toHaveLength(2);
    expect(snaps.filter((s) => s.reason === "debounce")).toHaveLength(0);
    // Idle afterwards: one debounce, then no periodic duplicates.
    vi.advanceTimersByTime(60_000);
    expect(snaps.map((s) => s.reason)).toEqual(["initial", "periodic", "periodic", "debounce"]);
    sched.stop();
  });

  it("forced snapshots are taken even when unchanged and cancel a pending debounce", () => {
    const { snaps, sched, set } = setup();
    sched.start();
    set("x");
    sched.onChange();
    sched.force("run");
    sched.force("run");
    vi.advanceTimersByTime(10_000);
    expect(snaps.map((s) => s.reason)).toEqual(["initial", "run", "run"]);
    sched.stop();
  });
});

describe("clock and ids", () => {
  it("stamps with the shared wall clock, so every context agrees", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-20T04:18:36.000Z"));
    expect(epochNow()).toBe(Date.parse("2026-10-20T04:18:36.000Z"));
    vi.useRealTimers();
    expect(isSkewed(1000, 2001)).toBe(true);
    expect(isSkewed(1500, 2000)).toBe(false);
  });

  it("converts epoch ms to session seconds, rounded to ms and never negative", () => {
    expect(toSessionT(1_000_084_620.0000001, 1_000_000_000)).toBe(84.62);
    expect(toSessionT(999, 1000)).toBe(0);
  });

  it("generates session ids that match the contract pattern", () => {
    const id = newSessionId("two-sum", new Date("2026-10-19T15:02:11.250Z"), () => 0.5);
    expect(id).toBe("20261019T150211Z_two-sum_ssssss");
    expect(SESSION_ID_RE.test(id)).toBe(true);
    expect(SESSION_ID_RE.test(newSessionId("weird/slug with spaces".repeat(5)))).toBe(true);
  });
});

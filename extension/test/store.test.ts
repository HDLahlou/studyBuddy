import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";

import { Recorder } from "../src/shared/session";
import { Store } from "../src/shared/store";

const T0 = 1_760_886_131_250;

let store: Store;
let recorder: Recorder;

beforeEach(async () => {
  store = await Store.open(new IDBFactory());
  recorder = new Recorder(store);
});

async function start(sessionId = "s1") {
  return recorder.start({
    tabId: 7,
    platform: "leetcode",
    adapterVersion: "0.1.0",
    slug: "two-sum",
    url: "https://leetcode.com/problems/two-sum/",
    mode: "practice",
    t0: T0,
    sessionId,
  });
}

describe("Recorder + Store", () => {
  it("writes session_start as seq 1 at t = 0", async () => {
    await start();
    const [ev] = await store.listEvents("s1");
    expect(ev).toEqual({
      id: "ev_1",
      t: 0,
      seq: 1,
      source: "extension",
      confidence: 1,
      t_uncertainty: 0,
      kind: "session_start",
      data: { url: "https://leetcode.com/problems/two-sum/" },
    });
  });

  it("assigns unique contiguous seqs under concurrent captures", async () => {
    await start();
    const evs = await Promise.all(
      Array.from({ length: 50 }, (_, i) => recorder.capture("s1", { kind: "undo", at: T0 + i * 10, data: { count: 1 } })),
    );
    const seqs = evs.map((e) => e.seq).sort((a, b) => (a ?? 0) - (b ?? 0));
    expect(seqs).toEqual(Array.from({ length: 50 }, (_, i) => i + 2));
    expect(new Set(evs.map((e) => e.id)).size).toBe(50);
    expect((await store.getSession("s1"))?.nextSeq).toBe(52);
  });

  it("keeps the seq counter across reopening the database (worker restart)", async () => {
    const factory = new IDBFactory();
    const s1 = await Store.open(factory);
    const r1 = new Recorder(s1);
    await r1.start({ tabId: 1, platform: "leetcode", adapterVersion: "0.1.0", slug: "a", url: "u", mode: "practice", t0: T0, sessionId: "s" });
    await r1.capture("s", { kind: "run", at: T0 + 1000, data: {} });
    s1.close();
    const s2 = await Store.open(factory);
    const ev = await new Recorder(s2).capture("s", { kind: "submit", at: T0 + 2000, data: {} });
    expect(ev).toMatchObject({ id: "ev_3", seq: 3, t: 2 });
  });

  describe("session language lock (E14)", () => {
    const snap = (at: number, language: string, code = "x") =>
      recorder.capture("s1", { kind: "code_snapshot", at: T0 + at, data: { code, reason: "debounce" }, language });
    const lang = (e: Awaited<ReturnType<typeof snap>>) => (e.kind === "code_snapshot" ? e.data.language : "n/a");

    it("switching from C++ to Java before typing gives a Java session; the template snapshot keeps cpp", async () => {
      // The real Valid Parentheses session: page opened in C++, switched to Java ~7 s in, then typed.
      await start();
      await recorder.patchCapabilities("s1", { language: "cpp" }); // picker reading at activation
      const template = await snap(0.36, "cpp");
      const switched = await snap(7.28, "java");
      await recorder.capture("s1", { kind: "keystroke", at: T0 + 9000, data: { duration_s: 2, counts: { insert: 5 } }, language: "java" });
      const after = await snap(12, "java");
      expect([lang(template), lang(switched), lang(after)]).toEqual(["cpp", "java", undefined]);
      expect(await store.getSession("s1")).toMatchObject({ language: "java", languageLocked: true, exactCode: true });
    });

    it("pre-lock snapshots carry the language even when it never changes", async () => {
      await start();
      await recorder.patchCapabilities("s1", { language: "python3" });
      const first = await snap(1, "python3");
      await recorder.capture("s1", { kind: "run", at: T0 + 2000, data: {}, language: "python3" });
      const later = await snap(3, "python3");
      expect([lang(first), lang(later)]).toEqual(["python3", undefined]);
    });

    it("a run or submit locks it too, falling back to the last snapshot's language", async () => {
      await start();
      await recorder.patchCapabilities("s1", { language: "cpp" });
      await snap(1, "golang");
      await recorder.capture("s1", { kind: "submit", at: T0 + 2000, data: {} }); // picker unreadable
      expect(await store.getSession("s1")).toMatchObject({ language: "golang", languageLocked: true });
    });

    it("after the lock, a later switch is recorded per snapshot and the session language stays", async () => {
      await start();
      await recorder.capture("s1", { kind: "paste", at: T0 + 500, data: { chars: 3, lines: 1 }, language: "java" });
      const other = await snap(2, "python3");
      await recorder.patchCapabilities("s1", { language: "python3" }); // e.g. page reload re-activation
      expect(lang(other)).toBe("python3");
      expect(await store.getSession("s1")).toMatchObject({ language: "java", languageLocked: true });
    });

    it("focus changes and problem loads do not lock; an untouched session keeps the provisional language", async () => {
      await start();
      await recorder.patchCapabilities("s1", { language: "cpp" });
      await recorder.capture("s1", { kind: "focus_change", at: T0 + 100, data: { target: "tab", state: "away" }, language: "java" });
      await snap(1, "java");
      expect(await store.getSession("s1")).toMatchObject({ language: "java", languageLocked: false });
    });
  });

  it("flags captures stamped well before t0 (a lagging clock) instead of passing them as exact", async () => {
    await start();
    // A tab whose clock lags by 10 minutes, as happened with a tab opened before a sleep.
    const lagging = await recorder.capture("s1", { kind: "run", at: T0 - 600_000, data: {} });
    // A capture a few ms before t0 is an ordinary race and stays exact.
    const race = await recorder.capture("s1", { kind: "submit", at: T0 - 5, data: {} });
    expect(lagging).toMatchObject({ t: 0, confidence: 0 });
    expect(race).toMatchObject({ t: 0, confidence: 1 });
    expect((await store.getSession("s1"))?.clockSkewed).toBe(1);
  });

  it("stop writes session_end once and then rejects captures", async () => {
    await start();
    await recorder.stop("s1", "user_stop", T0 + 5000);
    await recorder.stop("s1", "tab_closed", T0 + 6000);
    const evs = await store.listEvents("s1");
    expect(evs.map((e) => e.kind)).toEqual(["session_start", "session_end"]);
    expect(evs[1]).toMatchObject({ t: 5, data: { reason: "user_stop" } });
    const rec = await store.getSession("s1");
    expect(rec).toMatchObject({ status: "stopped", endSeq: 2 });
    await expect(recorder.capture("s1", { kind: "run", at: T0 + 7000, data: {} })).rejects.toThrow(/not recording/);
  });

  it("stores chunks and deletes a session completely", async () => {
    await start("keep");
    await start("drop");
    for (const sessionId of ["keep", "drop"]) {
      await store.putChunk({ sessionId, stream: "audio", index: 0, startMs: 350, bytes: new Uint8Array([1, 2]).buffer });
    }
    await store.deleteSession("drop");
    expect(await store.getSession("drop")).toBeUndefined();
    expect(await store.listEvents("drop")).toEqual([]);
    expect(await store.listChunks("drop", "audio")).toEqual([]);
    expect(await store.countChunks("keep", "audio")).toBe(1);
    expect(await store.countEvents("keep")).toBe(1);
  });

  it("marks a session left recording as interrupted", async () => {
    await start();
    await recorder.markInterrupted("s1");
    expect((await store.getSession("s1"))?.status).toBe("interrupted");
  });
});

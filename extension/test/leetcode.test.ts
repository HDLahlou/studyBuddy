// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { leetcode, normalizeVerdict, textOf } from "../src/adapters/leetcode";
import { waitForResult } from "../src/content/results";

const DOM = join(__dirname, "dom", "leetcode");

function load(name: string): Document {
  const html = readFileSync(join(DOM, name), "utf8");
  return new DOMParser().parseFromString(html, "text/html");
}

const verdictNode = (doc: Document, which: "run" | "submit") =>
  (which === "run" ? leetcode.runResult : leetcode.submitResult).verdictNode(doc)!;

describe("urls", () => {
  it.each([
    ["https://leetcode.com/problems/two-sum/", "two-sum"],
    ["https://leetcode.com/problems/two-sum/description/", "two-sum"],
    ["https://leetcode.com/problems/two-sum/submissions/208307350/", "two-sum"],
    ["https://leetcode.com/problems/two-sum", "two-sum"],
    ["https://leetcode.com/problemset/", null],
    ["https://leetcode.com/", null],
  ])("%s -> %s", (url, slug) => {
    expect(leetcode.problemKey(new URL(url))).toBe(slug);
    expect(leetcode.matches(new URL(url))).toBe(slug !== null);
  });

  it("does not match other hosts or plain http", () => {
    expect(leetcode.matches(new URL("https://leetcode.cn/problems/two-sum/"))).toBe(false);
    expect(leetcode.matches(new URL("http://leetcode.com/problems/two-sum/"))).toBe(false);
    expect(leetcode.matches(new URL("https://evil.example/problems/two-sum/"))).toBe(false);
  });
});

describe("problem page", () => {
  const doc = load("problem.html");
  const problem = leetcode.readProblem(doc, new URL("https://leetcode.com/problems/two-sum/description/"))!;

  it("reads title, slug, url and difficulty", () => {
    expect(problem).toMatchObject({
      platform: "leetcode",
      slug: "two-sum",
      url: "https://leetcode.com/problems/two-sum/",
      title: "Two Sum",
      difficulty: "easy",
    });
  });

  it("splits the statement, examples and constraints, rendering <sup> as ^", () => {
    expect(problem.statement).toMatch(/^Given an array of integers nums and an integer target/);
    expect(problem.statement).toContain("The answer can be returned in any order.");
    expect(problem.statement).not.toContain("Example");
    expect(problem.examples).toEqual([
      {
        input: "nums = [2,7,11,15], target = 9",
        output: "[0,1]",
        explanation: "Because nums[0] + nums[1] == 9, we return [0, 1].",
      },
      { input: "nums = [3,2,4], target = 6", output: "[1,2]" },
      { input: "nums = [3,3], target = 6", output: "[0,1]" },
    ]);
    expect(problem.constraints).toEqual([
      "2 <= nums.length <= 10^4",
      "-10^9 <= nums[i] <= 10^9",
      "-10^9 <= target <= 10^9",
      "Only one valid answer exists.",
    ]);
    expect(leetcode.hasStatement(problem)).toBe(true);
  });

  it("falls back to the document title when the description is not rendered", () => {
    const bare = new DOMParser().parseFromString("<title>Two Sum - LeetCode</title><body></body>", "text/html");
    const p = leetcode.readProblem(bare, new URL("https://leetcode.com/problems/two-sum/"))!;
    expect(p).toMatchObject({ title: "Two Sum", difficulty: "unknown", statement: null, examples: [], constraints: [] });
    expect(leetcode.hasStatement(p)).toBe(false);
  });

  it("reads the language from the picker and finds run/submit", () => {
    expect(leetcode.readLanguage(doc)).toBe("cpp");
    expect(leetcode.hasRunButtons(doc)).toBe(true);
    const runIcon = doc.querySelector('[data-e2e-locator="console-run-button"] svg')!;
    expect(leetcode.actionForClick(runIcon)).toBe("run");
    expect(leetcode.actionForClick(doc.querySelector('[data-e2e-locator="console-submit-button"]')!)).toBe("submit");
    expect(leetcode.actionForClick(doc.querySelector(".text-title-large")!)).toBe(null);
  });

  it("reports a pending run/submit button (LeetCode ignores clicks while it is styled cursor-not-allowed)", () => {
    const d = load("problem.html");
    expect(leetcode.actionPending(d, "run")).toBe(false);
    expect(leetcode.actionPending(d, "submit")).toBe(false);
    d.querySelector('[data-e2e-locator="console-run-button"]')!.className += " cursor-not-allowed opacity-50";
    expect(leetcode.actionPending(d, "run")).toBe(true);
    expect(leetcode.actionPending(d, "submit")).toBe(false);
  });

  it("maps LeetCode's run/submit shortcuts", () => {
    const k = (key: string, m: Partial<KeyboardEventInit> = {}) => new KeyboardEvent("keydown", { key, ...m });
    expect(leetcode.actionForKey(k("'", { metaKey: true }))).toBe("run");
    expect(leetcode.actionForKey(k("Enter", { ctrlKey: true }))).toBe("submit");
    expect(leetcode.actionForKey(k("Enter"))).toBe(null);
    expect(leetcode.actionForKey(k("'", { metaKey: true, altKey: true }))).toBe(null);
  });

  it("textOf keeps lines and superscripts", () => {
    const d = new DOMParser().parseFromString("<div><p>a<sup>2</sup></p><p>b&nbsp;c</p></div>", "text/html");
    expect(textOf(d.body.firstElementChild!)).toBe("a^2\nb c");
  });
});

describe("run results", () => {
  it("parses Wrong Answer with the failing case", () => {
    const doc = load("run-wrong-answer.html");
    expect(leetcode.runResult.read(verdictNode(doc, "run"))).toEqual({
      verdict: "wrong_answer",
      verdict_raw: "Wrong Answer",
      runtime_ms: 0,
      total_cases: 3,
      passed_cases: 0,
      failing_input: "nums = [2,7,11,15]\ntarget = 9",
      actual_output: "[0,0]",
      expected_output: "[0,1]",
    });
  });

  it("parses Accepted without failure details", () => {
    const doc = load("run-accepted.html");
    expect(leetcode.runResult.read(verdictNode(doc, "run"))).toEqual({
      verdict: "accepted",
      verdict_raw: "Accepted",
      runtime_ms: 0,
      total_cases: 3,
      passed_cases: 3,
    });
  });

  it("parses Runtime Error with the exception and the Last Executed Input", () => {
    const doc = load("run-runtime-error.html");
    const r = leetcode.runResult.read(verdictNode(doc, "run"))!;
    expect(r).toMatchObject({
      verdict: "runtime_error",
      verdict_raw: "Runtime Error",
      failing_input: "nums = [2,7,11,15]\ntarget = 9",
    });
    expect(r.error_message).toMatch(/^java\.lang\.ArrayIndexOutOfBoundsException: Index 1 out of bounds/);
  });

  it("parses Compile Error with the compiler message", () => {
    const doc = load("run-compile-error.html");
    const r = leetcode.runResult.read(verdictNode(doc, "run"))!;
    expect(r.verdict).toBe("compile_error");
    expect(r.error_message).toMatch(/^Line 5: Char 5: error: non-void function does not return a value/);
    expect(r.failing_input).toBeUndefined();
  });
});

describe("submit results", () => {
  it("parses an Accepted submission (units run into the next word: '3msBeats')", () => {
    const doc = load("submit-accepted.html");
    expect(leetcode.submitResult.read(verdictNode(doc, "submit"))).toEqual({
      verdict: "accepted",
      verdict_raw: "Accepted",
      passed_cases: 103,
      total_cases: 103,
      runtime_ms: 3,
      memory_mb: 42.99,
    });
    expect(doc.body.textContent).toContain("USER"); // the fixture holds no real account handle
  });

  it("finds a failed submission by its <h3> (no data-e2e-locator) and reads the failing case", () => {
    const doc = load("submit-wrong-answer.html");
    const node = verdictNode(doc, "submit");
    expect(node.tagName).toBe("H3"); // not the verdict-named tab title
    expect(leetcode.submitResult.read(node)).toEqual({
      verdict: "wrong_answer",
      verdict_raw: "Wrong Answer",
      passed_cases: 62,
      total_cases: 103,
      failing_input: 's = "(]"',
      actual_output: "true",
      expected_output: "false",
    });
  });

  it("is not ready until the case count renders (it appears ~300 ms after the verdict)", () => {
    const doc = load("submit-accepted.html");
    const node = verdictNode(doc, "submit");
    expect(leetcode.submitResult.ready?.(node)).toBe(true);
    node.parentElement!.querySelector(".text-text-tertiary")!.remove();
    expect(leetcode.submitResult.ready?.(node)).toBe(false);
  });
});

describe("waitForResult with a readiness check", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const probe = () => ({
    verdictNode: () => leetcode.submitResult.verdictNode(document),
    fingerprint: (n: Element) => leetcode.submitResult.fingerprint(n),
    ready: (n: Element) => leetcode.submitResult.ready!(n),
    read: (n: Element) => leetcode.submitResult.read(n),
  });

  it("waits for the stats that render after the verdict instead of settling early", async () => {
    document.body.innerHTML = '<div id="qd-content"></div>';
    const root = document.getElementById("qd-content")!;
    const full = load("submit-accepted.html").querySelector("#qd-content")!.innerHTML;
    const wait = waitForResult(probe(), () => Date.now());
    await vi.advanceTimersByTimeAsync(2600);
    // Verdict first, stats later: stable for several polls but not ready.
    root.innerHTML = full;
    root.querySelector(".text-text-tertiary")!.remove();
    root.querySelectorAll(".cursor-pointer").forEach((n) => n.textContent?.includes("Runtime") && n.remove());
    await vi.advanceTimersByTimeAsync(1000);
    root.innerHTML = full;
    await vi.advanceTimersByTimeAsync(1000);
    const settled = await wait.done;
    expect(settled).toMatchObject({ ok: true, result: { passed_cases: 103, runtime_ms: 3, memory_mb: 42.99 } });
  });

  it("ignores the previous submission's failure heading still on screen", async () => {
    document.body.innerHTML =
      '<div id="qd-content"><div data-layout-path="/ts0/t1"><h3 class="text-xl text-red-60">Wrong Answer</h3></div></div>';
    const wait = waitForResult(probe(), () => Date.now());
    await vi.advanceTimersByTimeAsync(31_000);
    expect(await wait.done).toMatchObject({ ok: false, reason: "timeout" });
  });

  it("a new heading that never becomes ready is read after the grace period", async () => {
    document.body.innerHTML = '<div id="qd-content"></div>';
    const wait = waitForResult(probe(), () => Date.now());
    await vi.advanceTimersByTimeAsync(500);
    document.getElementById("qd-content")!.innerHTML =
      '<div data-layout-path="/ts0/t1"><h3 class="text-xl text-red-60">Compile Error</h3></div>';
    await vi.advanceTimersByTimeAsync(4000);
    let done = false;
    void wait.done.then(() => (done = true));
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(1500);
    expect(await wait.done).toMatchObject({ ok: true, result: { verdict: "compile_error" } });
  });
});

it.each([
  ["Accepted", "accepted"],
  ["Wrong Answer", "wrong_answer"],
  [" Time Limit Exceeded ", "time_limit_exceeded"],
  ["Runtime Error", "runtime_error"],
  ["Pending", "unknown"],
])("normalizeVerdict(%j) = %s", (raw, v) => {
  expect(normalizeVerdict(raw)).toBe(v);
});

describe("waitForResult on the real panel markup", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const panelHtml = (file: string) => load(file).querySelector("#qd-content")!.innerHTML;

  it("ignores the stale panel, waits for the new verdict to settle, and times it from first appearance", async () => {
    document.body.innerHTML = `<div id="qd-content">${panelHtml("run-wrong-answer.html")}</div>`;
    const root = document.getElementById("qd-content")!;
    const now = () => Date.now();
    const start = Date.now();
    const wait = waitForResult(
      {
        verdictNode: () => leetcode.runResult.verdictNode(document),
        fingerprint: (n) => leetcode.runResult.fingerprint(n),
        read: (n) => leetcode.runResult.read(n),
      },
      now,
    );
    // LeetCode removes the old result right after the click, then renders the new one ~3.4 s later.
    vi.advanceTimersByTime(300);
    root.innerHTML = "";
    vi.advanceTimersByTime(3100);
    root.innerHTML = panelHtml("run-accepted.html");
    await vi.advanceTimersByTimeAsync(1000);
    const settled = await wait.done;
    expect(settled.ok).toBe(true);
    if (!settled.ok) return;
    expect(settled.result?.verdict).toBe("accepted");
    expect(settled.appearedAt - start).toBe(3500);
    expect(settled.settledAt - settled.appearedAt).toBe(250);
  });

  it("times out when no new verdict appears", async () => {
    document.body.innerHTML = `<div id="qd-content">${panelHtml("run-wrong-answer.html")}</div>`;
    const wait = waitForResult(
      {
        verdictNode: () => leetcode.runResult.verdictNode(document),
        fingerprint: (n) => n.textContent ?? "",
        read: (n) => leetcode.runResult.read(n),
      },
      () => Date.now(),
      { pollMs: 250, stablePolls: 2, timeoutMs: 2000 },
    );
    await vi.advanceTimersByTimeAsync(3000);
    expect(await wait.done).toMatchObject({ ok: false, reason: "timeout" });
  });

  it("can be cancelled (session stopped)", async () => {
    document.body.innerHTML = "";
    const wait = waitForResult(
      { verdictNode: () => null, fingerprint: () => "", read: () => null },
      () => Date.now(),
    );
    wait.cancel();
    expect(await wait.done).toMatchObject({ ok: false, reason: "cancelled" });
  });
});

describe("ResultTracker (late verdicts are never credited to an earlier click)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("supersedes a pending submit when a new one starts, so only the newest gets the verdict", async () => {
    const { ResultTracker } = await import("../src/content/results");
    document.body.innerHTML = '<div id="qd-content"></div>';
    const root = document.getElementById("qd-content")!;
    const tracker = new ResultTracker<"run" | "submit">();
    const begin = () =>
      waitForResult(
        {
          verdictNode: () => leetcode.submitResult.verdictNode(document),
          fingerprint: (n) => n.textContent ?? "",
          read: (n) => leetcode.submitResult.read(n),
        },
        () => Date.now(),
      );
    const first = tracker.start("submit", begin); // its result never shows up
    await vi.advanceTimersByTimeAsync(5000);
    const second = tracker.start("submit", begin);
    const run = tracker.start("run", () =>
      waitForResult({ verdictNode: () => null, fingerprint: () => "", read: () => null }, () => Date.now(), {
        pollMs: 250,
        stablePolls: 2,
        timeoutMs: 1000,
      }),
    );
    await vi.advanceTimersByTimeAsync(3000);
    root.innerHTML = load("submit-accepted.html").querySelector("#qd-content")!.innerHTML;
    await vi.advanceTimersByTimeAsync(1000);
    expect(await first.done).toMatchObject({ ok: false, reason: "superseded" });
    expect(await second.done).toMatchObject({ ok: true, result: { verdict: "accepted" } });
    expect(await run.done).toMatchObject({ ok: false, reason: "timeout" }); // other kinds are untouched
  });

  it("cancelAll stops every pending wait as cancelled (session stop)", async () => {
    const { ResultTracker } = await import("../src/content/results");
    const tracker = new ResultTracker<"run" | "submit">();
    const never = () => waitForResult({ verdictNode: () => null, fingerprint: () => "", read: () => null }, () => Date.now());
    const a = tracker.start("run", never);
    const b = tracker.start("submit", never);
    tracker.cancelAll();
    expect(await a.done).toMatchObject({ reason: "cancelled" });
    expect(await b.done).toMatchObject({ reason: "cancelled" });
  });
});

/**
 * LeetCode adapter. Selectors were checked against leetcode.com on 2026-10-19: Two Sum (problem
 * page; run results for Wrong Answer, Accepted, Compile Error) and Valid Parentheses (fresh
 * Wrong Answer and Accepted submissions). Saved fragments live in extension/test/dom/leetcode/.
 * Bump ADAPTER_VERSION when selectors change.
 *
 * 0.2.0: failed submissions carry no data-e2e-locator (verdict is an <h3 class="text-xl ...">);
 * submit panels are read only once "testcases passed" has rendered; metric units are matched
 * even when run into the next word ("3msBeats").
 * 0.3.0: clicks on a pending Run/Submit button (styled cursor-not-allowed, not `disabled`) are
 * ignored by LeetCode and are not runs; "Last Executed Input" (runtime errors) is read, matching
 * section labels by their own text since that label also contains an "Open Testcase" link.
 */

import type { Example, ProblemLoadedData } from "../generated/contract";
import type { ResultReader, RunResult, SiteAdapter, SubmitResult } from "./types";

export const ADAPTER_VERSION = "0.3.0";

const SEL = {
  title: ".text-title-large",
  difficulty: '[class*="text-difficulty-"]',
  description: '[data-track-load="description_content"]',
  editor: "#editor",
  run: '[data-e2e-locator="console-run-button"]',
  submit: '[data-e2e-locator="console-submit-button"]',
  runVerdict: '[data-e2e-locator="console-result"]',
  // Accepted: <span data-e2e-locator="submission-result">. Failures: <h3 class="text-xl ..."> whose
  // own text is the verdict, with "x / y testcases passed" nested inside it.
  submitVerdict: '[data-e2e-locator="submission-result"]',
  submitVerdictHeading: 'h3[class*="text-xl"]',
  panel: "[data-layout-path]",
} as const;

/** Language picker label -> LeetCode language slug. */
const LANGUAGES: Record<string, string> = {
  "c++": "cpp",
  java: "java",
  python: "python",
  python3: "python3",
  c: "c",
  "c#": "csharp",
  javascript: "javascript",
  typescript: "typescript",
  php: "php",
  swift: "swift",
  kotlin: "kotlin",
  dart: "dart",
  go: "golang",
  ruby: "ruby",
  scala: "scala",
  rust: "rust",
  racket: "racket",
  erlang: "erlang",
  elixir: "elixir",
};

const VERDICTS: Record<string, RunResult["verdict"]> = {
  accepted: "accepted",
  "wrong answer": "wrong_answer",
  "runtime error": "runtime_error",
  "compile error": "compile_error",
  "time limit exceeded": "time_limit_exceeded",
  "memory limit exceeded": "memory_limit_exceeded",
  "output limit exceeded": "output_limit_exceeded",
};

export function normalizeVerdict(raw: string): RunResult["verdict"] {
  return VERDICTS[raw.trim().toLowerCase()] ?? "unknown";
}

const BLOCK = new Set(["P", "DIV", "PRE", "LI", "UL", "OL", "BR", "H1", "H2", "H3", "H4", "TABLE", "TR"]);

/** Text of a node with <sup> rendered as ^ (so 10<sup>4</sup> reads 10^4) and blocks as lines. */
export function textOf(node: Node): string {
  let out = "";
  const walk = (n: Node) => {
    if (n.nodeType === 3) {
      out += n.textContent ?? "";
      return;
    }
    if (n.nodeType !== 1) return;
    const el = n as Element;
    if (el.tagName === "SUP") {
      out += "^" + (el.textContent ?? "");
      return;
    }
    if (el.tagName === "BR") {
      out += "\n";
      return;
    }
    el.childNodes.forEach(walk);
    if (BLOCK.has(el.tagName) && !out.endsWith("\n")) out += "\n";
  };
  walk(node);
  return out
    .replace(/ /g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseExampleText(text: string): Example | null {
  const m = /Input:\s*([\s\S]*?)\s*Output:\s*([\s\S]*?)(?:\s*Explanation:\s*([\s\S]*))?$/.exec(text.trim());
  if (!m) return null;
  const example: Example = { input: m[1]!.trim(), output: m[2]!.trim() };
  if (m[3]?.trim()) example.explanation = m[3].trim();
  return example;
}

export function parseDescription(desc: Element): Pick<ProblemLoadedData, "statement" | "examples" | "constraints"> {
  const statementParts: string[] = [];
  const examples: Example[] = [];
  const constraints: string[] = [];
  let section: "statement" | "examples" | "constraints" | "after" = "statement";
  for (const child of Array.from(desc.children)) {
    const text = textOf(child);
    if (/^Example \d+:?$/.test(text)) {
      section = "examples";
      continue;
    }
    if (/^Constraints:?$/.test(text)) {
      section = "constraints";
      continue;
    }
    if (/^Follow[- ]up/i.test(text)) section = "after";
    if (section === "statement") {
      if (text) statementParts.push(text);
    } else if (section === "examples") {
      // Older problems: <pre>; newer ones: <div class="example-block">.
      if (child.tagName === "PRE" || child.classList.contains("example-block")) {
        const ex = parseExampleText(text);
        if (ex) examples.push(ex);
      }
    } else if (section === "constraints" && (child.tagName === "UL" || child.tagName === "OL")) {
      for (const li of Array.from(child.querySelectorAll("li"))) constraints.push(textOf(li));
      section = "after";
    }
  }
  return { statement: statementParts.join("\n\n") || null, examples, constraints };
}

function slugOf(url: URL): string | null {
  const m = /^\/problems\/([a-z0-9-]+)(?:\/|$)/.exec(url.pathname);
  return m ? m[1]! : null;
}

function findLeaf(root: ParentNode, text: string): Element | null {
  for (const el of Array.from(root.querySelectorAll("*"))) {
    if (el.children.length === 0 && el.textContent?.trim() === text) {
      return el;
    }
  }
  return null;
}

/**
 * Value of a result section (Input / Last Executed Input / Output / Expected / Stdout). Labels are
 * matched by their own text: "Last Executed Input" also holds an "Open Testcase" link.
 */
function runSection(panel: ParentNode, label: string): Element | null {
  for (const el of Array.from(panel.querySelectorAll('[class*="text-label-3"]'))) {
    if (ownText(el) === label) return el.nextElementSibling;
  }
  return null;
}

function menloText(el: Element): string {
  const parts = Array.from(el.querySelectorAll(".font-menlo")).map((n) => n.textContent?.trim() ?? "");
  return parts.join("\n").trim();
}

/** Input section: pairs of "name =" labels and values -> "nums = [3,2,4]\ntarget = 6". */
function inputText(section: Element): string {
  const lines: string[] = [];
  for (const label of Array.from(section.querySelectorAll(".text-label-3"))) {
    const name = label.textContent?.trim() ?? "";
    const value = label.parentElement?.querySelector(".font-menlo")?.textContent?.trim();
    if (name.endsWith("=") && value !== undefined) lines.push(`${name} ${value}`);
  }
  return lines.length ? lines.join("\n") : menloText(section);
}

function panelOf(node: Element): Element {
  return node.closest(SEL.panel) ?? node.ownerDocument.body;
}

const runResult: ResultReader<RunResult> = {
  verdictNode: (root) => root.querySelector(SEL.runVerdict),
  fingerprint: (node) => panelOf(node).textContent ?? "",
  read: (node) => {
    const raw = node.textContent?.trim() ?? "";
    if (!raw) return null;
    const panel = panelOf(node);
    const result: RunResult = { verdict: normalizeVerdict(raw), verdict_raw: raw };
    const runtime = /Runtime:\s*([\d.]+)\s*ms/.exec(node.parentElement?.textContent ?? "");
    if (runtime) result.runtime_ms = Number(runtime[1]);

    // Case tabs: "Case N" with a red (failed) or green (passed) status icon.
    const tabs = Array.from(panel.querySelectorAll("div")).filter(
      (d) => d.children.length === 0 && /^Case \d+$/.test(d.textContent?.trim() ?? ""),
    );
    if (tabs.length) {
      const failed = tabs.filter((t) => t.parentElement?.querySelector('[class*="text-red"]')).length;
      result.total_cases = tabs.length;
      result.passed_cases = tabs.length - failed;
    }

    if (result.verdict === "compile_error" || result.verdict === "runtime_error") {
      const err = panel.querySelector('.font-menlo[class*="text-red"]');
      if (err?.textContent) result.error_message = err.textContent.trim();
    }
    if (result.verdict !== "accepted" && result.verdict !== "compile_error") {
      const input = runSection(panel, "Last Executed Input") ?? runSection(panel, "Input");
      const output = runSection(panel, "Output");
      const expected = runSection(panel, "Expected");
      const stdout = runSection(panel, "Stdout");
      if (input) result.failing_input = inputText(input);
      if (output) result.actual_output = menloText(output);
      if (expected) result.expected_output = menloText(expected);
      if (stdout) result.stdout = menloText(stdout);
    }
    return result;
  },
};

/** Number + unit after a label leaf such as "Runtime" or "Memory" in the submission panel. */
function metric(panel: Element, label: string): number | undefined {
  const leaf = findLeaf(panel, label);
  if (!leaf) return undefined;
  let box: Element | null = leaf.parentElement;
  for (let i = 0; i < 3 && box; i++, box = box.parentElement) {
    // textContent runs units into the next word ("3msBeats"), so no \b after the unit.
    const m = new RegExp(`${label}\\s*([\\d.]+)\\s*(ms|MB|KB|s)(?![a-z])`).exec((box.textContent ?? "").replace(/\s+/g, " "));
    if (m) {
      const v = Number(m[1]);
      return m[2] === "s" ? v * 1000 : m[2] === "KB" ? v / 1024 : v;
    }
  }
  return undefined;
}

/** The node's own text, without nested elements (the failure <h3> nests the case count). */
function ownText(node: Element): string {
  return Array.from(node.childNodes)
    .filter((n) => n.nodeType === 3)
    .map((n) => n.textContent ?? "")
    .join("")
    .trim();
}

function submitVerdictNode(root: ParentNode): Element | null {
  const tagged = root.querySelector(SEL.submitVerdict);
  if (tagged) return tagged;
  for (const h of Array.from(root.querySelectorAll(SEL.submitVerdictHeading))) {
    if (normalizeVerdict(ownText(h)) !== "unknown") return h;
  }
  return null;
}

const submitResult: ResultReader<SubmitResult> = {
  verdictNode: submitVerdictNode,
  fingerprint: (node) => panelOf(node).textContent ?? "",
  // The verdict renders ~300 ms before the case count and runtime/memory (observed live).
  ready: (node) => /testcases passed/.test(panelOf(node).textContent ?? ""),
  read: (node) => {
    const raw = ownText(node) || node.textContent?.trim() || "";
    if (!raw) return null;
    const panel = panelOf(node);
    const text = (panel.textContent ?? "").replace(/\s+/g, " ");
    const result: SubmitResult = { verdict: normalizeVerdict(raw), verdict_raw: raw };
    const cases = /(\d+)\s*\/\s*(\d+)\s*testcases passed/.exec(text);
    if (cases) {
      result.passed_cases = Number(cases[1]);
      result.total_cases = Number(cases[2]);
    }
    const runtime = metric(panel, "Runtime");
    const memory = metric(panel, "Memory");
    if (runtime !== undefined) result.runtime_ms = runtime;
    if (memory !== undefined) result.memory_mb = Math.round(memory * 100) / 100;
    if (result.verdict !== "accepted") {
      // Same section markup as the run panel.
      const input = runSection(panel, "Last Executed Input") ?? runSection(panel, "Input");
      const output = runSection(panel, "Output");
      const expected = runSection(panel, "Expected");
      const stdout = runSection(panel, "Stdout");
      const err = panel.querySelector('.font-menlo[class*="text-red"]');
      if (input) result.failing_input = inputText(input);
      if (output) result.actual_output = menloText(output);
      if (expected) result.expected_output = menloText(expected);
      if (stdout) result.stdout = menloText(stdout);
      if (err?.textContent) result.error_message = err.textContent.trim();
    }
    return result;
  },
};

export const leetcode: SiteAdapter = {
  name: "leetcode",
  platform: "leetcode",
  version: ADAPTER_VERSION,
  editorSelector: SEL.editor,

  matches: (url) => url.protocol === "https:" && url.hostname === "leetcode.com" && slugOf(url) !== null,
  problemKey: slugOf,
  canonicalUrl: (slug) => `https://leetcode.com/problems/${slug}/`,

  readProblem(root, url) {
    const slug = slugOf(url);
    if (!slug) return null;
    const titleEl = root.querySelector(SEL.title);
    const rawTitle = titleEl?.textContent?.trim() || root.title.replace(/\s*-\s*LeetCode\s*$/, "").trim();
    if (!rawTitle) return null;
    const diff = /text-difficulty-(easy|medium|hard)/.exec(root.querySelector(SEL.difficulty)?.className ?? "");
    const desc = root.querySelector(SEL.description);
    return {
      platform: "leetcode",
      slug,
      url: `https://leetcode.com/problems/${slug}/`,
      title: rawTitle.replace(/^\d+\.\s*/, ""),
      difficulty: (diff?.[1] as "easy" | "medium" | "hard" | undefined) ?? "unknown",
      ...(desc ? parseDescription(desc) : { statement: null, examples: [], constraints: [] }),
    };
  },

  hasStatement: (p) => !!p.statement,

  readLanguage(root) {
    const editorTab = root.querySelector(SEL.editor)?.closest(SEL.panel);
    const buttons = Array.from(editorTab?.querySelectorAll('button[aria-haspopup="dialog"]') ?? []);
    for (const b of buttons) {
      const label = b.textContent?.trim().toLowerCase() ?? "";
      if (label in LANGUAGES) return LANGUAGES[label]!;
    }
    return null;
  },

  actionForClick(target) {
    if (target.closest(SEL.run)) return "run";
    if (target.closest(SEL.submit)) return "submit";
    return null;
  },

  // LeetCode: Ctrl/Cmd + ' runs, Ctrl/Cmd + Enter submits.
  actionForKey(e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return null;
    if (e.key === "'") return "run";
    if (e.key === "Enter") return "submit";
    return null;
  },

  hasRunButtons: (root) => !!root.querySelector(SEL.run) && !!root.querySelector(SEL.submit),

  // While a run/submit is pending LeetCode styles the button cursor-not-allowed (it does not set
  // `disabled`, so clicks still fire) and ignores further clicks. Observed live for Run.
  actionPending(root, action) {
    const button = root.querySelector(action === "run" ? SEL.run : SEL.submit);
    return !!button && /\bcursor-not-allowed\b/.test(button.className);
  },

  runResult,
  submitResult,
};

/**
 * Content script (isolated world). Declared for all of leetcode.com but inert until the service
 * worker says a session is recording in this tab (E4). While active it:
 *  - reads the problem once, through the site adapter;
 *  - relays code snapshots from the main-world probe;
 *  - records run/submit clicks and shortcuts, then waits for the result panel to settle;
 *  - records editor-scoped key categories (bursts), paste sizes, undo, and focus changes.
 * No analysis happens here; every capture is stamped with when it happened and sent on.
 */

import { leetcode } from "../adapters/leetcode";
import type { ResultReader, SiteAdapter } from "../adapters/types";
import { epochNow, type EpochMs } from "../shared/clock";
import {
  type ActiveInfo,
  type CapabilityPatch,
  type Capture,
  type CaptureResponse,
  type ContentCommand,
  type ContentRequest,
  isProbeOutbound,
  PROBE_CHANNEL,
  type ProbeInboundBody,
  type QueryResponse,
} from "../shared/messages";
import { BurstAggregator, categorize, isUndo, pasteSize } from "./keystrokes";
import { DEFAULT_WAIT, ResultTracker, type Settled, waitForResult } from "./results";

const ADAPTERS: SiteAdapter[] = [leetcode];
const PROBLEM_RETRY_MS = 500;
const PROBLEM_TIMEOUT_MS = 10_000;
const FOCUS_SETTLE_MS = 50;

function send<T>(msg: ContentRequest): Promise<T> {
  return chrome.runtime.sendMessage(msg) as Promise<T>;
}

function toProbe(msg: ProbeInboundBody): void {
  window.postMessage({ channel: PROBE_CHANNEL, dir: "to-probe", ...msg }, window.location.origin);
}

class ActiveSession {
  private readonly cleanups: Array<() => void> = [];
  private readonly bursts: BurstAggregator;
  private readonly results = new ResultTracker<"run" | "submit">();
  private readonly inflight = new Set<Promise<unknown>>();
  private stopped = false;

  constructor(
    private readonly adapter: SiteAdapter,
    private readonly info: ActiveInfo,
  ) {
    this.bursts = new BurstAggregator((b) =>
      this.capture({
        kind: "keystroke",
        at: b.at,
        data: { duration_s: b.durationS, counts: b.counts },
        language: this.language(),
      }),
    );
  }

  async start(): Promise<void> {
    const language = this.adapter.readLanguage(document);
    const patch: CapabilityPatch = { run_events: this.adapter.hasRunButtons(document) };
    if (language) patch.language = language;
    await send({ type: "content/capabilities", patch });

    this.listenProbe();
    await send({ type: "content/inject-probe" });
    toProbe({ type: "init", editorSelector: this.adapter.editorSelector });

    if (this.info.needProblem) void this.readProblem();
    this.listenActions();
    this.listenKeys();
    this.listenFocus();
  }

  /** Stop listening, flush the open keystroke burst, and wait (briefly) for in-flight captures. */
  async stop(): Promise<void> {
    if (this.stopped) return;
    this.bursts.flush();
    this.stopped = true;
    toProbe({ type: "stop" });
    this.results.cancelAll();
    this.cleanups.forEach((c) => c());
    await Promise.race([Promise.allSettled([...this.inflight]), new Promise((r) => setTimeout(r, 1000))]);
  }

  /** Current editor language from the platform's picker (locks the session language, E14). */
  private language(): string | null {
    return this.adapter.readLanguage(document);
  }

  private on<K extends keyof (WindowEventMap & DocumentEventMap)>(
    target: Window | Document,
    type: K,
    fn: (e: (WindowEventMap & DocumentEventMap)[K]) => void,
    capture = true,
  ): void {
    const listener = fn as EventListener;
    target.addEventListener(type, listener, capture);
    this.cleanups.push(() => target.removeEventListener(type, listener, capture));
  }

  private capture(c: Capture): Promise<string | null> {
    if (this.stopped) return Promise.resolve(null);
    const p = send<CaptureResponse>({ type: "content/capture", capture: c })
      .then((res) => {
        if (res.ok) return res.id;
        void this.stop();
        return null;
      })
      .catch(() => null) // extension reloaded or service worker unreachable
      .finally(() => this.inflight.delete(p));
    this.inflight.add(p);
    return p;
  }

  private async readProblem(): Promise<void> {
    const startedAt = Date.now();
    const url = new URL(location.href);
    for (;;) {
      if (this.stopped) return;
      const problem = this.adapter.readProblem(document, url);
      const timedOut = Date.now() - startedAt > PROBLEM_TIMEOUT_MS;
      if (problem && (this.adapter.hasStatement(problem) || timedOut)) {
        await send({
          type: "content/capabilities",
          patch: { problem_statement: this.adapter.hasStatement(problem) ? "scraped" : "none" },
        });
        await this.capture({ kind: "problem_loaded", at: epochNow(), data: problem });
        return;
      }
      if (timedOut) return;
      await new Promise((r) => setTimeout(r, PROBLEM_RETRY_MS));
    }
  }

  private listenProbe(): void {
    this.on(window, "message", (ev) => {
      if (ev.source !== window || !isProbeOutbound(ev.data)) return;
      const msg = ev.data;
      if (msg.type === "snapshot") {
        const language = this.adapter.readLanguage(document) ?? msg.languageId;
        void this.capture({ kind: "code_snapshot", at: msg.at, data: { code: msg.code, reason: msg.reason }, language });
      } else if (msg.type === "unavailable") {
        void send({ type: "content/capabilities", patch: { exact_code: false } });
      }
    });
  }

  private listenActions(): void {
    const handle = (action: "run" | "submit", trigger: "click" | "shortcut") => {
      // The platform ignores clicks while the previous one is pending: not a run, and it must
      // not supersede the wait for the run that is actually in progress.
      if (this.adapter.actionPending(document, action)) return;
      const at = epochNow();
      this.bursts.flush();
      const reader: ResultReader<unknown> = action === "run" ? this.adapter.runResult : this.adapter.submitResult;
      // Supersedes an unsettled earlier wait of the same kind (recorded as unknown), so a later
      // verdict is never credited to an earlier click.
      const wait = this.results.start(action, () =>
        waitForResult(
          {
            verdictNode: () => reader.verdictNode(document),
            fingerprint: (n) => reader.fingerprint(n),
            ...(reader.ready ? { ready: (n: Element) => reader.ready!(n) } : {}),
            read: (n) => reader.read(n),
          },
          epochNow,
          DEFAULT_WAIT,
        ),
      );
      void (async () => {
        const id = await this.capture({ kind: action, at, data: { trigger }, language: this.language() });
        toProbe({ type: "snapshot-now", reason: action });
        const settled = await wait.done;
        if (!id || (!settled.ok && settled.reason === "cancelled")) return;
        await this.captureResult(action, id, settled);
      })();
    };
    this.on(document, "click", (e) => {
      const target = e.target instanceof Element ? e.target : null;
      const action = target ? this.adapter.actionForClick(target) : null;
      if (action) handle(action, "click");
    });
    this.on(document, "keydown", (e) => {
      const action = this.adapter.actionForKey(e);
      if (action && !e.repeat) handle(action, "shortcut");
    });
  }

  private async captureResult(
    action: "run" | "submit",
    id: string,
    settled: Settled<unknown>,
  ): Promise<void> {
    // Result time: when the verdict appeared; uncertainty covers one poll interval.
    const unc = DEFAULT_WAIT.pollMs / 1000;
    const failed = { verdict: "unknown" as const };
    const result = settled.ok ? (settled.result as object) : failed;
    const at: EpochMs = settled.ok ? settled.appearedAt : settled.at;
    const confidence = settled.ok ? 1 : 0;
    if (action === "run") {
      await this.capture({ kind: "run_result", at, confidence, t_uncertainty: unc, data: { ...failed, ...result, run_id: id } });
    } else {
      await this.capture({ kind: "submit_result", at, confidence, t_uncertainty: unc, data: { ...failed, ...result, submit_id: id } });
    }
  }

  private inEditor(target: EventTarget | null): boolean {
    return target instanceof Node && !!document.querySelector(this.adapter.editorSelector)?.contains(target);
  }

  private listenKeys(): void {
    this.on(document, "keydown", (e) => {
      if (!this.inEditor(e.target)) return;
      const at = epochNow();
      if (isUndo(e)) {
        this.bursts.flush();
        void this.capture({ kind: "undo", at, data: { count: 1 }, language: this.language() });
      }
      const category = categorize(e);
      if (category) this.bursts.add(category, at);
    });
    this.on(document, "paste", (e) => {
      if (!this.inEditor(e.target)) return;
      const size = pasteSize(e.clipboardData?.getData("text/plain") ?? "");
      this.bursts.flush();
      void this.capture({ kind: "paste", at: epochNow(), data: size, language: this.language() });
    });
  }

  private listenFocus(): void {
    const focus = (target: "tab" | "window" | "editor", state: "away" | "back", at = epochNow()) =>
      void this.capture({ kind: "focus_change", at, data: { target, state } });

    // A tab switch fires both visibilitychange and blur; report it once, as "tab".
    this.on(document, "visibilitychange", () => focus("tab", document.hidden ? "away" : "back"));
    this.on(window, "blur", (e) => {
      if (e.target !== window) return;
      const at = epochNow();
      setTimeout(() => !document.hidden && !this.stopped && focus("window", "away", at), FOCUS_SETTLE_MS);
    });
    this.on(window, "focus", (e) => {
      if (e.target !== window) return;
      const at = epochNow();
      setTimeout(() => !document.hidden && !this.stopped && focus("window", "back", at), FOCUS_SETTLE_MS);
    });
    let editorFocused = false;
    this.on(document, "focusin", (e) => {
      if (this.inEditor(e.target) && !editorFocused) {
        editorFocused = true;
        focus("editor", "back");
      }
    });
    this.on(document, "focusout", (e) => {
      const next = (e as FocusEvent).relatedTarget;
      if (editorFocused && this.inEditor(e.target) && !this.inEditor(next)) {
        editorFocused = false;
        focus("editor", "away");
      }
    });
  }
}

let active: ActiveSession | null = null;

function adapterFor(url: URL): SiteAdapter | null {
  return ADAPTERS.find((a) => a.matches(url)) ?? null;
}

async function activate(info: ActiveInfo): Promise<void> {
  if (active) return;
  const adapter = adapterFor(new URL(location.href));
  if (!adapter) return;
  active = new ActiveSession(adapter, info);
  await active.start();
}

async function deactivate(): Promise<void> {
  const session = active;
  active = null;
  await session?.stop();
}

declare global {
  // Set once per page so a second injection (static + chrome.scripting fallback) is a no-op.
  var __interviewCoachContent: boolean | undefined;
}

if (!globalThis.__interviewCoachContent) {
  globalThis.__interviewCoachContent = true;

  chrome.runtime.onMessage.addListener((msg: ContentCommand, _sender, sendResponse) => {
    if (msg.type === "sw/session-start") {
      void activate(msg).then(() => sendResponse({ ok: true }));
      return true;
    }
    if (msg.type === "sw/session-stop") {
      void deactivate().then(() => sendResponse({ ok: true }));
      return true;
    }
    return false;
  });

  // On (re)load, resume if this tab is the one recording (e.g. after a page reload).
  void send<QueryResponse>({ type: "content/query", url: location.href })
    .then((res) => (res.active ? activate(res) : undefined))
    .catch(() => undefined);
}

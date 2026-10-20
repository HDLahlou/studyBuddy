/**
 * Page probe, injected into the page's main world by the service worker only while a session is
 * recording (chrome.scripting, world: "MAIN"). It reads the Monaco editor, which the isolated
 * content script cannot see, and reports code snapshots over window.postMessage.
 *
 * It is generic Monaco code: the adapter tells it, via `init`, which editor container to use.
 * Anything on the page could post messages too, so the content script validates every message
 * and this probe only ever sends code text that the page already shows.
 */

import { epochNow } from "../shared/clock";
import { isProbeInbound, PROBE_CHANNEL, type ProbeOutboundBody } from "../shared/messages";
import { SnapshotScheduler } from "./snapshots";

interface MonacoModel {
  getValue(): string;
  getLanguageId?(): string;
}
interface MonacoEditor {
  getModel(): MonacoModel | null;
  getDomNode(): HTMLElement | null;
  onDidChangeModelContent(cb: () => void): { dispose(): void };
  onDidChangeModel(cb: () => void): { dispose(): void };
}
interface MonacoGlobal {
  editor: { getEditors(): MonacoEditor[] };
}

declare global {
  interface Window {
    monaco?: MonacoGlobal;
    __interviewCoachProbe?: boolean;
  }
}

const FIND_INTERVAL_MS = 500;
const FIND_TIMEOUT_MS = 30_000;

function post(msg: ProbeOutboundBody): void {
  window.postMessage({ channel: PROBE_CHANNEL, dir: "from-probe", ...msg }, window.location.origin);
}

function findEditor(selector: string): MonacoEditor | null {
  const root = document.querySelector(selector);
  const editors = window.monaco?.editor?.getEditors?.() ?? [];
  return editors.find((e) => {
    const node = e.getDomNode();
    return root && node && root.contains(node);
  }) ?? null;
}

function main(): void {
  if (window.__interviewCoachProbe) return;
  window.__interviewCoachProbe = true;

  let scheduler: SnapshotScheduler | null = null;
  let subscriptions: Array<{ dispose(): void }> = [];
  let editor: MonacoEditor | null = null;

  const languageId = () => editor?.getModel()?.getLanguageId?.() ?? null;

  const attach = (selector: string) => {
    const startedAt = Date.now();
    const tryFind = () => {
      editor = findEditor(selector);
      if (!editor) {
        if (Date.now() - startedAt > FIND_TIMEOUT_MS) {
          post({ type: "unavailable", reason: "monaco editor not found" });
          return;
        }
        setTimeout(tryFind, FIND_INTERVAL_MS);
        return;
      }
      const ed = editor;
      scheduler = new SnapshotScheduler(
        () => ed.getModel()?.getValue() ?? "",
        (s) => post({ type: "snapshot", code: s.code, reason: s.reason, at: s.at, languageId: languageId() }),
        epochNow,
      );
      subscriptions = [
        ed.onDidChangeModelContent(() => scheduler?.onChange()),
        // Switching language swaps the model: take a snapshot of the new one.
        ed.onDidChangeModel(() => scheduler?.onChange()),
      ];
      post({ type: "ready", languageId: languageId() });
      scheduler.start();
    };
    tryFind();
  };

  const detach = () => {
    scheduler?.stop();
    subscriptions.forEach((s) => s.dispose());
    scheduler = null;
    subscriptions = [];
    editor = null;
  };

  window.addEventListener("message", (ev) => {
    if (ev.source !== window || !isProbeInbound(ev.data)) return;
    const msg = ev.data;
    if (msg.type === "init") {
      detach();
      attach(msg.editorSelector);
    } else if (msg.type === "snapshot-now") {
      scheduler?.force(msg.reason);
    } else if (msg.type === "stop") {
      detach();
    }
  });
}

main();

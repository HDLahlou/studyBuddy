/**
 * Messages between the extension's own parts (chrome.runtime / chrome.tabs messaging and the
 * page probe's window.postMessage). Internal only: the engine protocol is in src/generated.
 */

import type {
  CodeSnapshotData,
  FocusChangeData,
  KeystrokeData,
  PasteData,
  ProblemLoadedData,
  RunData,
  RunResultData,
  SubmitData,
  SubmitResultData,
  UndoData,
} from "../generated/contract";
import type { EpochMs } from "./clock";

export type SessionMode = "practice" | "mock_interview" | "assessment";

/** A captured fact, before the service worker stamps seq, id and session time. */
interface CaptureBase {
  at: EpochMs;
  confidence?: number;
  t_uncertainty?: number;
  /** Editor language when captured (adapter's picker reading), if known. Not stored on the event
   * itself except for snapshots; used to lock the session language (E14). */
  language?: string | null;
}

export type Capture =
  | (CaptureBase & { kind: "problem_loaded"; data: ProblemLoadedData })
  | (CaptureBase & { kind: "code_snapshot"; data: CodeSnapshotData })
  | (CaptureBase & { kind: "keystroke"; data: KeystrokeData })
  | (CaptureBase & { kind: "paste"; data: PasteData })
  | (CaptureBase & { kind: "undo"; data: UndoData })
  | (CaptureBase & { kind: "run"; data: RunData })
  | (CaptureBase & { kind: "submit"; data: SubmitData })
  | (CaptureBase & { kind: "run_result"; data: RunResultData })
  | (CaptureBase & { kind: "submit_result"; data: SubmitResultData })
  | (CaptureBase & { kind: "focus_change"; data: FocusChangeData });

export type CaptureKind = Capture["kind"];

/** Content script -> service worker. */
export type ContentRequest =
  | { type: "content/query"; url: string }
  | { type: "content/capture"; capture: Capture }
  | { type: "content/inject-probe" }
  | { type: "content/capabilities"; patch: CapabilityPatch };

export interface CapabilityPatch {
  language?: string;
  exact_code?: boolean;
  run_events?: boolean;
  problem_statement?: "none" | "scraped" | "manual";
}

export interface ActiveInfo {
  sessionId: string;
  /** True when problem_loaded has not been recorded yet for this session. */
  needProblem: boolean;
}

export type QueryResponse = { active: false } | ({ active: true } & ActiveInfo);
export type CaptureResponse = { ok: true; id: string } | { ok: false; error: string };

/** Service worker -> content script. */
export type ContentCommand =
  | ({ type: "sw/session-start" } & ActiveInfo)
  | { type: "sw/session-stop" };

/** Popup / extension pages -> service worker. */
export type UiRequest =
  | { type: "ui/start"; tabId: number; mode: SessionMode }
  | { type: "ui/stop" }
  | { type: "ui/status" }
  | { type: "ui/delete"; sessionId: string };

export interface UiStatus {
  recording: null | {
    sessionId: string;
    tabId: number;
    slug: string;
    startedAt: EpochMs;
    audio: boolean;
    events: number;
  };
  sessions: SessionSummary[];
}

export interface SessionSummary {
  sessionId: string;
  slug: string;
  title: string | null;
  status: "recording" | "stopped" | "interrupted";
  wallTimeUtc: string;
  durationS: number | null;
  events: number;
  audioChunks: number;
}

export type UiResponse = { ok: true; status?: UiStatus } | { ok: false; error: string };

/** Service worker <-> offscreen document. */
export type OffscreenRequest =
  | { target: "offscreen"; type: "audio/start"; sessionId: string; t0: EpochMs }
  | { target: "offscreen"; type: "audio/stop" };

export type OffscreenStartResponse =
  | { ok: true; mime: string; offsetS: number }
  | { ok: false; error: string };
export type OffscreenStopResponse = { ok: true; lastIndex: number | null } | { ok: false; error: string };

/** Page probe (main world) <-> content script, over window.postMessage. */
export const PROBE_CHANNEL = "interview-coach/probe";

export type ProbeInbound =
  | { channel: typeof PROBE_CHANNEL; dir: "to-probe"; type: "init"; editorSelector: string }
  | { channel: typeof PROBE_CHANNEL; dir: "to-probe"; type: "snapshot-now"; reason: "run" | "submit" | "initial" }
  | { channel: typeof PROBE_CHANNEL; dir: "to-probe"; type: "stop" };

export type ProbeOutbound =
  | { channel: typeof PROBE_CHANNEL; dir: "from-probe"; type: "ready"; languageId: string | null }
  | { channel: typeof PROBE_CHANNEL; dir: "from-probe"; type: "unavailable"; reason: string }
  | {
      channel: typeof PROBE_CHANNEL;
      dir: "from-probe";
      type: "snapshot";
      code: string;
      reason: CodeSnapshotData["reason"];
      languageId: string | null;
      at: EpochMs;
    };

/** A probe message without the channel/dir envelope (distributes over the union). */
type Body<T> = T extends unknown ? Omit<T, "channel" | "dir"> : never;
export type ProbeInboundBody = Body<ProbeInbound>;
export type ProbeOutboundBody = Body<ProbeOutbound>;

export function isProbeOutbound(v: unknown): v is ProbeOutbound {
  if (typeof v !== "object" || v === null) return false;
  const m = v as Record<string, unknown>;
  if (m.channel !== PROBE_CHANNEL || m.dir !== "from-probe") return false;
  switch (m.type) {
    case "ready":
      return m.languageId === null || typeof m.languageId === "string";
    case "unavailable":
      return typeof m.reason === "string";
    case "snapshot":
      return (
        typeof m.code === "string" &&
        typeof m.at === "number" &&
        ["initial", "debounce", "periodic", "run", "submit"].includes(m.reason as string)
      );
    default:
      return false;
  }
}

export function isProbeInbound(v: unknown): v is ProbeInbound {
  if (typeof v !== "object" || v === null) return false;
  const m = v as Record<string, unknown>;
  return m.channel === PROBE_CHANNEL && m.dir === "to-probe" && typeof m.type === "string";
}

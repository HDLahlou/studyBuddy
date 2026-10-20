/**
 * Session logic: turns captures into canonical events. Used by the service worker and, unchanged,
 * by the fixture replay tests, so the exported bundle is tested without a browser.
 */

import type { Event, SessionEndData } from "../generated/contract";
import { type EpochMs, isSkewed, toSessionT } from "./clock";
import { eventId, newSessionId } from "./ids";
import type { CapabilityPatch, Capture, SessionMode } from "./messages";
import type { SessionRecord, Store } from "./store";

/**
 * The first of these locks the session language (E14). Before the lock, the user may still be
 * picking a language on the problem page, so every snapshot records its language.
 */
export const LANGUAGE_LOCK_KINDS: ReadonlySet<Capture["kind"]> = new Set(["keystroke", "paste", "undo", "run", "submit"]);

export interface StartOptions {
  tabId: number;
  platform: string;
  adapterVersion: string;
  slug: string;
  url: string;
  mode: SessionMode;
  t0: EpochMs;
  sessionId?: string;
  wallTime?: Date;
}

export class Recorder {
  constructor(private readonly store: Store) {}

  async start(opts: StartOptions): Promise<SessionRecord> {
    const wall = opts.wallTime ?? new Date(opts.t0);
    const rec: SessionRecord = {
      sessionId: opts.sessionId ?? newSessionId(opts.slug, wall),
      tabId: opts.tabId,
      platform: opts.platform,
      adapterVersion: opts.adapterVersion,
      slug: opts.slug,
      title: null,
      mode: opts.mode,
      t0: opts.t0,
      wallTimeUtc: wall.toISOString(),
      status: "recording",
      nextSeq: 1,
      language: null,
      languageLocked: false,
      lastSnapshotLanguage: null,
      clockSkewed: 0,
      exactCode: false,
      runEvents: false,
      problemStatement: "none",
      problemLoaded: false,
      audio: null,
      endSeq: null,
      lastAudioChunk: null,
    };
    await this.store.createSession(rec);
    await this.store.appendEvent(rec.sessionId, (seq) => ({
      id: eventId(seq),
      t: 0,
      seq,
      source: "extension",
      confidence: 1,
      t_uncertainty: 0,
      kind: "session_start",
      data: { url: opts.url },
    }));
    return rec;
  }

  /** Stamp a capture with seq, id and session time, and store it. */
  async capture(sessionId: string, c: Capture): Promise<Event> {
    return this.store.appendEvent(
      sessionId,
      (seq, rec) => {
        if (rec.status !== "recording") throw new Error(`session ${sessionId} is not recording`);
        const base = {
          id: eventId(seq),
          t: toSessionT(c.at, rec.t0),
          seq,
          source: "extension" as const,
          // A clock problem must not pass silently as "exact at t = 0".
          confidence: isSkewed(c.at, rec.t0) ? 0 : (c.confidence ?? 1),
          t_uncertainty: c.t_uncertainty ?? 0,
        };
        if (c.kind === "code_snapshot") {
          // Before the lock: always record the language. After: only when it differs.
          const lang = c.language ?? null;
          const data = { ...c.data };
          delete data.language;
          if (lang && (!rec.languageLocked || lang !== rec.language)) data.language = lang;
          return { ...base, kind: c.kind, data };
        }
        return { ...base, kind: c.kind, data: c.data } as Event;
      },
      (rec, ev) => {
        if (isSkewed(c.at, rec.t0)) rec.clockSkewed = (rec.clockSkewed ?? 0) + 1;
        if (ev.kind === "problem_loaded") {
          rec.problemLoaded = true;
          rec.title = ev.data.title;
        }
        if (ev.kind === "code_snapshot") rec.exactCode = true;
        if (ev.kind === "code_snapshot" && c.language) {
          rec.lastSnapshotLanguage = c.language;
          if (!rec.languageLocked) rec.language = c.language;
        }
        if (!rec.languageLocked && LANGUAGE_LOCK_KINDS.has(c.kind)) {
          rec.language = c.language ?? rec.lastSnapshotLanguage ?? rec.language;
          rec.languageLocked = true;
        }
      },
    );
  }

  async patchCapabilities(sessionId: string, patch: CapabilityPatch): Promise<SessionRecord> {
    return this.store.updateSession(sessionId, (rec) => {
      // The activation reading is provisional; once locked (E14) it never changes, e.g. on reload.
      if (patch.language && !rec.languageLocked) rec.language = patch.language;
      if (patch.exact_code !== undefined) rec.exactCode = patch.exact_code;
      if (patch.run_events !== undefined) rec.runEvents = patch.run_events;
      if (patch.problem_statement !== undefined) rec.problemStatement = patch.problem_statement;
    });
  }

  async setAudio(sessionId: string, audio: SessionRecord["audio"]): Promise<void> {
    await this.store.updateSession(sessionId, (rec) => {
      rec.audio = audio;
    });
  }

  async setLastAudioChunk(sessionId: string, index: number | null): Promise<void> {
    await this.store.updateSession(sessionId, (rec) => {
      rec.lastAudioChunk = index;
    });
  }

  /** Write session_end and mark the session stopped. Idempotent. */
  async stop(sessionId: string, reason: SessionEndData["reason"], at: EpochMs): Promise<SessionRecord> {
    const rec = await this.store.getSession(sessionId);
    if (!rec) throw new Error(`no session ${sessionId}`);
    if (rec.status !== "recording") return rec;
    await this.store.appendEvent(
      sessionId,
      (seq, r) => ({
        id: eventId(seq),
        t: toSessionT(at, r.t0),
        seq,
        source: "extension",
        confidence: 1,
        t_uncertainty: 0,
        kind: "session_end",
        data: { reason },
      }),
      (r, ev) => {
        r.status = "stopped";
        r.endSeq = ev.seq ?? null;
      },
    );
    return (await this.store.getSession(sessionId)) as SessionRecord;
  }

  /** A session left "recording" with no live tab (browser crash, extension reload). */
  async markInterrupted(sessionId: string): Promise<void> {
    await this.store.updateSession(sessionId, (rec) => {
      if (rec.status === "recording") rec.status = "interrupted";
    });
  }
}

/**
 * IndexedDB store shared by every extension context (same origin).
 *
 *   sessions  key: sessionId                 one record per session, holds nextSeq
 *   events    key: [sessionId, seq]          canonical events, exactly as exported
 *   chunks    key: [sessionId, stream, index] raw MediaRecorder payloads
 *
 * Seq is assigned inside the same transaction that writes the event and bumps nextSeq, so it
 * survives service-worker suspension and crashes (E2). Nothing is acked in v0 (no transport),
 * so data stays until the user deletes the session.
 */

import type { Event } from "../generated/contract";
import type { EpochMs } from "./clock";
import type { SessionMode } from "./messages";

export const DB_NAME = "interview-coach";
export const DB_VERSION = 1;

export type SessionStatus = "recording" | "stopped" | "interrupted";

export interface SessionRecord {
  sessionId: string;
  tabId: number;
  platform: string;
  adapterVersion: string;
  slug: string;
  title: string | null;
  mode: SessionMode;
  t0: EpochMs;
  wallTimeUtc: string;
  status: SessionStatus;
  nextSeq: number;
  /** Capabilities learned during capture. */
  /** Session language: provisional until `languageLocked`, then fixed (E14). */
  language: string | null;
  languageLocked: boolean;
  /** Language of the most recent snapshot, used when the lock is taken. */
  lastSnapshotLanguage: string | null;
  /** Captures stamped implausibly before t0 (clock problem); their events get confidence 0. */
  clockSkewed?: number;
  exactCode: boolean;
  runEvents: boolean;
  problemStatement: "none" | "scraped" | "manual";
  problemLoaded: boolean;
  audio: null | { mime: string; offsetS: number };
  /** Seq of session_end once written. */
  endSeq: number | null;
  /** Last audio chunk index once the recorder stopped. */
  lastAudioChunk: number | null;
}

export interface ChunkRow {
  sessionId: string;
  stream: "audio" | "video";
  index: number;
  startMs: number;
  bytes: ArrayBuffer;
}

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

function done(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error ?? new Error("transaction aborted"));
  });
}

export class Store {
  private constructor(private readonly db: IDBDatabase) {}

  static async open(factory: IDBFactory = indexedDB, name = DB_NAME): Promise<Store> {
    const open = factory.open(name, DB_VERSION);
    open.onupgradeneeded = () => {
      const db = open.result;
      db.createObjectStore("sessions", { keyPath: "sessionId" });
      db.createObjectStore("events", { keyPath: ["sessionId", "seq"] });
      db.createObjectStore("chunks", { keyPath: ["sessionId", "stream", "index"] });
    };
    return new Store(await req(open));
  }

  close(): void {
    this.db.close();
  }

  async createSession(rec: SessionRecord): Promise<void> {
    const tx = this.db.transaction("sessions", "readwrite");
    tx.objectStore("sessions").add(rec);
    await done(tx);
  }

  async getSession(sessionId: string): Promise<SessionRecord | undefined> {
    return req(this.db.transaction("sessions").objectStore("sessions").get(sessionId));
  }

  async listSessions(): Promise<SessionRecord[]> {
    const all = await req(this.db.transaction("sessions").objectStore("sessions").getAll());
    return (all as SessionRecord[]).sort((a, b) => b.t0 - a.t0);
  }

  /** Read-modify-write a session record atomically. Returns the updated record. */
  async updateSession(sessionId: string, fn: (rec: SessionRecord) => void): Promise<SessionRecord> {
    const tx = this.db.transaction("sessions", "readwrite");
    const store = tx.objectStore("sessions");
    const rec = (await req(store.get(sessionId))) as SessionRecord | undefined;
    if (!rec) throw new Error(`no session ${sessionId}`);
    fn(rec);
    store.put(rec);
    await done(tx);
    return rec;
  }

  /**
   * Assign the next seq and store the event built for it, in one transaction.
   * `build` must be synchronous (an await inside would let the transaction auto-commit).
   * `after` may update the session record in the same transaction.
   */
  async appendEvent(
    sessionId: string,
    build: (seq: number, rec: SessionRecord) => Event,
    after?: (rec: SessionRecord, ev: Event) => void,
  ): Promise<Event> {
    const tx = this.db.transaction(["sessions", "events"], "readwrite");
    const sessions = tx.objectStore("sessions");
    const rec = (await req(sessions.get(sessionId))) as SessionRecord | undefined;
    if (!rec) throw new Error(`no session ${sessionId}`);
    const seq = rec.nextSeq;
    const ev = build(seq, rec);
    if (ev.seq !== seq) throw new Error("built event has the wrong seq");
    tx.objectStore("events").add({ sessionId, ...ev });
    rec.nextSeq = seq + 1;
    after?.(rec, ev);
    sessions.put(rec);
    await done(tx);
    return ev;
  }

  async listEvents(sessionId: string): Promise<Event[]> {
    const range = IDBKeyRange.bound([sessionId, 0], [sessionId, Number.MAX_SAFE_INTEGER]);
    const rows = (await req(this.db.transaction("events").objectStore("events").getAll(range))) as Array<
      Event & { sessionId?: string }
    >;
    return rows.map(({ sessionId: _omit, ...ev }) => ev as Event);
  }

  async countEvents(sessionId: string): Promise<number> {
    const range = IDBKeyRange.bound([sessionId, 0], [sessionId, Number.MAX_SAFE_INTEGER]);
    return req(this.db.transaction("events").objectStore("events").count(range));
  }

  async putChunk(row: ChunkRow): Promise<void> {
    const tx = this.db.transaction("chunks", "readwrite");
    tx.objectStore("chunks").put(row);
    await done(tx);
  }

  async listChunks(sessionId: string, stream: ChunkRow["stream"]): Promise<ChunkRow[]> {
    const range = IDBKeyRange.bound([sessionId, stream, 0], [sessionId, stream, Number.MAX_SAFE_INTEGER]);
    return (await req(this.db.transaction("chunks").objectStore("chunks").getAll(range))) as ChunkRow[];
  }

  async countChunks(sessionId: string, stream: ChunkRow["stream"]): Promise<number> {
    const range = IDBKeyRange.bound([sessionId, stream, 0], [sessionId, stream, Number.MAX_SAFE_INTEGER]);
    return req(this.db.transaction("chunks").objectStore("chunks").count(range));
  }

  async deleteSession(sessionId: string): Promise<void> {
    const tx = this.db.transaction(["sessions", "events", "chunks"], "readwrite");
    tx.objectStore("sessions").delete(sessionId);
    tx.objectStore("events").delete(IDBKeyRange.bound([sessionId, 0], [sessionId, Number.MAX_SAFE_INTEGER]));
    tx.objectStore("chunks").delete(
      IDBKeyRange.bound([sessionId, "", 0], [sessionId, "￿", Number.MAX_SAFE_INTEGER]),
    );
    await done(tx);
  }
}

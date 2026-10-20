/**
 * Offline bundle export: one zip with a top-level `session_<id>/` folder that holds the bundle
 * exactly as on disk (docs/design.md "Session bundle", decisions 001 D5):
 *
 *   session_<id>/manifest.json
 *   session_<id>/events.jsonl
 *   session_<id>/media/audio/000000.webm ... + chunks.jsonl
 */

import { strToU8, zipSync, type Zippable } from "fflate";

import type { Capabilities, Event, Manifest } from "../generated/contract";
import { SCHEMA_VERSION } from "../generated/version";
import type { ChunkRow, SessionRecord } from "./store";

export interface BundleInput {
  session: SessionRecord;
  events: Event[];
  audioChunks: ChunkRow[];
}

export function chunkFilename(index: number, ext = "webm"): string {
  return `${String(index).padStart(6, "0")}.${ext}`;
}

function mimeExt(mime: string): string {
  const sub = mime.split("/")[1]?.split(";")[0]?.trim() ?? "";
  return ({ webm: "webm", ogg: "ogg", mp4: "mp4", wav: "wav" } as Record<string, string>)[sub] ?? "bin";
}

export function buildManifest({ session, events, audioChunks }: BundleInput): Manifest {
  const capabilities: Capabilities = {
    platform: session.platform,
    adapter_version: session.adapterVersion,
    language: session.language ?? "unknown",
    mode: session.mode,
    exact_code: session.exactCode,
    run_events: session.runEvents,
    keystrokes: "editor_scoped",
    problem_statement: session.problemStatement,
    audio: session.audio !== null && audioChunks.length > 0,
    video: false,
  };
  const lastSeq = events.reduce((m, e) => Math.max(m, e.seq ?? 0), 0);
  const lastChunk = audioChunks.reduce((m, c) => Math.max(m, c.index), -1);
  const ended = session.status === "stopped" && session.endSeq !== null;
  return {
    schema_version: SCHEMA_VERSION,
    session_id: session.sessionId,
    capabilities,
    clock_origin: { wall_time_utc: session.wallTimeUtc },
    media: {
      audio: capabilities.audio && session.audio ? { mime: session.audio.mime, offset_s: session.audio.offsetS } : null,
      video: null,
    },
    user_inputs: { self_assessment: null, target_time_s: null, reference_solution: null, tests: null },
    end: ended
      ? {
          final_seq: Math.max(lastSeq, session.endSeq ?? 0),
          final_chunk: capabilities.audio ? { audio: session.lastAudioChunk ?? lastChunk } : {},
        }
      : null,
  };
}

/** File path (inside the bundle folder) -> bytes. */
export function buildBundleFiles(input: BundleInput): Record<string, Uint8Array> {
  const manifest = buildManifest(input);
  const events = [...input.events].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
  const files: Record<string, Uint8Array> = {
    "manifest.json": strToU8(JSON.stringify(manifest, null, 2) + "\n"),
    "events.jsonl": strToU8(events.map((e) => JSON.stringify(e) + "\n").join("")),
  };
  if (manifest.media?.audio) {
    const ext = mimeExt(manifest.media.audio.mime);
    const chunks = [...input.audioChunks].sort((a, b) => a.index - b.index);
    const index: string[] = [];
    for (const c of chunks) {
      files[`media/audio/${chunkFilename(c.index, ext)}`] = new Uint8Array(c.bytes);
      index.push(JSON.stringify({ index: c.index, start_ms: c.startMs, bytes: c.bytes.byteLength }) + "\n");
    }
    files["media/audio/chunks.jsonl"] = strToU8(index.join(""));
  }
  return files;
}

export function bundleFolderName(sessionId: string): string {
  return `session_${sessionId}`;
}

export function buildBundleZip(input: BundleInput): Uint8Array {
  const folder = bundleFolderName(input.session.sessionId);
  const tree: Zippable = {};
  for (const [path, bytes] of Object.entries(buildBundleFiles(input))) {
    // Media is already compressed; store it as is.
    tree[`${folder}/${path}`] = path.startsWith("media/") ? [bytes, { level: 0 }] : bytes;
  }
  return zipSync(tree, { level: 6, mtime: new Date(input.session.wallTimeUtc) });
}

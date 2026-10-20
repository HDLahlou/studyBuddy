/**
 * Replays the captures behind fixtures/two_sum_basic through the real session code, store and
 * bundle exporter (the same code the service worker runs), then checks the zip:
 *  - every event and the manifest validate against schema/generated/*.schema.json;
 *  - the events equal the fixture's;
 *  - the zip is written to test-output/ for schema/tests/test_extension_bundle.py, which reads
 *    it with the Python bundle reader (ic_schema.read_bundle).
 */
import "fake-indexeddb/auto";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { IDBFactory } from "fake-indexeddb";
import { strFromU8, unzipSync } from "fflate";
import { beforeAll, describe, expect, it } from "vitest";

import type { Event, Manifest } from "../src/generated/contract";
import { buildBundleZip, buildManifest } from "../src/shared/bundle";
import type { Capture } from "../src/shared/messages";
import { Recorder } from "../src/shared/session";
import { Store, type ChunkRow, type SessionRecord } from "../src/shared/store";

const REPO = join(__dirname, "..", "..");
const FIXTURE = join(REPO, "fixtures", "two_sum_basic");
const SCHEMAS = join(REPO, "schema", "generated");
const OUT = join(__dirname, "..", "test-output");

const T0 = 1_760_886_131_250; // arbitrary epoch ms for session_start

function jsonl<T>(path: string): T[] {
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}

const withDefaults = (e: Event): Event => ({ confidence: 1, t_uncertainty: 0, ...e });

function validator(name: string) {
  const ajv = new Ajv2020({ strict: false, allErrors: true });
  addFormats(ajv);
  return ajv.compile(JSON.parse(readFileSync(join(SCHEMAS, `${name}.schema.json`), "utf8")));
}

const fixtureEvents = jsonl<Event>(join(FIXTURE, "events.jsonl"));
const fixtureManifest = JSON.parse(readFileSync(join(FIXTURE, "manifest.json"), "utf8")) as Manifest;

let session: SessionRecord;
let events: Event[];
let chunks: ChunkRow[];
let zip: Uint8Array;

beforeAll(async () => {
  const store = await Store.open(new IDBFactory());
  const recorder = new Recorder(store);
  const id = fixtureManifest.session_id;
  await recorder.start({
    tabId: 1,
    platform: "leetcode",
    adapterVersion: fixtureManifest.capabilities.adapter_version,
    slug: "two-sum",
    url: "https://leetcode.com/problems/two-sum/",
    mode: fixtureManifest.capabilities.mode,
    t0: T0,
    sessionId: id,
    wallTime: new Date(fixtureManifest.clock_origin.wall_time_utc),
  });
  // What the content script reports at activation.
  await recorder.patchCapabilities(id, { language: "python3", run_events: true, problem_statement: "scraped" });

  // Audio, as the offscreen document writes it.
  const audioDir = join(FIXTURE, "media", "audio");
  const index = jsonl<{ index: number; start_ms: number }>(join(audioDir, "chunks.jsonl"));
  await recorder.setAudio(id, { mime: fixtureManifest.media!.audio!.mime, offsetS: fixtureManifest.media!.audio!.offset_s! });
  for (const c of index) {
    const file = readFileSync(join(audioDir, `${String(c.index).padStart(6, "0")}.webm`));
    const bytes = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength) as ArrayBuffer;
    await store.putChunk({ sessionId: id, stream: "audio", index: c.index, startMs: c.start_ms, bytes });
  }

  // Captures, in the fixture's order, with the fixture's times.
  for (const ev of fixtureEvents) {
    if (ev.kind === "session_start" || ev.kind === "session_end") continue;
    const capture = {
      kind: ev.kind,
      data: ev.data,
      at: T0 + ev.t * 1000,
      ...(ev.confidence !== undefined ? { confidence: ev.confidence } : {}),
      ...(ev.t_uncertainty !== undefined ? { t_uncertainty: ev.t_uncertainty } : {}),
      language: "python3", // what the content script reads from the picker on every capture
    } as Capture;
    const stored = await recorder.capture(id, capture);
    expect(stored.id).toBe(ev.id);
  }
  await recorder.setLastAudioChunk(id, index.at(-1)!.index);
  const end = fixtureEvents.at(-1)!;
  await recorder.stop(id, "user_stop", T0 + end.t * 1000);

  session = (await store.getSession(id))!;
  events = await store.listEvents(id);
  chunks = await store.listChunks(id, "audio");
  zip = buildBundleZip({ session, events, audioChunks: chunks });
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, "two_sum_basic.zip"), zip);
});

describe("fixture replay: two_sum_basic", () => {
  it("reproduces the fixture's events exactly", () => {
    expect(events).toEqual(fixtureEvents.map(withDefaults));
  });

  it("every exported event validates against the generated event schema", () => {
    const validate = validator("event");
    for (const ev of events) {
      expect(validate(ev), `${ev.id}: ${JSON.stringify(validate.errors)}`).toBe(true);
    }
  });

  it("the manifest validates and matches the fixture apart from user inputs", () => {
    const manifest = buildManifest({ session, events, audioChunks: chunks });
    const validate = validator("manifest");
    expect(validate(manifest), JSON.stringify(validate.errors)).toBe(true);
    const { user_inputs: _a, ...mine } = manifest;
    const { user_inputs: _b, ...theirs } = fixtureManifest;
    expect({ ...mine, clock_origin: { wall_time_utc: new Date(mine.clock_origin.wall_time_utc).toISOString() } }).toEqual({
      ...theirs,
      clock_origin: { wall_time_utc: new Date(theirs.clock_origin.wall_time_utc).toISOString() },
    });
  });

  it("zips the bundle under session_<id>/ with media stored byte for byte", () => {
    const files = unzipSync(zip);
    const folder = `session_${fixtureManifest.session_id}`;
    const names = Object.keys(files).sort();
    expect(names).toContain(`${folder}/manifest.json`);
    expect(names).toContain(`${folder}/events.jsonl`);
    expect(names).toContain(`${folder}/media/audio/chunks.jsonl`);
    expect(names.every((n) => n.startsWith(`${folder}/`))).toBe(true);
    const audioNames = readdirSync(join(FIXTURE, "media", "audio")).filter((n) => n.endsWith(".webm"));
    for (const n of audioNames) {
      expect(Buffer.from(files[`${folder}/media/audio/${n}`]!)).toEqual(readFileSync(join(FIXTURE, "media", "audio", n)));
    }
    expect(strFromU8(files[`${folder}/media/audio/chunks.jsonl`]!)).toBe(
      readFileSync(join(FIXTURE, "media", "audio", "chunks.jsonl"), "utf8"),
    );
    const lines = strFromU8(files[`${folder}/events.jsonl`]!).trimEnd().split("\n");
    expect(lines.map((l) => (JSON.parse(l) as Event).seq)).toEqual(events.map((e) => e.seq));
  });
});

describe("manifest edge cases", () => {
  const base = (): SessionRecord => ({ ...session });

  it("an interrupted session exports with end = null (incomplete)", () => {
    const m = buildManifest({ session: { ...base(), status: "interrupted", endSeq: null }, events, audioChunks: chunks });
    expect(m.end).toBeNull();
  });

  it("a session without audio chunks reports audio: false and no media", () => {
    const m = buildManifest({ session: base(), events, audioChunks: [] });
    expect(m.capabilities.audio).toBe(false);
    expect(m.media).toEqual({ audio: null, video: null });
    expect(m.end).toEqual({ final_seq: 31, final_chunk: {} });
  });

  it("an unknown language is exported as 'unknown' rather than omitted", () => {
    expect(buildManifest({ session: { ...base(), language: null }, events, audioChunks: chunks }).capabilities.language).toBe("unknown");
  });
});

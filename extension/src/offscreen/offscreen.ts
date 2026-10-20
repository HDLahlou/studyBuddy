/**
 * Offscreen document: owns the microphone MediaRecorder for the whole recording (the service
 * worker can be suspended; this page cannot). Each 10 s timeslice is written straight to
 * IndexedDB as a chunk; nothing is sent anywhere in v0.
 *
 * Chunk start times use the session clock: chunk 0 starts when the recorder starts, chunk n
 * starts when chunk n-1 was delivered. Concatenating payloads in index order reproduces the
 * stream (only chunk 0 carries the WebM header).
 */

import { epochNow, type EpochMs } from "../shared/clock";
import type { OffscreenRequest, OffscreenStartResponse, OffscreenStopResponse } from "../shared/messages";
import { Store } from "../shared/store";

const TIMESLICE_MS = 10_000;
const PREFERRED_MIME = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];

interface Recording {
  sessionId: string;
  recorder: MediaRecorder;
  stream: MediaStream;
  nextIndex: number;
  boundary: EpochMs;
  t0: EpochMs;
  writes: Array<Promise<void>>;
  stopped: Promise<void>;
}

let current: Recording | null = null;
let storePromise: Promise<Store> | null = null;
const store = () => (storePromise ??= Store.open());

async function start(sessionId: string, t0: EpochMs): Promise<OffscreenStartResponse> {
  if (current) return { ok: false, error: "already recording" };
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    return { ok: false, error: `microphone unavailable: ${String(e)}` };
  }
  const mime = PREFERRED_MIME.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
  const recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 32_000 });
  let resolveStopped: () => void = () => {};
  const rec: Recording = {
    sessionId,
    recorder,
    stream,
    nextIndex: 0,
    boundary: 0,
    t0,
    writes: [],
    stopped: new Promise((r) => (resolveStopped = r)),
  };

  recorder.ondataavailable = (ev) => {
    const deliveredAt = epochNow();
    if (!ev.data.size) return;
    const index = rec.nextIndex++;
    const startMs = Math.max(0, Math.round(rec.boundary - rec.t0));
    rec.boundary = deliveredAt;
    rec.writes.push(
      (async () => {
        const bytes = await ev.data.arrayBuffer();
        await (await store()).putChunk({ sessionId, stream: "audio", index, startMs, bytes });
      })(),
    );
  };
  recorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    resolveStopped();
  };

  const started = new Promise<EpochMs>((resolve) => (recorder.onstart = () => resolve(epochNow())));
  recorder.start(TIMESLICE_MS);
  rec.boundary = await started;
  current = rec;
  return { ok: true, mime: recorder.mimeType || mime, offsetS: Math.max(0, Math.round(rec.boundary - t0)) / 1000 };
}

async function stop(): Promise<OffscreenStopResponse> {
  const rec = current;
  if (!rec) return { ok: true, lastIndex: null };
  current = null;
  if (rec.recorder.state !== "inactive") rec.recorder.stop(); // flushes the final partial chunk
  await rec.stopped;
  await Promise.all(rec.writes);
  return { ok: true, lastIndex: rec.nextIndex > 0 ? rec.nextIndex - 1 : null };
}

chrome.runtime.onMessage.addListener((msg: OffscreenRequest, _sender, sendResponse) => {
  if (msg.target !== "offscreen") return false;
  const work = msg.type === "audio/start" ? start(msg.sessionId, msg.t0) : stop();
  work.then(sendResponse, (e: unknown) => sendResponse({ ok: false, error: String(e) }));
  return true;
});

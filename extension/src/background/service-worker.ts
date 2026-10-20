/**
 * Service worker: session state machine, the session clock origin, seq assignment, routing.
 * It can be suspended at any time, so all state lives in IndexedDB (session records) and
 * chrome.storage.session (the id of the recording session). The offscreen document owns the
 * long-lived MediaRecorder. No live transport in v0: bundles are exported from export.html.
 */

import { leetcode } from "../adapters/leetcode";
import type { SiteAdapter } from "../adapters/types";
import { epochNow } from "../shared/clock";
import type {
  CaptureResponse,
  ContentCommand,
  ContentRequest,
  OffscreenRequest,
  OffscreenStartResponse,
  OffscreenStopResponse,
  QueryResponse,
  SessionMode,
  SessionSummary,
  UiRequest,
  UiResponse,
  UiStatus,
} from "../shared/messages";
import { Recorder } from "../shared/session";
import { type SessionRecord, Store } from "../shared/store";

const ADAPTERS: SiteAdapter[] = [leetcode];
const ACTIVE_KEY = "activeSessionId";
const OFFSCREEN_URL = "offscreen.html";

let storePromise: Promise<Store> | null = null;
const store = () => (storePromise ??= Store.open());
const recorder = async () => new Recorder(await store());

async function activeSession(): Promise<SessionRecord | null> {
  const { [ACTIVE_KEY]: id } = (await chrome.storage.session.get(ACTIVE_KEY)) as Record<string, string | undefined>;
  if (!id) return null;
  const rec = await (await store()).getSession(id);
  return rec && rec.status === "recording" ? rec : null;
}

function adapterFor(url: string | undefined): SiteAdapter | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return ADAPTERS.find((a) => a.matches(u)) ?? null;
  } catch {
    return null;
  }
}

// --- offscreen audio ------------------------------------------------------------------------

async function ensureOffscreen(): Promise<void> {
  const contexts = await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] });
  if (contexts.length) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: [chrome.offscreen.Reason.USER_MEDIA],
    justification: "Record microphone audio for the practice session the user started.",
  });
}

async function closeOffscreen(): Promise<void> {
  const contexts = await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] });
  if (contexts.length) await chrome.offscreen.closeDocument();
}

async function startAudio(rec: SessionRecord): Promise<OffscreenStartResponse> {
  try {
    await ensureOffscreen();
    const msg: OffscreenRequest = { target: "offscreen", type: "audio/start", sessionId: rec.sessionId, t0: rec.t0 };
    return (await chrome.runtime.sendMessage(msg)) as OffscreenStartResponse;
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

async function stopAudio(): Promise<OffscreenStopResponse> {
  try {
    const contexts = await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] });
    if (!contexts.length) return { ok: true, lastIndex: null };
    const msg: OffscreenRequest = { target: "offscreen", type: "audio/stop" };
    return (await chrome.runtime.sendMessage(msg)) as OffscreenStopResponse;
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// --- content script -------------------------------------------------------------------------

async function tellContent(tabId: number, msg: ContentCommand): Promise<boolean> {
  try {
    await chrome.tabs.sendMessage(tabId, msg);
    return true;
  } catch {
    // Tab opened before the extension was installed or reloaded: inject, then retry once.
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
      await chrome.tabs.sendMessage(tabId, msg);
      return true;
    } catch {
      return false;
    }
  }
}

async function injectProbe(tabId: number): Promise<void> {
  await chrome.scripting.executeScript({ target: { tabId }, world: "MAIN", files: ["probe.js"] });
}

// --- lifecycle ------------------------------------------------------------------------------

async function startSession(tabId: number, mode: SessionMode): Promise<UiResponse> {
  if (await activeSession()) return { ok: false, error: "A session is already recording." };
  const tab = await chrome.tabs.get(tabId);
  const adapter = adapterFor(tab.url);
  const slug = adapter && tab.url ? adapter.problemKey(new URL(tab.url)) : null;
  if (!adapter || !slug) return { ok: false, error: "Open a LeetCode problem page first." };

  const rec = await (await recorder()).start({
    tabId,
    platform: adapter.platform,
    adapterVersion: adapter.version,
    slug,
    url: adapter.canonicalUrl(slug),
    mode,
    t0: epochNow(),
  });
  await chrome.storage.session.set({ [ACTIVE_KEY]: rec.sessionId });
  await chrome.action.setBadgeText({ text: "REC" });
  await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });

  const audio = await startAudio(rec);
  if (audio.ok) await (await recorder()).setAudio(rec.sessionId, { mime: audio.mime, offsetS: audio.offsetS });
  else await closeOffscreen();

  const reached = await tellContent(tabId, { type: "sw/session-start", sessionId: rec.sessionId, needProblem: true });
  if (!reached) await (await recorder()).patchCapabilities(rec.sessionId, { exact_code: false, run_events: false });
  return { ok: true, status: await status() };
}

async function stopSession(reason: "user_stop" | "tab_closed" | "navigated_away"): Promise<void> {
  const rec = await activeSession();
  if (!rec) return;
  const at = epochNow();
  if (reason !== "tab_closed") await tellContent(rec.tabId, { type: "sw/session-stop" }).catch(() => false);
  const audio = await stopAudio();
  const r = await recorder();
  if (audio.ok) await r.setLastAudioChunk(rec.sessionId, audio.lastIndex);
  await r.stop(rec.sessionId, reason, at);
  await closeOffscreen();
  await chrome.storage.session.remove(ACTIVE_KEY);
  await chrome.action.setBadgeText({ text: "" });
}

async function summarize(rec: SessionRecord): Promise<SessionSummary> {
  const s = await store();
  const events = await s.listEvents(rec.sessionId);
  const last = events.at(-1);
  return {
    sessionId: rec.sessionId,
    slug: rec.slug,
    title: rec.title,
    status: rec.status,
    wallTimeUtc: rec.wallTimeUtc,
    durationS: rec.status === "stopped" && last ? last.t : null,
    events: events.length,
    audioChunks: await s.countChunks(rec.sessionId, "audio"),
  };
}

async function status(): Promise<UiStatus> {
  const s = await store();
  const rec = await activeSession();
  const sessions = await Promise.all((await s.listSessions()).slice(0, 20).map(summarize));
  return {
    recording: rec
      ? {
          sessionId: rec.sessionId,
          tabId: rec.tabId,
          slug: rec.slug,
          startedAt: rec.t0,
          audio: rec.audio !== null,
          events: await s.countEvents(rec.sessionId),
        }
      : null,
    sessions,
  };
}

/** Sessions left "recording" by a crash or extension reload can no longer be resumed. */
async function sweepInterrupted(): Promise<void> {
  const s = await store();
  const activeId = (await activeSession())?.sessionId;
  for (const rec of await s.listSessions()) {
    if (rec.status === "recording" && rec.sessionId !== activeId) await (await recorder()).markInterrupted(rec.sessionId);
  }
}

// --- message routing ------------------------------------------------------------------------

async function onContent(msg: ContentRequest, sender: chrome.runtime.MessageSender): Promise<unknown> {
  const rec = await activeSession();
  const fromRecordingTab = rec !== null && sender.tab?.id === rec.tabId;
  switch (msg.type) {
    case "content/query": {
      const adapter = adapterFor(msg.url);
      const slug = adapter?.problemKey(new URL(msg.url));
      const res: QueryResponse =
        fromRecordingTab && rec && slug === rec.slug
          ? { active: true, sessionId: rec.sessionId, needProblem: !rec.problemLoaded }
          : { active: false };
      return res;
    }
    case "content/inject-probe":
      if (fromRecordingTab && rec) await injectProbe(rec.tabId);
      return { ok: fromRecordingTab };
    case "content/capabilities":
      if (fromRecordingTab && rec) await (await recorder()).patchCapabilities(rec.sessionId, msg.patch);
      return { ok: fromRecordingTab };
    case "content/capture": {
      if (!fromRecordingTab || !rec) return { ok: false, error: "not recording in this tab" } satisfies CaptureResponse;
      try {
        const ev = await (await recorder()).capture(rec.sessionId, msg.capture);
        return { ok: true, id: ev.id } satisfies CaptureResponse;
      } catch (e) {
        return { ok: false, error: String(e) } satisfies CaptureResponse;
      }
    }
  }
}

async function onUi(msg: UiRequest): Promise<UiResponse> {
  switch (msg.type) {
    case "ui/start":
      return startSession(msg.tabId, msg.mode);
    case "ui/stop":
      await stopSession("user_stop");
      return { ok: true, status: await status() };
    case "ui/status":
      return { ok: true, status: await status() };
    case "ui/delete": {
      if ((await activeSession())?.sessionId === msg.sessionId) return { ok: false, error: "Stop the session first." };
      await (await store()).deleteSession(msg.sessionId);
      return { ok: true, status: await status() };
    }
  }
}

chrome.runtime.onMessage.addListener((msg: { type?: string; target?: string }, sender, sendResponse) => {
  if (msg.target === "offscreen") return false;
  const isOwnPage = sender.id === chrome.runtime.id && !sender.tab;
  let work: Promise<unknown> | null = null;
  if (msg.type?.startsWith("content/") && sender.tab) work = onContent(msg as ContentRequest, sender);
  else if (msg.type?.startsWith("ui/") && isOwnPage) work = onUi(msg as UiRequest);
  if (!work) return false;
  work.then(sendResponse, (e: unknown) => sendResponse({ ok: false, error: String(e) }));
  return true;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  void activeSession().then((rec) => (rec?.tabId === tabId ? stopSession("tab_closed") : undefined));
});

// Leaving the problem ends the session; moving between its tabs (description, submissions,
// editorial) or reloading does not, since the slug stays the same (E7).
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (!change.url && change.status !== "loading") return;
  void activeSession().then((rec) => {
    if (!rec || rec.tabId !== tabId) return;
    const url = change.url ?? tab.url;
    const adapter = adapterFor(url);
    const slug = adapter && url ? adapter.problemKey(new URL(url)) : null;
    // Without a host permission for the new page, Chrome hides its URL: that also means we left.
    if (slug !== rec.slug) return stopSession("navigated_away");
    return undefined;
  });
});

chrome.runtime.onStartup.addListener(() => void sweepInterrupted());
chrome.runtime.onInstalled.addListener(() => void sweepInterrupted());

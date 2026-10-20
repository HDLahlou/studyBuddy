/** Popup: start/stop, mode, timer, and the session list with Export / Delete. */

import { leetcode } from "../adapters/leetcode";
import type { SessionMode, SessionSummary, UiRequest, UiResponse, UiStatus } from "../shared/messages";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

async function ask(msg: UiRequest): Promise<UiResponse> {
  return (await chrome.runtime.sendMessage(msg)) as UiResponse;
}

function showError(text: string | null): void {
  const el = $("error");
  el.hidden = !text;
  el.textContent = text ?? "";
}

function fmtDuration(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

let timer: number | null = null;

function renderSessions(sessions: SessionSummary[]): void {
  const list = $("sessions");
  list.replaceChildren();
  $("empty").hidden = sessions.length > 0;
  for (const s of sessions) {
    const li = document.createElement("li");
    const title = document.createElement("div");
    title.textContent = s.title ?? s.slug;
    const meta = document.createElement("div");
    meta.className = "muted";
    const when = new Date(s.wallTimeUtc).toLocaleString();
    const dur = s.durationS !== null ? ` · ${fmtDuration(s.durationS)}` : "";
    const audio = s.audioChunks ? " · audio" : "";
    meta.textContent = `${when}${dur} · ${s.events} events${audio} · ${s.status}`;
    const row = document.createElement("div");
    row.className = "row";
    const exp = document.createElement("button");
    exp.textContent = "Export";
    exp.disabled = s.status === "recording";
    exp.onclick = () => void chrome.tabs.create({ url: chrome.runtime.getURL(`export.html?session=${encodeURIComponent(s.sessionId)}`) });
    const del = document.createElement("button");
    del.textContent = "Delete";
    del.className = "danger";
    del.disabled = s.status === "recording";
    del.onclick = async () => {
      if (!confirm(`Delete this session (${s.title ?? s.slug})? This cannot be undone.`)) return;
      const res = await ask({ type: "ui/delete", sessionId: s.sessionId });
      if (res.ok && res.status) render(res.status);
      else if (!res.ok) showError(res.error);
    };
    row.append(exp, del);
    li.append(title, meta, row);
    list.append(li);
  }
}

async function render(status: UiStatus): Promise<void> {
  const rec = status.recording;
  $("recording").hidden = !rec;
  $("idle").hidden = !!rec;
  if (timer !== null) clearInterval(timer);
  if (rec) {
    const tick = () => ($("timer").textContent = fmtDuration((Date.now() - rec.startedAt) / 1000));
    tick();
    timer = window.setInterval(tick, 1000);
    $("recinfo").textContent = `${rec.slug} · ${rec.events} events · ${rec.audio ? "mic on" : "no audio"}`;
  } else {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const slug = tab?.url ? leetcode.problemKey(new URL(tab.url)) : null;
    const onProblem = !!tab?.url && leetcode.matches(new URL(tab.url));
    $("target").textContent = onProblem ? `Problem: ${slug}` : "Open a LeetCode problem to start recording.";
    $<HTMLButtonElement>("start").disabled = !onProblem;
    const mic = await navigator.permissions.query({ name: "microphone" as PermissionName }).catch(() => null);
    $("mic").hidden = mic?.state === "granted";
  }
  renderSessions(status.sessions);
}

$("start").onclick = async () => {
  showError(null);
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return;
  const mode = $<HTMLSelectElement>("mode").value as SessionMode;
  const res = await ask({ type: "ui/start", tabId: tab.id, mode });
  if (!res.ok) showError(res.error);
  else if (res.status) await render(res.status);
};

$("stop").onclick = async () => {
  const res = await ask({ type: "ui/stop" });
  if (!res.ok) showError(res.error);
  else if (res.status) await render(res.status);
};

$("setup").onclick = (e) => {
  e.preventDefault();
  void chrome.tabs.create({ url: chrome.runtime.getURL("setup.html") });
};

void ask({ type: "ui/status" }).then((res) => (res.ok && res.status ? render(res.status) : showError(res.ok ? null : res.error)));

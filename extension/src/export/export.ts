/**
 * Builds the session zip from IndexedDB and downloads it with an <a download> link, so no
 * `downloads` permission is needed. Opened from the popup as export.html?session=<id>.
 */

import { buildBundleZip, bundleFolderName } from "../shared/bundle";
import { SESSION_ID_RE } from "../shared/ids";
import { Store } from "../shared/store";

const state = document.getElementById("state")!;
const link = document.getElementById("download") as HTMLAnchorElement;

async function main(): Promise<void> {
  const sessionId = new URLSearchParams(location.search).get("session") ?? "";
  if (!SESSION_ID_RE.test(sessionId)) throw new Error("Invalid session id.");
  const store = await Store.open();
  const session = await store.getSession(sessionId);
  if (!session) throw new Error("Session not found. It may have been deleted.");
  if (session.status === "recording") throw new Error("Stop the session before exporting it.");
  const [events, audioChunks] = await Promise.all([store.listEvents(sessionId), store.listChunks(sessionId, "audio")]);
  const zip = buildBundleZip({ session, events, audioChunks });
  const url = URL.createObjectURL(new Blob([zip as Uint8Array<ArrayBuffer>], { type: "application/zip" }));
  link.href = url;
  link.download = `${bundleFolderName(sessionId)}.zip`;
  link.hidden = false;
  link.click();
  const mb = (zip.byteLength / 1_048_576).toFixed(2);
  state.textContent = `Exported ${events.length} events and ${audioChunks.length} audio chunks (${mb} MB) as ${link.download}.`;
  state.className = session.status === "stopped" ? "ok" : "";
  if (session.status === "interrupted") state.textContent += " The session was interrupted, so the bundle is marked incomplete.";
}

main().catch((e: unknown) => {
  state.textContent = e instanceof Error ? e.message : String(e);
  state.className = "error";
});

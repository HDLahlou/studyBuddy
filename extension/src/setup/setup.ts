/**
 * One-time microphone grant. The offscreen document cannot show a permission prompt, so the
 * prompt is shown here, on a visible extension page; the grant then applies to the extension.
 */

const state = document.getElementById("state")!;

async function refresh(): Promise<void> {
  const p = await navigator.permissions.query({ name: "microphone" as PermissionName }).catch(() => null);
  if (p?.state === "granted") {
    state.textContent = "Microphone allowed. You can close this tab.";
    state.className = "ok";
  } else if (p?.state === "denied") {
    state.textContent = "Microphone blocked. Allow it for this extension in Chrome's site settings.";
    state.className = "error";
  }
}

document.getElementById("grant")!.addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
  } catch {
    // reported by refresh()
  }
  await refresh();
});

void refresh();

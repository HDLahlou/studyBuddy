// Bundle each entry point into dist/ and copy static files. Load dist/ as an unpacked extension.
import { build } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";

const entries = {
  background: "src/background/service-worker.ts",
  content: "src/content/content.ts",
  probe: "src/probe/monaco-probe.ts",
  offscreen: "src/offscreen/offscreen.ts",
  popup: "src/popup/popup.ts",
  setup: "src/setup/setup.ts",
  export: "src/export/export.ts",
};

await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });
await build({
  entryPoints: entries,
  outdir: "dist",
  bundle: true,
  format: "iife", // the service worker is declared type=module, but needs no imports at runtime
  target: "chrome116",
  sourcemap: "linked",
  logLevel: "info",
  legalComments: "none",
});
await cp("static", "dist", { recursive: true });

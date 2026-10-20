# extension

Chrome MV3 capture extension, v0: LeetCode only, with offline export. The design is in `docs/design.md` (Component 1), and the decisions are in `docs/decisions/002-extension-v0.md`.

`src/generated/` is written by `make schema`. Never edit it by hand.

## Build and load

```
npm ci
npm run build        # -> dist/
npm test             # vitest, no browser
npm run typecheck
```

To load it:

1. In Chrome, open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and select `extension/dist`. After each rebuild, click the reload icon on the extension's card.
3. The first time, use the popup's **Allow microphone** link, or open the extension's `setup.html` page.

## Layout

| Path | Runs in | What |
| --- | --- | --- |
| `src/background/` | Service worker | Session lifecycle, clock origin, seq numbers, routing, end reasons |
| `src/content/` | Content script (isolated world) | Problem scrape, run/submit and results, key categories, paste, undo, focus |
| `src/probe/` | Page main world | Monaco reader and snapshot schedule |
| `src/offscreen/` | Offscreen document | Microphone MediaRecorder, writing 10 s chunks to IndexedDB |
| `src/adapters/` | — | `SiteAdapter` interface and `leetcode.ts`. All LeetCode selectors live there. |
| `src/shared/` | All | Clock, IndexedDB store, session logic, bundle zip, internal messages |
| `src/popup/`, `src/setup/`, `src/export/` | Extension pages | Controls, mic grant, zip download |

## Manual checklist (needs a real browser)

The unit tests and fixture replay cover the logic and the bundle format. These can only be checked live:

- [ ] On a problem page, Start begins recording: the popup timer runs and the badge shows REC.
- [ ] The microphone works after the one-time grant, and the exported zip contains `media/audio/*.webm` that plays when the chunks are joined.
- [ ] Typing produces `code_snapshot` (debounce/periodic) and `keystroke` events. No characters appear outside snapshots.
- [ ] Run gives `run` → `code_snapshot(run)` → `run_result` with the right verdict and failing case.
- [ ] Submit gives `submit_result` with the case count, runtime and memory. **Also check a failing submit** (Wrong Answer, TLE): this panel wasn't captured in the DOM survey.
- [ ] Switching tabs gives `focus_change` and doesn't end the session. Reloading the page keeps recording.
- [ ] Opening a different problem in the same tab ends the session with `navigated_away`. Closing the tab ends it with `tab_closed`.
- [ ] Export downloads `session_<id>.zip`. After unzipping, `ic_schema.read_bundle` reports it complete.

# 002: Extension v0, LeetCode capture (build-plan step 2)

Oct 19, 2026 · Status: accepted · `schema_version` 1.0 (no contract change)

These are the decisions made while building the capture extension (`extension/`), where `docs/design.md` was silent or ambiguous. `docs/design.md` → Decisions links here.

Scope, as in the build plan:

- **In scope:** code snapshots, run/submit and results, problem scrape, mic audio and offline bundle export. Keystroke categories, paste, undo and focus changes are also included (E9).
- **Out of scope:** video, live transport and pause (see design → Open questions).

---

## E1. Session clock across contexts

> **Superseded by E16.** Captures are now stamped with `Date.now()`.

**Decision.**

- At start, the service worker takes `t0 = performance.timeOrigin + performance.now()` (epoch ms) and stores it in the session record.
- Every context records the epoch time when something actually happened (`at`). The service worker converts it: `t = round(at − t0) / 1000`.

**Options weighed:**

| Option | Problem |
| --- | --- |
| The service worker stamps on receipt | It adds the worker's wake-up latency, which can be hundreds of ms after a suspension. Debounced snapshots would be stamped late. |
| `performance.now()` in the service worker | It restarts at 0 whenever the worker restarts, and each context has its own origin. |
| `Date.now()` | Millisecond resolution and not monotonic. `timeOrigin + now()` is monotonic within a context. |

**Known risk.** A system clock change in the middle of a session can skew times across contexts, because each context's `timeOrigin` is wall-clock based. That's acceptable for v0. The design's spoken and hotkey sync marker remains the mitigation for audio drift.

## E2. Seq assignment and durability

- Seq is assigned inside the IndexedDB transaction that writes the event and increments `nextSeq`. So it survives service-worker suspension, crashes, and concurrent captures. A test covers 50 concurrent captures.
- Nothing is acked in v0, because there's no transport. Events and chunks stay in IndexedDB until the user deletes the session from the popup.
- **Seq is arrival order, not time order.** A keystroke burst carries its start time but is written when it ends. A run result is written when its panel settles. Consumers must sort by `t`, and the engine's Normalize stage already does. The fixture happens to be ordered both ways.

## E3. Snapshot schedule

The design specifies a 500 ms debounce, a forced snapshot every 15 s, and a snapshot on every run or submit. Clarifications:

- **The 15 s periodic snapshot fires only if the code changed since the last snapshot.** It exists for continuous typing, which never gives the debounce 500 ms of quiet. An unconditional 15 s timer would mostly add duplicates.
- **Run, submit and session start (`initial`) always take a snapshot,** even if the code is unchanged, so every run has its exact code next to it.
- **Language switches.** Switching language swaps the Monaco model, which triggers a debounced snapshot.

## E4. What runs when (privacy)

- **Content script:** declared for `https://leetcode.com/*`. It's inert until the service worker confirms a session is recording in that tab: no listeners, no reads. It's declared for all of leetcode.com, rather than only `/problems/*`, because LeetCode is a single-page app; a static match on `/problems/*` would miss problems reached by in-app navigation.
- **Main-world Monaco probe:** injected with `chrome.scripting` only when a session starts, and again after a reload of the recording tab.
- **Recording tab only.** Only the tab where recording started is captured. Captures from any other tab are rejected by the service worker.
- **Keys:** keystrokes are categories only, and only when the event target is inside the adapter's editor container.
- **Pastes:** pastes record a character count and a line count. The text is read only to count it.

## E5. Keystroke bursts

- **When a burst ends:** after 1 s with no keys, after 30 s of continuous typing, or when flushed (run, submit, paste, undo, stop).
- **Timing:** `t` is the burst start and `duration_s` its length.
- **Categories:**

  | Keys | Category |
  | --- | --- |
  | Ctrl/Cmd plus any key, or Alt plus a named key (Monaco line moves) | `shortcut` |
  | Backspace, Delete | `delete` |
  | Enter | `newline` |
  | Arrows, Home, End, PageUp, PageDown | `navigation` |
  | Printable characters, Tab, Alt plus a printable key (it types a character on macOS) | `insert` |
  | Bare modifiers, Escape | ignored |

- **Undo:** Ctrl/Cmd+Z also emits an `undo` event. Redo is only a `shortcut`; the contract has no redo kind.
- **Focus changes:**
  - **Tab switch:** fires both `visibilitychange` and `blur`, and is reported once, as `target: "tab"`.
  - **Window blur that doesn't hide the tab:** reported as `"window"`.
  - **Editor focus in and out:** reported as `"editor"`.

## E6. Result capture and failed scrapes

- After a run or submit, the content script polls the result panel every 250 ms. A result counts as new when the verdict element is a different node from the one present at click time, or its text changed. It's settled when the panel text is unchanged across two polls.
- **Timing:** the event time is when the verdict first appeared, with `t_uncertainty` 0.25 s.
- **Observed on leetcode.com:** the old result disappears within 300 ms of the click, and the new verdict appears about 3.4 s later.
- **Failed scrape.** If no result settles within 30 s, or the panel can't be read, the extension emits `run_result` / `submit_result` with `verdict: "unknown"` and `confidence: 0.0`. `Capabilities.run_events` means "run and submit buttons were found". This is the interim answer to the open question in design.md; there's no contract change.
- **Stopping mid-wait:** if the session stops while a result is pending, that result isn't recorded.
- **Submit navigation:** LeetCode moves to `/problems/<slug>/submissions/<id>/` after a submit. The slug is the same, so the session continues (E7).

## E7. Session end reasons

| Event | Reason |
| --- | --- |
| Popup Stop | `user_stop` |
| Recording tab closed | `tab_closed` |
| The tab's problem slug changes, or the tab leaves leetcode.com | `navigated_away` |

**Not end events:**

- Switching tabs or windows (recorded as `focus_change`).
- Moving between a problem's sub-pages (description, submissions, editorial).
- Reloading the page.
- An accepted submit.

Without a host permission for the new page, Chrome hides its URL. A missing URL therefore also counts as leaving, so no `tabs` permission is needed.

**Interrupted sessions.** A session still marked `recording` when the browser or extension restarts is marked `interrupted`. It can still be exported, with `manifest.end = null`, so it reads as incomplete.

## E8. Permissions

- **Requested:**
  - permissions `offscreen`, `storage`, `scripting`
  - host `https://leetcode.com/*`
- **Not requested in v0:**
  - `tabCapture` (video is step 6)
  - `http://127.0.0.1/*` (live transport is step 6)
  - `downloads`: export uses an `<a download>` link on `export.html`
  - `tabs`: see E7
  - `<all_urls>`
- **Microphone.** An offscreen document can't show a permission prompt, so `setup.html` asks for the microphone once, on a visible extension page. If permission is missing or denied, the session records with `capabilities.audio = false`.

## E9. Scope additions beyond the step-2 list

Keystroke categories, paste, undo and focus changes aren't named in build-plan step 2. They're included because the fixture and engine step 3 ("merge keystroke bursts", focus-away spans) expect them, and they come from the same content script.

## E10. Adapter interface, refined

The design's `SiteAdapter` sketch was adjusted:

- `editor()` became `editorSelector`, because the main-world probe reads the editor and only needs to know where it is.
- `readResult()` was split into `runResult` and `submitResult` readers, because the two panels differ.
- Added:
  - `problemKey`, which the `navigated_away` rule needs.
  - `readLanguage`, which reads the language picker. `Capabilities.language` uses LeetCode's slug (e.g. `cpp`, `python3`), with Monaco's language id as a fallback.
  - `actionForClick` and `actionForKey`. LeetCode's run shortcut is Ctrl/Cmd+' and its submit shortcut is Ctrl/Cmd+Enter.
  - `hasRunButtons`.
- All parsing functions take a root node, so they're tested on saved HTML (`extension/test/dom/leetcode/`).

**Verification status.** Selectors were checked live on 2026-10-19 for: the problem page; Wrong Answer, Accepted and Compile Error run panels; and fresh Wrong Answer and Accepted submissions (see E13). Submit TLE, runtime-error and compile-error panels haven't been observed. They are expected to use the same `<h3>` heading, and fall back to verdict-only.

## E11. Export format

- **Zip layout:** one top-level folder, `session_<id>/`, containing exactly the on-disk bundle: `manifest.json`, `events.jsonl` sorted by seq, `media/audio/<index>.webm` plus `chunks.jsonl`.
- **Compression:** media is stored uncompressed (`level 0`); JSON is deflated.
- **Manifest values:**
  - `user_inputs` are null; the GUI fills them in later.
  - `capabilities.language` is `"unknown"` if it was never read.
  - `capabilities.audio` is true only when chunks exist.
- **Cross-language check.** `extension/test/fixture-replay.test.ts` replays `fixtures/two_sum_basic` through the real session, store and exporter code. `schema/tests/test_extension_bundle.py` then reads the zip with `ic_schema.read_bundle` and checks it's complete and identical to the fixture. `make test` runs them in that order.

## E12. Session IDs

The format is `<UTC yyyymmddThhmmssZ>_<slug>_<6 random chars>`, e.g. `20261019T150211Z_two-sum_k3f9q2`. It matches the contract's `^[A-Za-z0-9_-]{1,64}$`, sorts by time, and is readable in a file browser.

## Tooling

- **Build:** esbuild (one IIFE bundle per entry point, then copy `static/`).
- **Tests:** vitest with happy-dom (DOM), fake-indexeddb (store) and ajv (JSON Schema).
- **Zip:** fflate.
- **TypeScript:** strict. `tsconfig.test.json` adds Node types for tests only, so extension code can't use Node APIs.
- `make schema` now also emits `SCHEMA_VERSION` constants for TS (`extension/src/generated/version.ts`) and Dart.

## E13. Fixes from the first real session (adapter 0.2.0)

A 16-minute Valid Parentheses session, recorded and checked on 2026-10-19, found three submit bugs. The fixed panels were captured live; `extension/test/dom/leetcode/` has the markup.

1. **A late verdict was credited to an earlier submit.** Two submits were waiting at once, and both took the second one's Accepted panel. Now, starting a run or submit *supersedes* any unsettled earlier wait of the same kind. The superseded click is recorded as `verdict: "unknown"`, `confidence: 0` (`ResultTracker`). Runs and submits use different panels, so they don't affect each other.
2. **Failed submissions weren't detected.** They carry no `data-e2e-locator`. The verdict is an `<h3 class="text-xl ...">` whose own text is the verdict, with "x / y testcases passed" nested inside it. The adapter now finds this heading, reads only its own text, and parses Input/Output/Expected with the same section parser as the run panel. The tab strip also shows a verdict-named tab title; it isn't mistaken for the result.
3. **Accepted submits had no case count, runtime or memory.** Two causes:
   - The verdict renders about 300 ms before the stats, so two 250 ms polls could settle early. Result readers now have an optional `ready()` check (for submit: "testcases passed" has rendered), with a 5 s grace period for panels that never show it.
   - `textContent` joins units to the next word ("3msBeats"), which defeated a `\b` in the metric regex.

`ADAPTER_VERSION` is now 0.2.0.

## E14. Session language locks at the first action

**Problem.** `Capabilities.language` was read from the language picker at session start, before the user had chosen a language. The real session opened in C++ and switched to Java 7 s in, so the manifest said `cpp` for a Java solution.

**Decision.** The user's premise is that the language only changes at the start of a problem. So:

- The activation reading is **provisional**. It follows each snapshot's language until the session language **locks** at the first `keystroke`, `paste`, `undo`, `run` or `submit`. The lock uses the picker's reading at that moment, falling back to the last snapshot's language.
- **Before the lock,** every snapshot carries `data.language`, even when it equals the final language. **After the lock,** a snapshot carries it only when it differs, which is rare.
- Focus changes and the problem load don't lock it. A session with no edits, runs or submits keeps the provisional value.
- A page reload's re-activation can't change a locked language.
- **Contract:** the `CodeSnapshotData.language` description was clarified to allow pre-lock snapshots. There's no structural change and the version stays 1.0, as the user chose on 2026-10-19. A reader's rule is unchanged: if `language` is absent, use `Capabilities.language`. `fixtures/*/events.jsonl` `ev_3` now carries `"language":"python3"`, because it's the only snapshot before the first keystroke.

**Options weighed:**

| Option | Verdict |
| --- | --- |
| Record `language` on every snapshot (schema 1.1) | Rejected. Readers keep the old rule anyway (minor bump), the manifest would still be wrong, and it means churn in all components. |
| Set `Capabilities.language` from the last snapshot at export | Rejected. It stops working once events stream live (step 6). |
| **Lock at the first action (chosen)** | Extension-only. Accurate for both language-switch and no-switch sessions. |

**Deferred cost (step 6).** Live `hello` is sent at session start, before the lock. Step 6 must either delay `hello` until the lock, or add a way to send the locked language afterwards. The second option would be a protocol addition.

**Step 3.** The engine should also report the solution language from the final snapshot (snapshot `language`, falling back to `Capabilities.language`), independent of the lock.

## E15. Ignored clicks and runtime-error inputs (adapter 0.3.0)

A second real session (Longest Palindromic Substring, 20 min, Java) had two `unknown` runs, recorded on 2026-10-19. A live investigation in Chrome the same day showed the cause:

- **While a run is pending,** LeetCode styles the Run button `cursor-not-allowed opacity-50`, until the result appears about 3 s later. It doesn't set `disabled`, so click events still fire, but LeetCode ignores them: one result for three clicks. There's no cooldown after a result; a click 0.8 s later runs normally.
- **In the session,** a slow run (the judge took over 9 s) was followed by two clicks during its pending state. The extension recorded both as runs. The first superseded the wait for the real run (E13 rule) and was recorded `unknown`, and the eventual result was probably credited to the last ignored click.

**Fixes:**

1. `SiteAdapter.actionPending(root, action)` reads the button state. The content script drops a click or shortcut on a pending button: it isn't recorded as a run and doesn't supersede anything. The Submit button is assumed to behave the same, which hasn't been observed.
2. Runtime Error run panels label the failing case **"Last Executed Input"**. That label element also contains an "Open Testcase" link, so section labels are now matched by their *own* text, not as leaf elements. The run and submit readers both try "Last Executed Input" before "Input".

**Not recorded:** ignored clicks themselves (impatience may be a useful signal, but the contract has no kind for it). Bundles exported before 0.3.0 may contain these phantom runs. They show as a `run` followed by an `unknown` result, close to the next click.

## E16. Wall-clock stamps (supersedes E1)

**Problem.** A real session recorded on 2026-10-19 had every content-script event at `t = 0`. The LeetCode tab had been open before the Mac slept. `performance.now()` doesn't advance during sleep, so the page's `timeOrigin + now()` ran behind the fresh service worker's clock. Every capture landed before `t0`, and the never-negative clamp hid it.

**Decision.**

- All contexts stamp captures with `Date.now()`. It's the same system clock everywhere, unaffected by when a context started or by sleep.
- A capture more than 1 s before `t0` is recorded with `confidence: 0`, and counted in the session record (`clockSkewed`), instead of passing silently as exact.

**Trade-off.** `Date.now()` has millisecond resolution, and can jump when the system syncs its clock. Both are acceptable for a timeline measured in tenths of a second. Sleep during a session now shows up as real elapsed time, which is correct.

## Carried into step 3 (engine v0)

Agreed on 2026-10-19: seq is delivery order and `t` is timeline order (E2), but nothing orders by `t` yet. Step 3 will:

1. Add `Bundle.timeline()` to `ic_schema`. It returns captured and derived events sorted by `(t, seq)`, and the engine and AI layer use only this ordering.
2. Replace the "captured events must be time-ordered by seq" assertion in `schema/tests/test_fixtures.py`. Real captures break that rule. The replacement checks seqs unique and contiguous, `t` within the session, and each result after its run/submit.
3. Add a fixture in the shape the real extension writes, with a keystroke burst stored after a later snapshot.
4. Note in decisions 001 (D1) that consumers must order by `t`, not seq.
5. MediaRecorder WebM has no duration header (`ffprobe` reports N/A). Transcription must decode the stream rather than trust the header. The real session decoded to 954.0 s, against 953.94 s expected.
6. Report the solution language from the final snapshot (E14).

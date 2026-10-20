# Interview Coach — System Design

Oct 19, 2026 · @Hakim

## Overview

Interview Coach reviews recorded LeetCode-style practice sessions and returns timed, evidence-backed feedback: where time went, what went well, what cost time, and whether the solution is correct and optimal.

Scope for v1 is browser-based platforms (LeetCode first, HackerRank and similar via adapters). Capture happens in the page, so code, runs and results are exact; video is kept for playback and as fallback evidence, not as the primary data source.

The system has three components joined by one contract, the **session bundle**:

1. **Capture (Chrome extension)** records the session in the browser and emits a stream of timestamped events plus audio and tab video.
2. **Prepare (Python engine + Flutter GUI)** ingests the bundle, transcribes audio, builds and segments the unified timeline, computes metrics, and runs the code against tests.
3. **Analyze (AI orchestration)** turns the prepared timeline into a structured, timestamp-grounded feedback report.

&#91;embedded content: architecture · 3 components + GUI\]

The extension hands the engine a bundle; the engine hands the AI a timeline with all numbers already computed; the GUI drives the engine and shows the report.

Each component can be built and tested on its own against the bundle format: the engine can replay a saved bundle, and the AI layer can run on a saved timeline.

## Shared contract

Every component reads or writes the same three things: a canonical event, a capability manifest, and a session bundle. Define these first and version them; everything else can change behind them.

### Canonical event

```python
class Event(BaseModel):
    id: str
    t: float                 # seconds from session start (monotonic clock)
    kind: Literal[
        "session_start", "session_end",
        "problem_loaded",     # statement, title, difficulty, examples
        "code_snapshot",      # full editor text
        "code_diff",          # derived by engine from snapshots
        "keystroke",          # editor-scoped key category, not raw text
        "paste", "undo",
        "run", "submit",
        "run_result", "submit_result",  # verdict, failing case, runtime
        "focus_change",       # left/returned to the tab or editor
        "speech",             # transcript segment (engine-produced)
        "idle",               # derived gap
        "marker",             # user hotkey: stuck, idea, done
    ]
    data: dict
    source: Literal["extension", "engine", "whisper", "user"]
    confidence: float = 1.0  # 1.0 = exact
    t_uncertainty: float = 0.0
```

### Capability manifest

Recorded per session so later stages know what they can trust and what to skip.

```python
class Capabilities(BaseModel):
    platform: str             # "leetcode", "hackerrank", ...
    adapter_version: str
    language: str             # editor language as reported by the platform
    exact_code: bool
    run_events: bool
    keystrokes: Literal["none", "editor_scoped"]
    problem_statement: Literal["none", "scraped", "manual"]
    audio: bool
    video: bool
```

### Session bundle

One folder (or zip) per session, the only thing that crosses component boundaries:

```
session_<id>/
  manifest.json        # schema_version, capabilities, clock origin, user inputs
  events.jsonl         # append-only canonical events
  audio.webm           # mic, chunked during capture, joined on ingest
  video.webm           # tab capture (optional, playback only)
  inputs/              # optional: final assessment, reference solution, tests
  derived/             # engine output: timeline.json, metrics.json, sandbox.json
  report/              # AI output: report.json, prompts + responses for audit
```

All times are seconds from `session_start`, taken from one clock in the extension; audio and video record their own offset from that origin in the manifest.

## Component 1: Chrome extension (capture)

The extension's only job is faithful capture: exact events with timestamps, plus audio and optional video. It does no analysis, which keeps it small and keeps Manifest V3 limits from mattering.

### Parts

| Part | Runs in | Responsibility |
| --- | --- | --- |
| Page probe | Page main world (injected script) | Reads the editor model (e.g. Monaco `getValue()`), listens for content changes, reports code snapshots |
| Content script | Isolated world | Site adapter: scrapes problem statement, watches Run/Submit and result panels, editor-scoped key and paste events; relays to the service worker |
| Service worker | Background | Session state machine, the single clock, batching, forwarding to the engine |
| Offscreen document | Offscreen page | `MediaRecorder` for mic audio and `tabCapture` video, emitted as 10-second chunks |
| Popup / side panel | Extension UI | Session controls: start, stop, pause, mode, timer, connection status, optional hotkeys |

### What it captures

- **Code:** a full snapshot on change, debounced (about 500 ms of quiet) plus a forced snapshot every 15 s and on every run or submit. The engine derives diffs; the extension never has to.
- **Runs and results:** run and submit clicks, then the verdict, failing input, expected vs actual output, and runtime, read from the result panel once it settles.
- **Problem:** title, difficulty, statement text, examples and constraints, once at start.
- **Keystrokes:** editor-scoped only, stored as categories (insert, delete, newline, navigation, shortcut) with counts per burst, not raw characters. The code snapshots already hold the text.
- **Paste, undo, focus changes:** to show leaving the page to look something up, and large pastes.
- **Markers:** optional hotkeys for "stuck", "have an idea", "done", off by default. Nothing depends on them: spoken cues and engine signals flag the same moments, and markers can be added later during review.

### Transport

Events and media stream live to the engine over a localhost WebSocket. Exporting a bundle zip is only the fallback for when the engine isn't running.

```
content script ──msg──► service worker ──msg──► offscreen document ──WS──► engine /ingest
(code, runs, keys)      (clock, seq numbers)     (MediaRecorder + socket)
```

#### Connection

- The engine binds `127.0.0.1:8765` (configurable in the GUI) and serves `WS /ingest`.
- **Pairing:** the GUI shows a one-time token; you paste it into the extension once, which stores it in `chrome.storage`. Every connection carries it.
- **The offscreen document owns the socket.** It lives for the whole recording and already produces the media chunks; the MV3 service worker can be suspended, so it only stamps and relays events.
- The extension declares `http://127.0.0.1/*` in `host_permissions`.

#### Message protocol

| Direction | Frame | Message | Purpose |
| --- | --- | --- | --- |
| Extension → engine | text | `hello {session_id, schema_version, adapter, capabilities, resume_from}` | Open or resume a session |
| Engine → extension | text | `welcome {session_id, last_seq, last_chunk}` | Confirms what the engine already has |
| Extension → engine | text | `event {seq, ...Event}` | One canonical event |
| Extension → engine | binary | 16-byte header (stream, chunk index, start ms) + media bytes | Audio or video chunk, about 10 s each |
| Engine → extension | text | `ack {seq, chunk}` | Lets the extension prune its buffer |
| Both | text | `ping` / `pong` every 20 s | Keepalive, dead-connection detection |
| Extension → engine | text | `end {final_seq, final_chunk}` | Closes the session cleanly |
| Engine → extension | text | `error {code, retryable}` | Bad token, schema mismatch, disk full |

#### Reliability

- Every event and chunk is written to IndexedDB before it is sent, and pruned only when acked.
- The engine acks events every 20 messages or 2 seconds, and each media chunk individually.
- On disconnect, the extension reconnects with backoff (1 s up to 30 s) and sends `hello` with `resume_from`; the engine dedupes by `seq`, so replaying is always safe.
- The engine appends to `events.jsonl` and writes chunk files as they arrive, and marks the session incomplete until `end` arrives and all sequences are contiguous.
- If the engine is unreachable for the whole session, the extension exports the buffered bundle as a zip for import in the GUI.

#### Security

- Bind to the loopback address only, never `0.0.0.0`.
- **Check the `Origin` header** equals `chrome-extension://<extension id>`. Browsers don't apply CORS to WebSockets, so any website you visit could otherwise open a socket to localhost.
- Reject connections without the pairing token; the GUI can rotate it.
- Cap frame size and message rate to bound memory use.

#### Engine handler (sketch)

```python
@app.websocket("/ingest")
async def ingest(ws: WebSocket, token: str):
    if ws.headers.get("origin") != EXTENSION_ORIGIN or not tokens.valid(token):
        await ws.close(code=4403)
        return
    await ws.accept()
    hello = Hello.model_validate(await ws.receive_json())
    session = SessionWriter.open_or_resume(hello)
    await ws.send_json({"type": "welcome", **session.position()})
    while True:
        msg = await ws.receive()
        if msg.get("text"):
            m = json.loads(msg["text"])
            if m["type"] == "event":
                session.append(Event.model_validate(m))     # dedupes by seq
            elif m["type"] == "end":
                session.close(m); break
        elif msg.get("bytes"):
            idx = session.write_chunk(msg["bytes"])          # parses header
            await ws.send_json({"type": "ack", "chunk": idx})
        if session.should_ack():
            await ws.send_json({"type": "ack", "seq": session.last_seq})
        progress.publish(session.id, session.stats())       # live status in the GUI
```

Because events arrive live, the GUI shows the session growing while you practice, and the engine can start cheap stages (normalizing, transcribing finished audio chunks) before the session ends.

### Site adapters

Each platform gets one adapter module behind a common interface, so a site redesign touches one file:

```ts
interface SiteAdapter {
  matches(url: URL): boolean;
  readProblem(): Problem | null;
  editor(): EditorHandle;              // getValue, onChange
  onRun(cb), onSubmit(cb);
  readResult(): RunResult | null;
  version: string;
}
```

Adapters are selector-driven with fallbacks, report their version into the manifest, and degrade gracefully: if result scraping fails, the session still records `run` events and the manifest marks `run_events` accordingly.

### Permissions

`tabCapture`, `offscreen`, `storage`, `scripting`, and host permissions only for supported platforms. No `<all_urls>`, and nothing is captured outside an active session.

## Component 2: Python engine + Flutter GUI (prepare)

The engine turns a raw bundle into a clean, segmented timeline with deterministic facts (timings, metrics, test results), so the AI only has to interpret, never measure. The Flutter desktop app is the control surface and the review experience.

### Engine pipeline

Runs as a local FastAPI service, launched by the GUI as a sidecar. Each stage reads and writes files in `derived/`, so any stage can be re-run alone.

1. **Ingest:** accept the live WebSocket stream or an imported zip; validate schema version; detect sequence gaps; join media chunks.
2. **Normalize:** sort by `t`, dedupe snapshots, derive `code_diff` events from consecutive snapshots (line-level with `difflib`), merge keystroke bursts.
3. **Transcribe:** faster-whisper on the audio with word timestamps, shifted by the manifest's audio offset; emit `speech` events. Tag cue phrases ("wait", "why is", "let me think") and pauses over 10 s. Spoken cues such as "I'm stuck" or "oh, I see" become \`marker\` events, the primary hands-free way to flag a moment.
4. **Derive signals:** `idle` gaps (no code change, no speech) over 45 s; churn windows (deleted lines / added lines over a sliding 2-minute window); run-fail streaks; focus-away spans.
5. **Segment phases:** rule-based first pass labels *read → clarify/plan → code → debug → test → submit*. First code edit ends planning; first failed run starts debugging; accepted submit ends the session. The AI refines boundaries later.
6. **Evaluate (sandbox):** run the final snapshot against the scraped examples, and user-supplied tests in a per-language runner (a container image per language with time and memory limits). Languages without a runner skip this step and rely on the platform's own verdicts. Record pass/fail per case and runtime.
7. **Metrics:** total time, time per phase, time to first run, time to first passing run, runs before accept, churn, longest idle, talk ratio (speech time / session time).
8. **Build AI context:** compress the timeline into the text form Component 3 consumes (below), plus a short list of keyframe candidates from the video at moments worth seeing.

### Output: `derived/timeline.json`

A list of phase segments, each with its events, metrics and evidence IDs, so every later claim can point back to a specific event:

```json
{"phase": "debug", "start": 742.1, "end": 1008.4,
 "signals": {"runs": 4, "fails": 3, "churn": 0.62, "longest_idle": 71},
 "events": ["ev_311", "ev_312", ...]}
```

### Storage

SQLite holds sessions, problems, metrics and reports for history and trends; media and events stay in the bundle folder. Problems are keyed by platform + slug so repeat attempts at the same problem are linked. On ingest the engine flags likely repeats (same platform and slug, or a close match on normalized title and statement across sites) and the GUI asks you to confirm before they are linked.

### Engine API

| Endpoint | Purpose |
| --- | --- |
| `WS /ingest` | Live event and media stream from the extension |
| `POST /sessions/import` | Import a bundle zip |
| `POST /sessions/{id}/inputs` | Add final assessment, reference solution, extra tests |
| `POST /sessions/{id}/process` | Run the pipeline (optionally from a given stage) |
| `WS /sessions/{id}/progress` | Stage-by-stage progress for the GUI |
| `GET /sessions/{id}/timeline` | Prepared timeline and metrics |
| `POST /sessions/{id}/analyze` | Trigger Component 3 |
| `GET /sessions/{id}/report` | Final report |
| `GET /trends` | Cross-session aggregates |

### Flutter GUI (desktop)

Flutter desktop talks only to the engine API; it never touches media processing itself.

- **Home:** recent sessions, streaks, and the top recurring time-sink categories.
- **Pair / capture:** shows the extension pairing token and live session status while you practice.
- **Session prep:** problem statement (scraped, editable), add your final assessment, reference solution and extra tests, confirm or reject a suggested repeat, then Process.
- **Timeline review:** video player (`media_kit`) on top; a phase bar below with run results, idle gaps, markers and churn as tracks; code viewer that shows the snapshot at the playhead; transcript synced to playback. Clicking any event seeks the video. AI findings appear as highlighted spans you can step through, each jumping to the moment it refers to. You can add or correct markers here while watching the replay.
- **Report:** scores, strengths, weaknesses, time sinks as cards with timestamp links, correctness and complexity, next-practice suggestions.
- **Trends:** time-to-accept by difficulty, time-sink categories over time, repeat-problem comparisons.
- **Settings:** API key, engine port, sandbox limits, which adapters are enabled.

Packaging: the engine is built with PyInstaller and shipped inside the Flutter app bundle; it runs as a background service, started at login or from a tray icon, so the extension can record without the GUI open. The GUI connects to it when opened.

### Where controls live

A normal practice session never touches the desktop app: open the problem, click start, practice, click stop. The GUI is for one-time setup and for review.

| Task | Chrome extension | Python engine + Flutter GUI |
| --- | --- | --- |
| Start, stop, pause a session | Popup or side panel; auto-prompt "Start recording this problem?" on problem pages | Not needed |
| Choose mode (Practice, Mock interview, Assessment) | Per session | Default set in settings |
| Flag moments | Optional hotkeys, off by default | Add or correct markers during review |
| Pairing | Enter the token once | Shows and rotates the token |
| Settings (API key, port, thresholds, target times) | Fetched from the engine on `hello`; no local copy | Edited here |
| Review, repeat confirmation, self-assessment, trends | Not available | All here |

If the engine isn't running, the extension still records to its local buffer and exports a bundle zip for import later.

## Component 3: AI processing and feedback (analyze)

The AI layer interprets a prepared timeline; it never measures time or judges correctness on its own. Every finding must cite event IDs, and findings that don't resolve to real events are dropped.

### Inputs to the model

- Problem statement, constraints, examples.
- Capability manifest (so it knows what is exact).
- Deterministic facts: metrics, sandbox results, phase boundaries.
- The timeline rendered as compact text, one line per event, for example `[12:22 ev_311 run_result] Wrong Answer, input "1,2", expected [1,2], got ['1','2']`.
- Code snapshots at phase boundaries and before/after each failed run, not every snapshot.
- Optional: your final assessment, reference solution, target time, and notes and metrics from the most recent confirmed attempt at the same problem.
- Keyframes on request: the model can ask for frames at specific timestamps, answered by the engine from the stored video, when events don't explain a moment.

### Orchestration

1. **Segment pass (map):** one call per phase segment, run in parallel. Asks: what were you trying to do, what happened, what cost time and why, what went well. Returns structured `SegmentFinding`s with cited events.
2. **Code review pass:** one call on the final code plus sandbox results: correctness reasoning for failures, time and space complexity, whether the approach is optimal, code quality and edge-case handling, and edge cases or tests worth considering (suggested, never run), comparison with the reference solution if given.
3. **Synthesis pass (reduce):** takes the segment findings, code review, metrics and your self-assessment; merges duplicates; ranks time sinks by time lost; writes the final report and next-practice suggestions.
4. **Validation:** Pydantic-validate the output; check every cited event exists and its timestamp falls inside the claimed span; check time-lost figures don't exceed the span; drop or re-ask on failure.

### Report schema

```python
class TimeSink(BaseModel):
    start: float; end: float
    time_lost_s: float
    category: Literal["understanding", "input_parsing", "output_format",
                      "algorithm_choice", "implementation", "debugging",
                      "edge_cases", "syntax_api_recall", "communication"]
    what_happened: str
    suggestion: str
    evidence: list[str]          # event ids

class Report(BaseModel):
    summary: str
    metrics: Metrics             # copied from engine, not generated
    correctness: Correctness     # sandbox verdicts + AI explanation
    complexity: Complexity       # time, space, optimal?, better approach
    strengths: list[Finding]
    weaknesses: list[Finding]
    time_sinks: list[TimeSink]
    communication: Communication # thinking aloud, clarifying, testing out loud
    vs_self_assessment: str      # where your read differs from the evidence
    vs_previous_attempts: str | None  # confirmed repeats only: what improved, what recurred
    suggested_tests: list[str]   # edge cases to consider; not executed
    next_practice: list[str]
```

The fixed `category` list is what makes trends work: across sessions you can see that, say, output formatting cost time in most string problems.

### Prompting rules

- Facts come from the engine; the model is told not to restate or alter numbers it was given.
- Low-confidence events (if any) must be phrased as estimates.
- Feedback is phrased as an interviewer would give it: specific moment, consequence, concrete fix.
- Store every prompt and response in `report/` for debugging and for re-running with a newer model.

### Cost and model choice

A typical 30-minute session becomes a few hundred lines of timeline text, about 5 to 8 calls in total. Use a vision-capable model only if keyframes are attached. Cache per-segment results so re-running synthesis after you add a self-assessment is cheap.

## Build plan, risks, open questions

### Build plan

1. **Contract + replay harness:** event schema, manifest, bundle format, and a hand-made sample bundle. Everything below is tested against it.
2. **Extension v0 (LeetCode only):** code snapshots, run/submit + results, problem scrape, mic audio; offline bundle export. No video, no live transport yet.
3. **Engine v0 (CLI):** ingest zip, normalize, transcribe, derive signals, rule-based phases, metrics (correctness from platform verdicts; no local sandbox yet).
4. **AI v0:** single synthesis call on the prepared timeline with the full report schema and evidence validation. Use it on real sessions before adding the map pass.
5. **Engine API + Flutter v0:** import, process, report view with timestamp links.
6. **Live transport + video:** WebSocket ingest, tab video, synced playback in the timeline view.
7. **AI v1:** segment map pass, code review pass, caching.
8. **Trends + second adapter (HackerRank):** cross-session dashboard, adapter interface proven on a second site.

### Potential next steps: local sandbox

Platform verdicts stay the primary correctness signal, since the platform runs hidden tests that can't be replicated locally. A local sandbox is an optional later phase that only runs what you trigger.

1. **Python runner with a LeetCode-style harness:** wraps the `class Solution` signature, builds helper types (`ListNode`, `TreeNode`), calls your method, and compares outputs, inside a container with time and memory limits.
2. **Your own tests:** run the tests you add in session prep, including when you stopped before submitting.
3. **Opt-in suggested tests:** pick from the AI's suggested edge cases in the GUI and run them; nothing generated runs automatically.
4. **Time to first correct solution:** replay intermediate code snapshots through the runner to find when the code first became correct, and add it as a metric alongside time to accept.
5. **Performance at scale:** large generated inputs to expose solutions that pass small examples but are too slow.
6. **Repeat comparison:** run the same tests against the most recent attempt's code for a direct comparison.
7. **More languages:** add a runner and harness per language as you start practicing in it.

### Potential next steps: live feedback while coding

The WebSocket already runs both ways, so the engine can push nudges back to the extension during a session. The hard part is deciding when to speak and how much to say, so live feedback ships in tiers.

| Tier | What it does | Latency | Effort | Recommendation |
| --- | --- | --- | --- | --- |
| 1. Rule-based reminders | Fires on signals the engine already derives: no code after 10 min, 90 s with no code change or speech, 2 min without talking, 3 failed runs in a row, submitting without running examples, time checkpoints against your target | Near zero | A few days | Ship with live transport |
| 2. AI hints on trigger | A Tier 1 signal or a spoken "stuck" cue (or the optional hotkey) sends the last few minutes of timeline plus current code to a fast model | 2–5 s | 1–2 weeks after the pipeline exists | Add next, starting in Mock interview mode |
| 3. Continuous AI copilot | Constant analysis of everything you do | Varies | High | Not recommended: costly, noisy, and unlike a real interview |

**Tier 2 behavior**

- **Hint ladder:** a nudge first, then a direction, then something specific, only if you ask again.
- **Hint budget:** a cap per session so the tool doesn't become a crutch.
- **Interviewer style:** the AI asks questions an interviewer would ("What's the complexity of that loop?") rather than giving answers.
- **Transcript lag:** Whisper on 10-second chunks lags about 10–20 s, which is fine for hints; "not talking" detection uses cheap voice-activity detection per chunk instead.

**Design changes**

- **Protocol:** engine → extension `nudge {id, level, text, evidence}`; extension → engine `nudge_feedback {id, helpful | dismissed}`.
- **UI:** shown in Chrome's side panel rather than overlays injected into the platform's page, which is sturdier against site changes and easier to ignore.
- **Session modes** recorded in the manifest: Practice (hints allowed), Mock interview (interviewer-style questions only), Assessment (no live feedback).
- **Hints as events:** each shown hint is a `hint_shown` event, so the report separates assisted from unassisted time.
- **Tuning:** dismissed nudges feed back into trigger thresholds.

### Potential next steps: recognizing the best approach

Work out what each problem is really asking for and which approaches are optimal. Then compare that with the approach the user took and when they found it, so the feedback can say things like:

- "The constraint n ≤ 10⁵ ruled out the O(n²) scan you started with."
- "'Longest substring without…' is a sliding-window cue."
- "You switched to the right approach at 9:40, after two Time Limit Exceeded results."

Nothing in capture changes: the statement, examples and constraints are already in `problem_loaded`.

**How it works**

1. **Complexity budget (engine, deterministic).** From the scraped constraints, the engine derives the largest input size and a time budget:

   | Largest input n | Budget |
   | --- | --- |
   | ≤ 10 | O(n!) |
   | ≤ 20 | O(2ⁿ) |
   | ≤ 500 | O(n³) |
   | ≤ 5·10³ | O(n²) |
   | ≤ 10⁶ | O(n log n) |
   | larger | O(log n) |

   A stated follow-up overrides the budget. For example, Two Sum's "less than O(n²)" overrides the O(n²) its 10⁴ limit would allow. This number is computed by the engine, like every other number, and stored in `derived/problem_profile.json`.
2. **Problem analysis (AI, once per problem).** It's cached by platform + slug and reused for repeat attempts. The input is the statement, examples, constraints and budget. The output is an `ApproachAnalysis`:
   - what is asked, in one sentence
   - **recognition cues**, quoted from the statement (e.g. "contiguous subarray", "sorted array", "k-th largest")
   - candidate approaches from a fixed taxonomy, each with expected time and space and a confidence
   - the recommended approach
   - common traps

   Validation drops any cue whose quote isn't a substring of the statement. This is the same rule as event citations.
3. **Approach used (AI code review pass).** It identifies the approach in the final code, and in snapshots at phase boundaries, citing snapshot and speech event IDs.
4. **Timing (engine).** The engine computes "time to the right approach" and "time on the wrong approach" from the cited events' timestamps. The AI names the moment and the engine measures it.
5. **Report (schema minor bump when built).** It gets `approach {asked, cues[], expected[], used, matched, switched_at, time_to_right_approach_s, evidence[]}`. Time lost is still filed under the existing `algorithm_choice` time-sink category.

**Taxonomy.** The list is fixed, so trends work, just as for time-sink categories:

- **Lookup and scanning:** hash map / counting, two pointers, sliding window, prefix sums, binary search (on an index or on the answer), sorting + greedy.
- **Stacks, queues and heaps:** stack / monotonic stack, deque / monotonic queue, heap.
- **Lists, trees and graphs:** linked-list techniques, tree DFS/BFS, graph BFS/DFS, topological sort, union-find, shortest paths.
- **Search and optimization:** dynamic programming (1D, 2D, knapsack, interval, bitmask), backtracking, divide and conquer.
- **Other:** trie, bit manipulation, math, intervals / sweep line, simulation / parsing, data-structure design.

**Rules**

- **More than one optimal answer.** "Matched" means the user's approach meets the budget and the platform accepted it. An equally optimal alternative isn't penalized: for Two Sum, a hash map and sort + two pointers both qualify.
- **Correctness.** It still comes from platform verdicts only. Complexity claims about the user's code are AI interpretations, labeled as such, and low-confidence ones are phrased as estimates.
- **Trends.** Track recognition time per pattern ("you're slow to spot monotonic-stack problems"). `next_practice` picks problems from weak patterns.
- **Live feedback (Tier 2).** Mock-interview hints can point at a cue ("What do the constraints allow?") without naming the approach.

**Placement and evaluation**

- **Placement.** The budget is cheap and could ship with the engine metrics (step 3 or later). The AI parts need the code review pass, so they belong after AI v1 (step 7).
- **Evaluation.** A hand-labelled set of about 100 problems covering the taxonomy measures classification accuracy. Tests use recorded responses, as for the rest of the AI layer.
- **Storage.** A `problems` table in SQLite caches the analysis (platform, slug, profile, model, created_at).

**Open questions**

- **Topic tags.** Should LeetCode's "Topics" tags be scraped as an extra signal? That would add a `ProblemLoadedData.topics` field (contract minor bump), and tags must stay hidden from live hints so they don't spoil the problem.
- **Trends with several optimal approaches.** How should trends count a problem that has more than one optimal approach?

### Risks

| Risk | Mitigation |
| --- | --- |
| Site redesign breaks scraping | One adapter per site, versioned; manifest records what failed; session still usable |
| Editor internals not reachable | Fall back to reading the editor's DOM text, marked lower confidence |
| Platform terms of service | Only read pages you are already viewing for your own practice; no automated submits or bulk scraping |
| Audio/event clock drift | Single clock in the service worker; media offsets in the manifest; spoken + hotkey sync marker at start |
| AI invents feedback | Engine owns all numbers; every finding cites events; validation drops uncited claims |
| Sandbox runs untrusted code | Subprocess limits now, container isolation before any code from outside your own sessions |
| MV3 worker suspension mid-session | Offscreen document holds the long-lived recorder; worker state persisted to storage each batch |

### Decisions

- **Video:** recorded and kept, but not sent to the AI by default. The AI can request frames at specific timestamps when events don't explain a moment, and the GUI uses the recording to play back each highlighted finding at its exact moment.
- **Languages:** support every language the platform offers. Capture and ingest are language-agnostic, since code is stored as text and verdicts come from the platform. Only the local sandbox is per-language: runners are added one at a time, and until a language has one, correctness relies on platform verdicts plus AI code review.
- **Repeat problems:** the engine flags likely repeats, you confirm in the GUI, and confirmed repeats feed the most recent attempt's notes and metrics into the feedback.

* **Previous attempts:** only the most recent confirmed attempt is used, to keep feedback unambiguous.
* **Test cases:** no generated hidden tests are run. The AI suggests edge cases and tests for you to consider, listed in the report.

**Contract v1 (build-plan step 1).** Full rationale and the options weighed are in [`decisions/001-contract-v1.md`](decisions/001-contract-v1.md).

- **`seq`:** required on extension events, forbidden on others. Extension event IDs are `ev_<seq>`. `events.jsonl` holds captured events only; engine and Whisper events (speech, spoken markers, diffs, idle) go in `derived/*.jsonl`. (D1)
- **Typed payloads:** `Event` is a tagged union on `kind`, and each `data` payload is typed and strict. `run_result` and `submit_result` cite their `run_id` / `submit_id` and carry a normalized `verdict`. `problem_loaded` carries `slug`. (D2)
- **Per-stream chunks:** chunk indexes count separately per stream. `ack.chunk` is `{stream, index}`. `welcome.last_chunk` and `end.final_chunk` are maps keyed by stream. `welcome` reports the highest value with nothing missing below it. (D3)
- **Media header:** 16 bytes, big-endian: `version u8 | stream u8 | reserved u16 | chunk_index u32 | start_ms u64`. `start_ms` is on the session clock. (D4)
- **Media files:** chunks are stored raw as `media/<stream>/<index>.webm`, with a `chunks.jsonl` index. Joining into `audio.webm` is an ingest job. For a repeated seq with different content, the first copy wins and the rejected copy is logged to `events.conflicts.jsonl`. (D5)
- **Completeness:** the `end` message is stored as `manifest.end`. "Complete" is computed when the bundle is read (`end` present, no seq or chunk gaps), not stored. (D6)
- **Manifest fields:** the manifest has `clock_origin.wall_time_utc` and `media.{audio,video}.{mime, offset_s}`. Small `user_inputs` go inline; files go in `inputs/`. `session_id` is restricted to `[A-Za-z0-9_-]`. Session `mode` is in `Capabilities`. (D7)
- **Event framing:** event frames are nested (`{"type":"event","event":{…}}`). The pairing token goes only in the URL. Origin or token failures close the socket with code 4403. (D8)
- **Versioning:** `schema_version` is `"MAJOR.MINOR"`, starting at `"1.0"`. The engine accepts the same major version. (D9)
- **Generators:** Pydantic generates the JSON Schema, json-schema-to-typescript the TS types, and quicktype the Dart types. Dart flattens the unions, so the GUI reads events but must not send them back as they are; revisit in step 5. (D10)
- **Report sub-models:** `Metrics`, `Correctness`, `Complexity`, `Finding` and `Communication` are now defined. `Report` gets `schema_version` and `session_id`. (D11)

**Extension v0 (build-plan step 2).** Full rationale is in [`decisions/002-extension-v0.md`](decisions/002-extension-v0.md). There is no contract change.

- **Clock:** every context stamps captures with `Date.now()`, and the service worker converts them to `t` from its stored `t0`. A capture more than 1 s before `t0` gets confidence 0 (E16 supersedes E1, after a sleep-lagged tab stamped everything at `t = 0`). Seq is assigned in the same IndexedDB transaction that stores the event. Seq is arrival order, not time order, so consumers sort by `t`. (E1, E2)
- **Snapshots:** taken on a 500 ms debounce, every 15 s **only if the code changed**, and always at start and on run/submit. (E3)
- **Activation:** the content script is inert until a session records in its tab. The Monaco probe is injected only during a session. Only the recording tab is captured. (E4)
- **Keystrokes and focus:** keystroke bursts end after 1 s of quiet or 30 s of typing, and `t` is the burst start. A tab switch is recorded once, as `focus_change` target `tab`. (E5)
- **Results:** the result panel is polled every 250 ms until settled, and timed from when the verdict first appeared. A failed scrape gives verdict `unknown`, confidence 0 (interim; see Open questions). (E6)
- **Ending a session:** a session ends on Stop, on closing the tab, or when the tab leaves the problem's slug. Tabbing out, moving between a problem's sub-pages, reloading, and accepted submits don't end it. (E7)
- **Permissions:** `offscreen`, `storage`, `scripting`, plus host `https://leetcode.com/*`. There's no `tabCapture` or `127.0.0.1` until step 6, and no `downloads`. Microphone permission is granted once on `setup.html`. (E8)
- **Extra captures:** keystrokes, paste, undo and focus are captured in v0, although step 2 doesn't list them. (E9)
- **Adapter:** the `SiteAdapter` interface is refined (`editorSelector`, separate run and submit readers, `problemKey`, `readLanguage`). Submit failure panels are not yet verified live. (E10)
- **Export:** the zip contains a single `session_<id>/` folder. A cross-language test checks that the TS exporter's output equals the fixture when read by `ic_schema`. (E11)
- **Submit fixes:** failed submissions are detected by their `<h3>` heading. Submit panels are read only once their stats render. A newer run or submit supersedes an unsettled earlier one, recorded as `unknown`. Adapter version is 0.2.0. (E13)
- **Session language:** the session language locks at the first edit, run or submit. Snapshots before the lock always carry `language`. The `CodeSnapshotData.language` description is clarified, with no version bump. (E14)
- **Ignored clicks and runtime errors:** clicks on a pending Run/Submit button (styled `cursor-not-allowed`) are ignored by LeetCode, so they aren't recorded as runs. Runtime Error results read the "Last Executed Input" section. Adapter version is 0.3.0. (E15)

### Open questions

- **Pause.** The popup design lists start, stop and pause, but the contract has no way to record a pause. Options: add `session_pause` / `session_resume` event kinds (schema minor bump), or treat pause as stop plus a new linked session. Deferred from step 2, where v0 has start and stop only.
- **Failed result scrape.** How should a run or submit whose result panel never settles be recorded? v0 (step 2) emits `run_result` / `submit_result` with `verdict: "unknown"` and `confidence: 0.0`, and keeps `Capabilities.run_events` meaning "run/submit clicks are hooked". The alternative is an explicit capability (e.g. `Capabilities.run_results`). Revisit when the engine (step 3) starts consuming results, and add a fixture for this bug class then.

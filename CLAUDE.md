# Interview Coach

Interview Coach reviews recorded LeetCode-style practice sessions and returns timed, evidence-backed feedback: where time went, what went well, what cost time, and whether the solution was correct and optimal.

The full design lives in `docs/design.md`. Read it before starting any non-trivial task, and follow it. If a task requires deviating from it, stop and say so instead of improvising.

## Architecture

Three components joined by one contract, the **session bundle**:

1. **`extension/`: Chrome extension (capture).** MV3, TypeScript. Captures exact events in the browser (code snapshots, run/submit results, problem statement, editor-scoped keystroke categories, audio, optional tab video) and streams them live to the engine. Does no analysis.
2. **`engine/`: Python engine (prepare).** FastAPI service on `127.0.0.1`, running as a background service. Ingests the stream, transcribes audio, builds and segments the timeline, computes metrics, and serves the GUI.
3. **`engine/ai/`: AI layer (analyze).** Turns a prepared timeline into a structured, evidence-cited report.
4. **`gui/`: Flutter desktop app.** Setup and review only. Talks to the engine API; never processes media itself.

```
interview-coach/
  schema/      # Pydantic models: the source of truth for the contract
  extension/   # MV3 extension, TypeScript
  engine/      # FastAPI, ingest, pipeline, ai/
  gui/         # Flutter desktop
  fixtures/    # sample session bundles for replay tests
  docs/design.md
```

## Invariants (never break these)

- **The contract is the source of truth.** Event, Capabilities, and bundle models live in `schema/` as Pydantic models. JSON Schema is generated from them, and TypeScript and Dart types are generated from that. Never hand-edit generated types; change the Pydantic model and regenerate.
- **Schema changes are versioned.** Bump `schema_version` and update `fixtures/` in the same change.
- **One clock.** All times are float seconds from `session_start`, taken from the extension's service worker. Media streams store their offset from that origin in the manifest.
- **The engine owns every number.** Timings, metrics, and verdicts are computed deterministically in the engine. The AI layer interprets; it never measures time or decides correctness.
- **Every AI finding cites event IDs.** Validation drops any finding whose evidence doesn't resolve to real events inside its claimed time span.
- **Platform verdicts are the primary correctness signal.** No local sandbox in v1 (it is a later, optional phase in the design).
- **Capture is language-agnostic.** Code is stored as text; nothing in capture or ingest may depend on the solution's language.
- **Video is not sent to the AI by default.** The AI may request frames at specific timestamps; otherwise video is for playback in the GUI.
- **Repeat problems use the most recent confirmed attempt only.**
- **No generated hidden tests are executed.** The AI may only suggest edge cases for the user to consider.

## Security rules

- The engine binds to `127.0.0.1` only, never `0.0.0.0`.
- `WS /ingest` must check `Origin == chrome-extension://<extension id>` and a valid pairing token before accepting. Browsers don't apply CORS to WebSockets, so this check is the only thing keeping other websites out.
- Keystrokes are captured only inside the platform's editor, only during an active session, and stored as categories (insert, delete, newline, navigation, shortcut), never raw characters.
- Extension host permissions cover supported platforms and `http://127.0.0.1/*` only. Never request `<all_urls>`.
- Never log or commit API keys or pairing tokens.

## Component conventions

### extension/
- MV3, TypeScript, strict mode.
- The **offscreen document** owns the WebSocket and `MediaRecorder`; the service worker can be suspended, so it only stamps time and sequence numbers and relays.
- Every event and media chunk is written to IndexedDB before sending and pruned only on ack. Reconnect with backoff and resume via `hello.resume_from`.
- One **site adapter** per platform behind the `SiteAdapter` interface. Platform-specific selectors live only in that adapter. Adapters report their version into the manifest and degrade gracefully when scraping fails.
- UI lives in the popup and side panel, never as overlays injected into the platform page.

### engine/
- Python 3.12, FastAPI, Pydantic v2, SQLite. Format with ruff; type-check with mypy (strict on `schema/` and `engine/ai/`).
- Pipeline stages read and write files under the session's `derived/` folder and must be re-runnable on their own.
- Ingest dedupes by `seq`, so replay from the extension is always safe.
- Transcription: faster-whisper with word timestamps. Spoken cues ("I'm stuck", "oh, I see") become `marker` events.

### engine/ai/
- Structured outputs validated with Pydantic against the report schema in `docs/design.md`.
- Store every prompt and response under the session's `report/` folder.
- Low-confidence events must be phrased as estimates.

### gui/
- Flutter desktop (macOS, Windows, Linux). Talks only to the engine API (REST plus progress WebSocket).
- Video playback with `media_kit`. Clicking any event or finding seeks the video.

## Testing

- Every pipeline stage is tested by replaying bundles from `fixtures/`, without a browser.
- Add a fixture for each new bug class (gaps in `seq`, missing audio, failed result scrape, repeat problem).
- AI-layer tests use recorded responses; never call the live API in the default test run.
- Run the relevant tests before reporting a task as done, and say which ones you ran.

## Commands

Fill these in as the project takes shape:

```
# schema
make schema            # regenerate JSON Schema, TS and Dart types (DART=... if not on PATH)
make test              # contract tests: models, protocol, bundle I/O, fixtures, replay
make check             # ruff + mypy --strict + tests + tsc/dart analyze on generated types
make fixtures-audio    # rebuild silent audio chunks in fixtures/two_sum_basic (needs ffmpeg)
# engine
cd engine && uv run pytest                       # recorded transcripts only; never a live model
make engine-transcribe-deps                      # faster-whisper extra (model downloads on first use)
cd engine && IC_WHISPER=1 uv run pytest -m whisper   # opt-in: real small.en on the fixture audio
cd engine && uv run interview-coach run SESSION.zip  # import + process (Engine v0 CLI)
cd engine && uv run interview-coach show SESSION
cd engine && uv run uvicorn engine.app:app --host 127.0.0.1 --port 8765   # step 5 (API)
# extension
cd extension && npm run build    # load extension/dist as unpacked in Chrome
cd extension && npm test         # vitest; also writes test-output/ zip read by schema/tests/test_extension_bundle.py
make test                        # extension tests, then pytest (order matters)
# gui
cd gui && flutter run -d macos
```

## How to work in this repo

- Work one build-plan step at a time (see "Build plan" in `docs/design.md`). Don't start the next step unless asked.
- Before writing code for a step, list the files you will touch and any design questions. If a question changes the contract, ask first.
- Keep changes scoped: no drive-by refactors outside the step.
- When a decision is made that the design doc doesn't cover, add it to the "Decisions" section of `docs/design.md` in the same change.

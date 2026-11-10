# 003: Engine v0, CLI pipeline (build-plan step 3)

Oct 19, 2026 · Status: accepted · `schema_version` 1.0 (no contract change)

This records decisions made while building `engine/` (ingest, normalize, transcribe, signals, phases, metrics and timeline) where `docs/design.md` was silent or ambiguous. `docs/design.md` → Decisions links here. The user approved the step-3 plan's defaults on 2026-10-19.

**Out of scope:**

- the sandbox
- the API and live WebSocket ingest (steps 5–6)
- SQLite and repeat detection (deferred to step 5)
- building the AI context (step 4)

---

## C1. Derived-file models stay in the engine for v0

`IngestReport`, `NormalizeReport`, `Signals`, `Phases`, `SessionFacts`, `Timeline` and `PipelineStatus` live in `engine/models.py`. `metrics.json` uses the contract's `ic_schema.report.Metrics` unchanged.

The engine models are promoted to `schema/`, as a minor contract bump, in step 5, when the GUI first reads them over the API. They're likely to change during AI v0 (step 4) first.

The rejected alternative was adding them to `schema/` now with a bump to 1.1. That means regenerating everything, updating fixture manifests, and the extension starts writing 1.1, all for models nobody outside the engine reads yet.

## C2. No schema change for the step-3 carry-over items

- `Bundle.timeline()` is a reader helper in `ic_schema`, not a model. It's described below under "Carry-over from step 2".
- The solution language goes in `SessionFacts`, not `Report.Metrics`.
- Pauses, churn windows, fail streaks, typing spans and focus-away spans are spans in `signals.json`, not new event kinds.
- `schema/src/ic_schema/py.typed` was added so mypy checks the engine against the contract's real types. It's packaging metadata, not a schema change.

## E1. Events are never deleted

- **"Dedupe snapshots" (design).** Snapshots identical to the previous one, and taken by the timer (debounce/periodic), are listed in `normalize.json` as redundant and left out of timeline segments. They stay in the bundle, so every evidence ID still resolves. Forced snapshots (initial/run/submit) are never redundant, because they tie exact code to a run.
- **"Merge keystroke bursts" (design).** Bursts less than 5 s apart become typing spans in `signals.json`. New keystroke events would double-count keys.
- **`code_diff` events.** One per pair of consecutive distinct snapshots, in timeline order (`df_<n>`, source `engine`, line-level with `difflib`), written to `derived/diffs.jsonl`.

## E2. Phase rules

A state machine over `Bundle.timeline()`. Phases can recur, because real sessions loop (a failed submit returns to debug).

1. `read` starts at 0.
2. `plan` starts at the first *substantive* speech segment (3+ content words) that isn't reading the problem aloud.
   - "Reading aloud" means at least 50% content-word overlap with the title, statement, examples and constraints. For example, "Given an array of integers…" is reading, and "Brute force is two nested loops…" is planning.
   - Without a statement (see design → Open questions), `plan` starts at the first substantive speech segment.
   - Without speech, there's no `plan` phase.
3. `code` starts at the first edit: a keystroke burst that inserts or deletes, a paste, or a run/submit click.
   - A code change counts only when the session didn't capture keystrokes.
   - A code change from a **language switch** never counts: the platform swaps in a new template. In a real session, a C++ → Java switch at 7.3 s had started `code` 4 s before the first keystroke.
4. Transitions:
   - A failed run or submit result (any known verdict other than accepted) moves to `debug`.
   - An accepted run moves `code`/`debug` to `test`.
   - A submit click moves to `submit`.
   - An accepted submit closes the timeline. Time after it is the **tail**, excluded from time per phase (the design says "accepted submit ends the session").
   - `unknown` results (failed scrapes, 002 E6) change nothing.
5. **Segment contents.** A segment lists every event in `[start, end)`, except redundant snapshots, and the last segment includes its end. The failure that opens a `debug` segment is therefore inside it, and is counted in its `fails`.

## E3. What counts as idle

Idle is a gap of more than 45 s with no activity. Activity is any of:

- a code change (`code_diff`)
- speech
- a paste or undo
- a run/submit click
- a result, including an `unknown` one

That widens the design's "no code change, no speech": waiting on the judge isn't idle.

- **Before the first activity:** that gap is reading, not idle.
- **After the last activity:** the gap to the session end counts.
- **Longest idle:** `Metrics.longest_idle_s` is the longest gap of any length, even under 45 s. Idle spans are also written as `idle` events (`id_<n>`) to `derived/idle.jsonl`.

## E4. Focus-away and other signals

| Signal | Rule |
| --- | --- |
| Focus away | Only `tab` and `window` changes count. `editor` focus changes are noise: a real session had 40, mostly from clicking Run. |
| Churn | Deleted ÷ max(added, 1) lines. Windows are 2 minutes long, stepping by 30 s. A window is flagged high when it deletes at least 5 lines with churn ≥ 0.5. `Metrics.churn` is the whole session's ratio. |
| Fail streaks | 2 or more consecutive failed results. `unknown` neither counts nor breaks a streak. |
| Pauses | More than 10 s between speech segments. |

## E5. Transcription

- **Packaging.** faster-whisper is an optional extra (`transcribe`), so the default test environment stays light. The default model is `small.en`, downloaded on first use (483 MB) into the Hugging Face cache.
- **Pinned decoder.** `av>=15,<19` is pinned in the extra. PyAV 19 removed `av.open(metadata_errors=…)`, which faster-whisper 1.2.1 passes, so decoding failed. Versions 15–18 were checked.
- **Model settings.** Word timestamps on. The voice-activity filter is on, so silence produces no invented text: the fixture's 176 s of silence gives 0 segments with the real model. `language="en"`, and `condition_on_previous_text=False`.
- **Decoding.** Audio is decoded from the joined stream by PyAV, never from the WebM header, which MediaRecorder leaves without a duration (002, carry-over 5).
- **Clock.** Times are shifted by `media.audio.offset_s` and clamped to the session.
- **Confidence.** `confidence` = exp(average log-probability), and `t_uncertainty` = 0.2 s.
- **Markers.** Marker phrases come from a deliberately small, conservative list in `engine/cues.py` (stuck / idea / done), because a false marker is worse than a missed one. Matching is on whole words: "I'm not stuck" isn't a marker. A marker's time is the start of its first word, not the segment's start.
- **No transcriber.** Without a transcriber (`--no-transcribe`, or the extra not installed), an existing transcript is **kept**, not wiped. Without audio, a stale transcript is removed. `Metrics.talk_ratio` is null, not 0, unless there's audio *and* a transcript.
- **Tests.** Tests use `RecordedTranscriber`, built from the fixture transcript. The real model only runs in the opt-in test (`IC_WHISPER=1 pytest -m whisper`).

## E6. Files, layout and CLI

- **`timeline.json`** wraps the design's list of phase segments as `{session_id, facts, metrics, segments, tail}`, so it's self-contained.
- **Joined audio.** It's written to **`derived/audio.webm`**. The design's bundle layout puts `audio.webm` at the bundle root, but CLAUDE.md says stages write only under `derived/`, and the joined file is derived from `media/`.
- **Event files.** `derived/*.jsonl` are event files, which `Bundle.timeline()` merges. `derived/*.json` are structured results. The signals stage leaves its own `idle.jsonl` out of its input, so re-runs are stable.
- **Pipeline status.** `derived/pipeline.json` records each stage's status (`ok` / `skipped` / `failed`), time taken and message. A stage whose inputs are missing fails with "run the stage that writes it first".
- **Package layout.** `engine/src/engine/` (with `engine/ai/` arriving in step 4). CLAUDE.md's run command, `uv run uvicorn engine.app:app` from `engine/`, needs an importable `engine` package.
- **CLI.** The `interview-coach` command has `import`, `process` (`--from`/`--only`/`--skip`/`--no-transcribe`/`--model`), `run` and `show`.
- **Data directory.** `~/Library/Application Support/InterviewCoach` (platform equivalents elsewhere), overridable with `IC_DATA_DIR` or `--data-dir`.
- **Import safety.** One top-level `session_<id>/` folder matching the manifest. Rejected: absolute paths, `..` paths and symlinks. Limits: 20,000 entries, 4 GiB expanded, and a 200:1 compression ratio for entries over 1 MiB. Extraction goes to a staging folder, then renames, so a failed import leaves nothing behind.

## E7. Ingest warnings

`ingest.json` lists warnings, and `interview-coach show` prints them with any non-ok stage messages. They cover:

- no `end` record
- missing seqs
- rejected conflicts
- a torn last line
- audio claimed but missing
- audio chunk gaps
- **timestamps collapsed at `t = 0`**: 3 or more captured events at exactly 0, or any with confidence 0. This is the pre-E16 clock bug (002), which older bundles recorded without confidence 0.

## E8. Results on real sessions (manual run, 2026-10-19)

These are the four recordings in `extension/test-output/manual/` (gitignored, never fixtures), run with `small.en` on CPU in a scratch data directory:

| Session | Transcription | Result |
| --- | --- | --- |
| Valid Parentheses, 15:54 | 49 s for 16 min of audio; 44 segments, talk 77% | read 4 s → plan 7 s → code 9:49 → debug 4:25 → test 8 s → submit 56 s, then the tail. 12 runs (11 failed), first pass at 14:26. Plausible. Its submit facts carry the pre-fix capture bugs (002 E13). |
| Longest Palindromic Substring, 20:11 | 37 s; 27 segments | **Flagged by E7:** 123 events at `t = 0`. It was recorded before the clock fix (002 E16), so its phases (code 18 s, debug 19:53) aren't meaningful. My step-2 check of this zip missed it, because it only looked at result timing. |
| Longest Palindromic Substring, 0:33 | no speech | Flagged by E7: all events at `t = 0`, the original clock-bug session. |
| Longest Palindromic Substring, 0:17 | no speech | read → code → test → submit, then the tail. Correct. No statement (design → Open questions), so the difficulty is unknown. |

**Known limits of the v0 rules,** for the AI to refine (design step 5):

- A single trivial keystroke (one newline) starts `code`, even if the user is still planning aloud.
- With 77% talk time, the read/plan split rests on the first few segments only.
- No marker phrases were spoken in these sessions, so marker detection has only been exercised on the fixture.

## Carry-over from step 2 (all done)

1. **Ordering helper.** `Bundle.timeline()` orders by `t`, then captured before derived, then `seq`, then `id`, and rejects duplicate IDs. Every engine stage uses it.
2. **Fixture assertion.** `schema/tests/test_fixtures.py` no longer asserts time order by seq. It checks what the contract guarantees: unique contiguous seqs, `t` within the session, and each result after its click.
3. **New fixtures.** `fixtures/two_sum_live_order` (arrival-ordered seq, 6 inversions) and `fixtures/two_sum_failed_scrape` (bug class "failed result scrape"), generated by `fixtures/tools/make_variant_fixtures.py`.
4. **001 D1:** consumers order by `t`, never by seq.
5. **WebM duration:** audio is decoded from the stream, not the header (E5).
6. **Solution language:** `SessionFacts.solution_language` comes from the final snapshot, and `session_language` from `Capabilities.language`.

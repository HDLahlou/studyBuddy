# 001: Shared contract v1 (build-plan step 1)

Oct 19, 2026 · Status: accepted · `schema_version` 1.0

This record covers the contract decisions made in build-plan step 1, where `docs/design.md` was ambiguous or silent. For each one it gives the decision, the options weighed, and the reasons. `docs/design.md` → Decisions has a one-line summary of each, linking here.

Code: `schema/src/ic_schema/`. Fixtures: `fixtures/`.

---

## D1. `seq`, and where engine-produced events live

**Problem.** The protocol sends `event {seq, ...Event}`, but the design's `Event` has no `seq`. Kinds such as `speech`, `code_diff` and `idle` come from the engine or Whisper, so they have no capture sequence number.

**Decision.**

- `seq: int | None` (≥ 1). It's required when `source == "extension"` and forbidden otherwise.
- Extension event IDs are `ev_<seq>`. The validator enforces this, so IDs are unique without coordination.
- `events.jsonl` holds captured events only. Engine and Whisper events go in `derived/*.jsonl`. In the fixture, `derived/transcript.jsonl` holds `speech` and the spoken `marker`.
- Engine IDs use a short prefix per kind (`sp_`, `mk_`, `df_`, `id_`), so they never collide with `ev_`.

| Option | Pros | Cons |
| --- | --- | --- |
| **Captured-only `events.jsonl`; derived events in `derived/` (chosen)** | Gap detection is just "seqs 1..final are contiguous". `events.jsonl` stays a pure, append-only record of what the browser sent. Pipeline stages stay re-runnable because they never rewrite capture output. | Readers that want the full timeline must merge two sources. The engine's Normalize stage does that anyway. |
| Mixed file, with `seq` null for derived events | One file to read | Re-running a stage means rewriting or filtering an append-only file. Gap logic must skip some lines. Derived output becomes mixed with the evidence it was derived from. |
| Engine assigns its own seq range to derived events | Uniform envelope | Invents numbers that mean nothing for transport. Collides with replay and resume semantics. |

## D2. Typed `data` per kind (tagged union)

**Problem.** The design has `data: dict`. That's untyped, so the TS and Dart types would be `Record<string, unknown>`, and fixture mistakes would go unnoticed.

**Decision.**

- Each kind is its own model, with `kind: Literal[...]` and a typed `data` model.
- `Event` is a Pydantic tagged union, chosen by `kind`.
- Payload models use `extra="forbid"`.

| Option | Pros | Cons |
| --- | --- | --- |
| **Tagged union with typed payloads (chosen)** | Real types in TS (narrowing on `kind`) and Python. JSON Schema validation catches payload errors in fixtures and at ingest. | Dart flattens it (see D10). Adding a payload field is a contract change, which is intended. |
| `data: dict` with Python-only payload validation | Simplest generated types | No type safety in the extension, where most events are produced. Two sources of truth. |
| `data` as an untagged union | — | Ambiguous when parsing. No discriminator. |

**Payload details fixed here:**

- `problem_loaded` has `slug` and `url`. Repeat detection keys on platform + slug.
- `run_result` and `submit_result` have `run_id` and `submit_id` pointing at the click they answer, plus `verdict`, which is normalized (`accepted`, `wrong_answer`, `runtime_error`, `compile_error`, `time_limit_exceeded`, `memory_limit_exceeded`, `output_limit_exceeded`, `unknown`). `verdict_raw` keeps the platform's own text. For a run, `accepted` means all example cases passed.
- `keystroke` is one event per burst. `t` is the burst start. It has `duration_s`, and `counts` per category (insert, delete, newline, navigation, shortcut). There are never raw characters, and the schema forbids extra keys.
- `paste` stores `chars` and `lines` only. The text is visible in the next snapshot.
- `code_snapshot.reason` is one of `initial`, `debounce`, `periodic`, `run` or `submit`. `language` is set when it differs from `Capabilities.language`, and on every snapshot taken before the session language locks (clarified in 002 E14, still 1.0). If it's absent, use `Capabilities.language`.
- `speech` has `end` (on the session clock), optional `words` with word timestamps, and `cues`.
- `marker` has `label` (`stuck`, `idea`, `done`), `origin` (`hotkey`, `speech`, `review`) and optional `text`. A spoken marker has `source: "whisper"`. A hotkey marker comes from the extension. A review marker has `source: "user"`.
- `hint_shown` and `nudge` are left out, because live feedback is future work. Adding them later is a minor version bump.

## D3. Chunk numbering is per stream: acks, welcome, end

**Problem.** Audio and video each count chunks from 0, so one integer for `last_chunk`, `chunk` or `final_chunk` is ambiguous.

**Decision.**

- `ack {seq?, chunk?: {stream, index}}`.
- `welcome.last_chunk` and `end.final_chunk` are maps keyed by stream: `{"audio": 12, "video": 11}`.
- `welcome.last_seq` and `last_chunk` report the **highest value with nothing missing below it**. That's exactly where the extension should resume.
- `hello.resume_from` is the first seq the extension will (re)send, or null on a new session.

| Option | Pros | Cons |
| --- | --- | --- |
| **Maps keyed by stream (chosen)** | Explicit. One message covers both streams. | Slightly more structure than the design table shows |
| A global chunk index across streams | Keeps single integers | The extension has to coordinate two `MediaRecorder`s on one counter. Gaps become ambiguous. |
| Separate `ack_audio` and `ack_video` messages | — | More message types for no gain |

## D4. Media chunk binary header (16 bytes, big-endian)

| Offset | Size | Field | Meaning |
| --- | --- | --- | --- |
| 0 | 1 | `version` | Header layout version, currently 1 |
| 1 | 1 | `stream` | 0 = audio, 1 = video |
| 2 | 2 | `reserved` | Must be 0 |
| 4 | 4 | `chunk_index` | u32 per stream, from 0, contiguous |
| 8 | 8 | `start_ms` | u64, chunk start in ms from `session_start` |

`struct` format `>BBHIQ`. Pack and unpack are `MediaChunkHeader.pack()` and `unpack()`. TypeScript will mirror this with a `DataView` in step 6; it's not code-generated.

**Options weighed:**

- **Version byte or not.** A version byte costs one byte, and it lets the layout change without breaking old engines silently. Kept.
- **`start_ms` as u32 versus u64.** u32 covers about 49 days, which is plenty. u64 fills the 16 bytes with no odd padding and never overflows. Chose u64.
- **Little-endian versus big-endian.** Big-endian is network order. JS `DataView` handles either. Chose big-endian.
- **A JSON header instead.** A JSON header would mean a length prefix and parsing on the hot path. Rejected.

`start_ms` is on the session clock. So `manifest.media.<stream>.offset_s` = the first chunk's `start_ms` / 1000.

## D5. Bundle layout for media and conflicts

**Problem.** The design shows a single `audio.webm` "joined on ingest". The step asks for chunk files.

**Decision.**

- Chunks are stored as `media/<stream>/<index:06d>.<ext>`, holding the raw MediaRecorder bytes with no header.
- `media/<stream>/chunks.jsonl` records `{index, start_ms, bytes}` for each chunk.
- Joining into `audio.webm` is an engine ingest job (step 3), not part of bundle I/O.
- `StreamChunks.join()` concatenates the chunks in index order.

**Options weighed:**

- **Keep the header in each file.** That makes the files unplayable and duplicates the index.
- **Encode `start_ms` in the filename.** That's brittle.
- **Payload files plus an index file (chosen).** Each file is a valid byte slice, and the index can be appended crash-safely.

**Dedupe:**

- A repeated `seq` with identical content is dropped silently.
- A repeated `seq` with different content keeps the first copy. The rejected copy is appended to `events.conflicts.jsonl` for audit, so the first write wins and nothing is overwritten silently.
- Chunks follow the same rule.

**Crash safety:**

- A torn (unterminated) last line is ignored by the reader, and reported as `torn_tail`.
- The writer truncates a torn line when it resumes.
- Chunk files and the manifest are written atomically (write to a temp file, then rename).

## D6. Completeness and the `end` record

**Problem.** The engine "marks the session incomplete until `end` arrives and all sequences are contiguous", but the design doesn't say where that state is stored.

**Decision.**

- `Manifest.end: {final_seq, final_chunk} | null` is written when `end` arrives.
- `Bundle.complete` is computed when the bundle is read: `end` is present, seqs `1..final_seq` have no gaps, and each stream's chunks `0..final_chunk[stream]` have no gaps.
- Without `end`, gap detection runs up to the highest seq seen, because a trailing gap can't be known yet.

**Options weighed:**

- **A stored `complete: bool` flag.** It can go stale, so it was rejected.
- **A separate `ingest.json`.** It's one more file for one field.

Seqs start at 1, so `welcome.last_seq = 0` means "nothing received".

## D7. Manifest shapes the design leaves open

- **`clock_origin`** is `{wall_time_utc}`, used for display and history. The extension's `performance.now()` origin is omitted, because it means nothing outside the browser.
- **`media`** is `{audio?, video?}`. Each stream is `{mime, offset_s}`. `offset_s` is null until the first chunk arrives.
- **`user_inputs`** holds `self_assessment` and `target_time_s` inline. `reference_solution` and `tests` are paths under `inputs/`. Small inputs go inline and file-sized ones go in the folder the design already defines.
- **`session_id`** must match `^[A-Za-z0-9_-]{1,64}$`, because it becomes a folder name (`session_<id>`) and must not allow path traversal.
- **Session `mode`** lives in `Capabilities`, as requested. The design says "manifest", and `Capabilities` is part of the manifest, so both hold. `mode` describes the session rather than what capture could record. That's a slight semantic stretch, accepted so that `hello` carries it with no extra field.

## D8. Protocol message details

- **Event framing.** `{"type":"event","event":{...}}`, nested rather than flattened into `{type, seq, ...}` as the design table shows. `seq` already lives inside the event. Nesting keeps the tagged union intact in every generated language. A flattened shape would need a second union, a `type` + `kind` cross-product, for no gain.
- **Pairing token.** It's sent in the connection URL (`/ingest?token=…`), as in the design's handler sketch. It's never part of a message, so it can't end up in stored frames or logs of message bodies.
- **Origin or token failures.** The engine closes the socket with code 4403 and sends no `error` message, because the socket was never accepted.
- **`error.code`** is one of `bad_message`, `schema_mismatch`, `session_mismatch`, `frame_too_large`, `rate_limited`, `disk_full` or `internal`, plus `retryable` and an optional `message`.
- **`hello`** carries `clock_origin` and `media` in addition to the design's fields. Those are what the engine needs to write `manifest.json`. `user_inputs` come later from the GUI.
- **`ping` and `pong`** have no payload.
- **Names.** The class is named `ErrorMessage` (wire `type` stays `"error"`), so the generated types don't collide with built-in `Error` in TypeScript and Dart.

## D9. `schema_version` format

**Decision.** A `"MAJOR.MINOR"` string, starting at `"1.0"`. The engine accepts the same major version (`is_compatible`) and rejects others with `error{schema_mismatch}`. A minor bump only adds optional fields.

**Options weighed:**

- **An integer.** It can't express "compatible addition".
- **Full semver.** The patch number means nothing for a schema.

## D10. Code generators

- **JSON Schema: Pydantic v2 `model_json_schema` / `models_json_schema`.** It's built in, so the Pydantic models stay the only source of truth.
- **TypeScript: `json-schema-to-typescript` 16.0.0.** It's the most widely used JSON Schema→TS generator. It emits plain types and tagged unions with no runtime cost.
- **Dart: `quicktype` 26.0.0.** It's the maintained JSON Schema→Dart generator with `fromJson`/`toJson`, and it runs on Node, so generating needs no Dart toolchain.

**Export details:**

- A combined `contract.schema.json` (every type in `$defs`) feeds both generators, so shared types such as `Capabilities` are emitted once.
- Per-document schemas (`event`, `manifest`, `client_message`, `server_message`, `report`) are what validation uses.
- The exporter drops Pydantic's per-property `title`s, which would otherwise become noise aliases.
- It marks `const` discriminators (`kind`, `type`) as required, so TS can narrow on them.
- A test fails if `schema/generated/` drifts from the models. Regeneration is deterministic.

**Known limitation (Dart).** quicktype flattens tagged unions: Dart gets one `Event` class whose `Data` has every payload field as optional, and one `ClientMessage` or `ServerMessage` class. Reading works. But `Data.toJson()` emits nulls for other kinds' fields, which the strict payload models reject. So the GUI must not send generated `Event` objects back to the engine as they are.

**Options weighed for Dart:**

- **json_serializable.** It needs hand-written Dart classes, which breaks "never hand-edit".
- **A custom sealed-class generator.** Best output, but it's code we'd maintain.
- **quicktype now (chosen).** Revisit in step 5, when the GUI first posts review markers. Likely options then are a thin sealed-class generator over `contract.schema.json`, or engine endpoints that take narrow request bodies instead of full events.

Not code-generated: the binary header (D4), and the cross-field rule "extension ⇔ seq ⇔ `ev_<seq>`". JSON Schema can't express that rule simply, so it's enforced in Python, and at ingest.

## D11. Report sub-models

The design references `Metrics`, `Correctness`, `Complexity`, `Finding` and `Communication` without defining them. Defined as follows:

- **`Metrics`**, from pipeline step 7:
  - `total_time_s` and `time_per_phase_s` (phases are `read`, `plan`, `code`, `debug`, `test`, `submit`; "clarify/plan" is `plan`)
  - `time_to_first_run_s` and `time_to_first_passing_run_s`
  - `runs_before_accept`, `churn` and `longest_idle_s`
  - `talk_ratio`, which is null without audio
- **`Correctness`:** `platform_verdict` (the final submit verdict), `accepted`, the counts `runs`, `failed_runs` and `submits`, and the AI's `explanation` plus `evidence`.
- **`Complexity`:** `time`, `space`, `optimal`, `better_approach` and `evidence`.
- **`Finding`:** `start`, `end`, `title`, `detail`, and `evidence` (at least one ID).
- **`Communication`:** `thinking_aloud`, `clarifying`, `testing_out_loud` and `evidence`.
- **`Report`** also gets `schema_version` and `session_id`, so a stored report is self-describing.

**Model-level checks** cover what can be checked without the timeline:

- `end >= start`
- `time_lost_s <= end - start`
- at least one cited ID

Checking that cited IDs resolve to real events inside the span is the AI layer's validation step (build-plan step 4).

## D12. Fixtures

- **`two_sum_basic`** has 31 captured events and 10 derived events (9 speech, 1 spoken `stuck` marker).
  - Audio is **real silent WebM/Opus**, generated with ffmpeg, so `capabilities.audio = true` is truthful. It's cut into 18 byte slices, matching how MediaRecorder timeslices behave.
  - The transcript is hand-written, and the fixture README says so.
  - **Option rejected:** `audio: false` with speech events. That would contradict the capabilities.
- **`two_sum_seq_gap`** is the same session, with seqs 18–20 lost and seqs 21–22 replayed after a reconnect.
  - It has `end` (`final_seq` 31), so it reads as ended but incomplete.
  - Audio is off. The fixture isolates the transport fault.

## D13. Python package name

The import name is `ic_schema` (distribution `ic-schema`), in `schema/`. A bare `schema` would clash with the existing PyPI package of that name and is too generic to import safely.

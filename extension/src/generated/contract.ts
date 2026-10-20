/* GENERATED from schema/ (Pydantic) by `make schema`. Do not edit. schema_version 1.0 */

/**
 * Text frame sent by the extension.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage = Hello | EventMessage | Ping | Pong | End;
/**
 * Root wrapper so the union gets a named JSON Schema / generated type.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Event".
 */
export type Event =
  | SessionStartEvent
  | SessionEndEvent
  | ProblemLoadedEvent
  | CodeSnapshotEvent
  | CodeDiffEvent
  | KeystrokeEvent
  | PasteEvent
  | UndoEvent
  | RunEvent
  | SubmitEvent
  | RunResultEvent
  | SubmitResultEvent
  | FocusChangeEvent
  | SpeechEvent
  | IdleEvent
  | MarkerEvent;
/**
 * Text frame sent by the engine.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage = Welcome | Ack | Ping | Pong | ErrorMessage;

/**
 * All contract types. Root properties exist only to anchor code generation.
 */
export interface Contract {
  client_message?: ClientMessage;
  event?: Event;
  manifest?: Manifest;
  report?: Report;
  server_message?: ServerMessage;
}
/**
 * Open or resume a session. Carries what the engine needs to write manifest.json.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Hello".
 */
export interface Hello {
  /**
   * Site adapter module name, e.g. 'leetcode'.
   */
  adapter: string;
  capabilities: Capabilities;
  clock_origin: ClockOrigin;
  media?: MediaInfo;
  /**
   * First seq the extension will (re)send; null on a new session.
   */
  resume_from?: number | null;
  schema_version: string;
  session_id: string;
  type: "hello";
}
/**
 * What this session's capture could record, so later stages know what to trust or skip.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Capabilities".
 */
export interface Capabilities {
  adapter_version: string;
  audio: boolean;
  exact_code: boolean;
  keystrokes: "none" | "editor_scoped";
  /**
   * Editor language as reported by the platform.
   */
  language: string;
  mode: "practice" | "mock_interview" | "assessment";
  /**
   * "leetcode", "hackerrank", ...
   */
  platform: string;
  problem_statement: "none" | "scraped" | "manual";
  run_events: boolean;
  video: boolean;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ClockOrigin".
 */
export interface ClockOrigin {
  /**
   * Wall-clock time of session_start (t = 0).
   */
  wall_time_utc: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "MediaInfo".
 */
export interface MediaInfo {
  audio?: MediaStreamInfo | null;
  video?: MediaStreamInfo | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "MediaStreamInfo".
 */
export interface MediaStreamInfo {
  /**
   * MediaRecorder mime type, e.g. "audio/webm;codecs=opus".
   */
  mime: string;
  /**
   * Start of the stream on the session clock (first chunk start).
   */
  offset_s?: number | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "EventMessage".
 */
export interface EventMessage {
  event:
    | SessionStartEvent
    | SessionEndEvent
    | ProblemLoadedEvent
    | CodeSnapshotEvent
    | CodeDiffEvent
    | KeystrokeEvent
    | PasteEvent
    | UndoEvent
    | RunEvent
    | SubmitEvent
    | RunResultEvent
    | SubmitResultEvent
    | FocusChangeEvent
    | SpeechEvent
    | IdleEvent
    | MarkerEvent;
  type: "event";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SessionStartEvent".
 */
export interface SessionStartEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data?: SessionStartData;
  id: string;
  kind: "session_start";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SessionStartData".
 */
export interface SessionStartData {
  url?: string | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SessionEndEvent".
 */
export interface SessionEndEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: SessionEndData;
  id: string;
  kind: "session_end";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SessionEndData".
 */
export interface SessionEndData {
  reason: "user_stop" | "tab_closed" | "navigated_away" | "timeout";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ProblemLoadedEvent".
 */
export interface ProblemLoadedEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: ProblemLoadedData;
  id: string;
  kind: "problem_loaded";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ProblemLoadedData".
 */
export interface ProblemLoadedData {
  constraints?: string[];
  difficulty?: "easy" | "medium" | "hard" | "unknown";
  examples?: Example[];
  platform: string;
  /**
   * Platform problem slug; platform + slug keys repeat attempts.
   */
  slug: string;
  statement?: string | null;
  title: string;
  url: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Example".
 */
export interface Example {
  explanation?: string | null;
  input: string;
  output: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "CodeSnapshotEvent".
 */
export interface CodeSnapshotEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: CodeSnapshotData;
  id: string;
  kind: "code_snapshot";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "CodeSnapshotData".
 */
export interface CodeSnapshotData {
  /**
   * Full editor text.
   */
  code: string;
  /**
   * Editor language of this snapshot. Set when it differs from Capabilities.language, and on every snapshot taken before the session language is locked (at the first edit, run or submit). Absent means Capabilities.language.
   */
  language?: string | null;
  reason: "initial" | "debounce" | "periodic" | "run" | "submit";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "CodeDiffEvent".
 */
export interface CodeDiffEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: CodeDiffData;
  id: string;
  kind: "code_diff";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "CodeDiffData".
 */
export interface CodeDiffData {
  added_lines: number;
  deleted_lines: number;
  from_id: string;
  to_id: string;
  unified_diff: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "KeystrokeEvent".
 */
export interface KeystrokeEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: KeystrokeData;
  id: string;
  kind: "keystroke";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * One burst of editor-scoped keys. `t` is the burst start. Never raw characters.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "KeystrokeData".
 */
export interface KeystrokeData {
  counts: KeyCounts;
  duration_s: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "KeyCounts".
 */
export interface KeyCounts {
  delete?: number;
  insert?: number;
  navigation?: number;
  newline?: number;
  shortcut?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "PasteEvent".
 */
export interface PasteEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: PasteData;
  id: string;
  kind: "paste";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * Size only; the pasted text is visible in the next code snapshot.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "PasteData".
 */
export interface PasteData {
  chars: number;
  lines: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "UndoEvent".
 */
export interface UndoEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data?: UndoData;
  id: string;
  kind: "undo";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "UndoData".
 */
export interface UndoData {
  count?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "RunEvent".
 */
export interface RunEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data?: RunData;
  id: string;
  kind: "run";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "RunData".
 */
export interface RunData {
  trigger?: ("click" | "shortcut") | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SubmitEvent".
 */
export interface SubmitEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data?: SubmitData;
  id: string;
  kind: "submit";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SubmitData".
 */
export interface SubmitData {
  trigger?: ("click" | "shortcut") | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "RunResultEvent".
 */
export interface RunResultEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: RunResultData;
  id: string;
  kind: "run_result";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "RunResultData".
 */
export interface RunResultData {
  actual_output?: string | null;
  error_message?: string | null;
  expected_output?: string | null;
  failing_input?: string | null;
  memory_mb?: number | null;
  passed_cases?: number | null;
  /**
   * Id of the `run` event this result answers.
   */
  run_id: string;
  runtime_ms?: number | null;
  stdout?: string | null;
  total_cases?: number | null;
  verdict:
    | "accepted"
    | "wrong_answer"
    | "runtime_error"
    | "compile_error"
    | "time_limit_exceeded"
    | "memory_limit_exceeded"
    | "output_limit_exceeded"
    | "unknown";
  /**
   * Verdict text as the platform shows it.
   */
  verdict_raw?: string | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SubmitResultEvent".
 */
export interface SubmitResultEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: SubmitResultData;
  id: string;
  kind: "submit_result";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SubmitResultData".
 */
export interface SubmitResultData {
  actual_output?: string | null;
  error_message?: string | null;
  expected_output?: string | null;
  failing_input?: string | null;
  memory_mb?: number | null;
  passed_cases?: number | null;
  runtime_ms?: number | null;
  stdout?: string | null;
  /**
   * Id of the `submit` event this result answers.
   */
  submit_id: string;
  total_cases?: number | null;
  verdict:
    | "accepted"
    | "wrong_answer"
    | "runtime_error"
    | "compile_error"
    | "time_limit_exceeded"
    | "memory_limit_exceeded"
    | "output_limit_exceeded"
    | "unknown";
  /**
   * Verdict text as the platform shows it.
   */
  verdict_raw?: string | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "FocusChangeEvent".
 */
export interface FocusChangeEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: FocusChangeData;
  id: string;
  kind: "focus_change";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "FocusChangeData".
 */
export interface FocusChangeData {
  state: "away" | "back";
  target: "tab" | "window" | "editor";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SpeechEvent".
 */
export interface SpeechEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: SpeechData;
  id: string;
  kind: "speech";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * Transcript segment. `t` is the segment start; `end` is on the same session clock.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SpeechData".
 */
export interface SpeechData {
  /**
   * Cue phrases, e.g. "wait".
   */
  cues?: string[];
  end: number;
  text: string;
  words?: Word[] | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Word".
 */
export interface Word {
  end: number;
  p?: number | null;
  start: number;
  w: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "IdleEvent".
 */
export interface IdleEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: IdleData;
  id: string;
  kind: "idle";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "IdleData".
 */
export interface IdleData {
  duration_s: number;
  end: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "MarkerEvent".
 */
export interface MarkerEvent {
  /**
   * 1.0 = exact.
   */
  confidence?: number;
  data: MarkerData;
  id: string;
  kind: "marker";
  /**
   * Capture sequence number; required for source=extension.
   */
  seq?: number | null;
  source: "extension" | "engine" | "whisper" | "user";
  /**
   * Seconds from session_start.
   */
  t: number;
  t_uncertainty?: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "MarkerData".
 */
export interface MarkerData {
  label: "stuck" | "idea" | "done";
  origin: "hotkey" | "speech" | "review";
  /**
   * Spoken phrase, for origin=speech.
   */
  text?: string | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Ping".
 */
export interface Ping {
  type: "ping";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Pong".
 */
export interface Pong {
  type: "pong";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "End".
 */
export interface End {
  /**
   * Last chunk index per stream; omit streams not recorded.
   */
  final_chunk?: {
    [k: string]: number | undefined;
  };
  final_seq: number;
  type: "end";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Manifest".
 */
export interface Manifest {
  capabilities: Capabilities;
  clock_origin: ClockOrigin;
  end?: EndInfo | null;
  media?: MediaInfo;
  schema_version?: string;
  session_id: string;
  user_inputs?: UserInputs;
}
/**
 * Written when the extension sends `end`. Absent means the session never closed cleanly.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "EndInfo".
 */
export interface EndInfo {
  final_chunk?: {
    [k: string]: number | undefined;
  };
  final_seq: number;
}
/**
 * Small inputs inline; larger ones are files under `inputs/`, referenced by relative path.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "UserInputs".
 */
export interface UserInputs {
  /**
   * Path under inputs/.
   */
  reference_solution?: string | null;
  self_assessment?: string | null;
  target_time_s?: number | null;
  /**
   * Path under inputs/.
   */
  tests?: string | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Report".
 */
export interface Report {
  communication: Communication;
  complexity: Complexity;
  correctness: Correctness;
  metrics: Metrics;
  next_practice?: string[];
  schema_version?: string;
  session_id: string;
  strengths: Finding[];
  /**
   * Edge cases to consider; never executed.
   */
  suggested_tests?: string[];
  summary: string;
  time_sinks: TimeSink[];
  /**
   * Most recent confirmed repeat only; null otherwise.
   */
  vs_previous_attempts?: string | null;
  /**
   * Where your read differs from the evidence.
   */
  vs_self_assessment: string;
  weaknesses: Finding[];
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Communication".
 */
export interface Communication {
  clarifying: string;
  evidence?: string[];
  testing_out_loud: string;
  thinking_aloud: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Complexity".
 */
export interface Complexity {
  better_approach?: string | null;
  evidence?: string[];
  optimal?: boolean | null;
  space: string;
  /**
   * e.g. "O(n)"
   */
  time: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Correctness".
 */
export interface Correctness {
  accepted: boolean;
  evidence?: string[];
  /**
   * AI reasoning about failures and correctness.
   */
  explanation: string;
  failed_runs: number;
  /**
   * Final submit verdict; null if never submitted.
   */
  platform_verdict:
    | (
        | "accepted"
        | "wrong_answer"
        | "runtime_error"
        | "compile_error"
        | "time_limit_exceeded"
        | "memory_limit_exceeded"
        | "output_limit_exceeded"
        | "unknown"
      )
    | null;
  runs: number;
  submits: number;
}
/**
 * Computed deterministically by the engine (pipeline step 7).
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Metrics".
 */
export interface Metrics {
  /**
   * Deleted / added lines, session-wide.
   */
  churn?: number | null;
  longest_idle_s?: number;
  runs_before_accept?: number | null;
  /**
   * Speech time / session time; null without audio.
   */
  talk_ratio?: number | null;
  time_per_phase_s?: {
    [k: string]: number | undefined;
  };
  time_to_first_passing_run_s?: number | null;
  time_to_first_run_s?: number | null;
  total_time_s: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  detail: string;
  end: number;
  /**
   * Cited event ids.
   *
   * @minItems 1
   */
  evidence: [string, ...string[]];
  start: number;
  title: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "TimeSink".
 */
export interface TimeSink {
  category:
    | "understanding"
    | "input_parsing"
    | "output_format"
    | "algorithm_choice"
    | "implementation"
    | "debugging"
    | "edge_cases"
    | "syntax_api_recall"
    | "communication";
  end: number;
  /**
   * Cited event ids.
   *
   * @minItems 1
   */
  evidence: [string, ...string[]];
  start: number;
  suggestion: string;
  time_lost_s: number;
  what_happened: string;
}
/**
 * What the engine already holds: the highest seq / chunk index with no gaps below it.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Welcome".
 */
export interface Welcome {
  last_chunk?: {
    [k: string]: number | undefined;
  };
  /**
   * 0 when nothing has been received.
   */
  last_seq: number;
  session_id: string;
  type: "welcome";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Ack".
 */
export interface Ack {
  chunk?: ChunkRef | null;
  /**
   * Every event with seq <= this is stored.
   */
  seq?: number | null;
  type: "ack";
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ChunkRef".
 */
export interface ChunkRef {
  index: number;
  stream: "audio" | "video";
}
/**
 * Origin and token failures close the socket with code 4403 instead of sending an error.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ErrorMessage".
 */
export interface ErrorMessage {
  code:
    | "bad_message"
    | "schema_mismatch"
    | "session_mismatch"
    | "frame_too_large"
    | "rate_limited"
    | "disk_full"
    | "internal";
  message?: string | null;
  retryable: boolean;
  type: "error";
}

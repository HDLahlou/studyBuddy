// To parse this JSON data, do
//
//     final contract = contractFromJson(jsonString);

import 'dart:convert';

Contract contractFromJson(String str) => Contract.fromJson(json.decode(str));

String contractToJson(Contract data) => json.encode(data.toJson());

///All contract types. Root properties exist only to anchor code generation.
class Contract {
  final ClientMessage? clientMessage;
  final Event? event;
  final Manifest? manifest;
  final Report? report;
  final ServerMessage? serverMessage;

  Contract({
    this.clientMessage,
    this.event,
    this.manifest,
    this.report,
    this.serverMessage,
  });

  factory Contract.fromJson(Map<String, dynamic> json) => Contract(
    clientMessage: json["client_message"] == null
        ? null
        : ClientMessage.fromJson(json["client_message"]),
    event: json["event"] == null ? null : Event.fromJson(json["event"]),
    manifest: json["manifest"] == null
        ? null
        : Manifest.fromJson(json["manifest"]),
    report: json["report"] == null ? null : Report.fromJson(json["report"]),
    serverMessage: json["server_message"] == null
        ? null
        : ServerMessage.fromJson(json["server_message"]),
  );

  Map<String, dynamic> toJson() => {
    "client_message": clientMessage?.toJson(),
    "event": event?.toJson(),
    "manifest": manifest?.toJson(),
    "report": report?.toJson(),
    "server_message": serverMessage?.toJson(),
  };
}

///Text frame sent by the extension.
///
///Open or resume a session. Carries what the engine needs to write manifest.json.
class ClientMessage {
  ///Site adapter module name, e.g. 'leetcode'.
  final String? adapter;
  final Capabilities? capabilities;
  final ClockOrigin? clockOrigin;
  final MediaInfo? media;

  ///First seq the extension will (re)send; null on a new session.
  final int? resumeFrom;
  final String? schemaVersion;
  final String? sessionId;
  final ClientMessageType type;
  final Event? event;

  ///Last chunk index per stream; omit streams not recorded.
  final Map<String, int>? finalChunk;
  final int? finalSeq;

  ClientMessage({
    this.adapter,
    this.capabilities,
    this.clockOrigin,
    this.media,
    this.resumeFrom,
    this.schemaVersion,
    this.sessionId,
    required this.type,
    this.event,
    this.finalChunk,
    this.finalSeq,
  });

  factory ClientMessage.fromJson(Map<String, dynamic> json) => ClientMessage(
    adapter: json["adapter"],
    capabilities: json["capabilities"] == null
        ? null
        : Capabilities.fromJson(json["capabilities"]),
    clockOrigin: json["clock_origin"] == null
        ? null
        : ClockOrigin.fromJson(json["clock_origin"]),
    media: json["media"] == null ? null : MediaInfo.fromJson(json["media"]),
    resumeFrom: json["resume_from"],
    schemaVersion: json["schema_version"],
    sessionId: json["session_id"],
    type: clientMessageTypeValues.map[json["type"]]!,
    event: json["event"] == null ? null : Event.fromJson(json["event"]),
    finalChunk: Map.from(json["final_chunk"]!)
        .map((k, v) => MapEntry<String, int>(k, v)),
    finalSeq: json["final_seq"],
  );

  Map<String, dynamic> toJson() => {
    "adapter": adapter,
    "capabilities": capabilities?.toJson(),
    "clock_origin": clockOrigin?.toJson(),
    "media": media?.toJson(),
    "resume_from": resumeFrom,
    "schema_version": schemaVersion,
    "session_id": sessionId,
    "type": clientMessageTypeValues.reverse[type],
    "event": event?.toJson(),
    "final_chunk": Map.from(finalChunk!)
        .map((k, v) => MapEntry<String, dynamic>(k, v)),
    "final_seq": finalSeq,
  };
}

///What this session's capture could record, so later stages know what to trust or skip.
class Capabilities {
  final String adapterVersion;
  final bool audio;
  final bool exactCode;
  final Keystrokes keystrokes;

  ///Editor language as reported by the platform.
  final String language;
  final Mode mode;

  ///"leetcode", "hackerrank", ...
  final String platform;
  final ProblemStatement problemStatement;
  final bool runEvents;
  final bool video;

  Capabilities({
    required this.adapterVersion,
    required this.audio,
    required this.exactCode,
    required this.keystrokes,
    required this.language,
    required this.mode,
    required this.platform,
    required this.problemStatement,
    required this.runEvents,
    required this.video,
  });

  factory Capabilities.fromJson(Map<String, dynamic> json) => Capabilities(
    adapterVersion: json["adapter_version"],
    audio: json["audio"],
    exactCode: json["exact_code"],
    keystrokes: keystrokesValues.map[json["keystrokes"]]!,
    language: json["language"],
    mode: modeValues.map[json["mode"]]!,
    platform: json["platform"],
    problemStatement: problemStatementValues.map[json["problem_statement"]]!,
    runEvents: json["run_events"],
    video: json["video"],
  );

  Map<String, dynamic> toJson() => {
    "adapter_version": adapterVersion,
    "audio": audio,
    "exact_code": exactCode,
    "keystrokes": keystrokesValues.reverse[keystrokes],
    "language": language,
    "mode": modeValues.reverse[mode],
    "platform": platform,
    "problem_statement": problemStatementValues.reverse[problemStatement],
    "run_events": runEvents,
    "video": video,
  };
}

enum Keystrokes { EDITOR_SCOPED, NONE }

final keystrokesValues = EnumValues({
  "editor_scoped": Keystrokes.EDITOR_SCOPED,
  "none": Keystrokes.NONE,
});

enum Mode { ASSESSMENT, MOCK_INTERVIEW, PRACTICE }

final modeValues = EnumValues({
  "assessment": Mode.ASSESSMENT,
  "mock_interview": Mode.MOCK_INTERVIEW,
  "practice": Mode.PRACTICE,
});

enum ProblemStatement { MANUAL, NONE, SCRAPED }

final problemStatementValues = EnumValues({
  "manual": ProblemStatement.MANUAL,
  "none": ProblemStatement.NONE,
  "scraped": ProblemStatement.SCRAPED,
});

class ClockOrigin {
  ///Wall-clock time of session_start (t = 0).
  final DateTime wallTimeUtc;

  ClockOrigin({required this.wallTimeUtc});

  factory ClockOrigin.fromJson(Map<String, dynamic> json) =>
      ClockOrigin(wallTimeUtc: DateTime.parse(json["wall_time_utc"]));

  Map<String, dynamic> toJson() => {
    "wall_time_utc": wallTimeUtc.toIso8601String(),
  };
}

///Root wrapper so the union gets a named JSON Schema / generated type.
class Event {
  ///1.0 = exact.
  final double? confidence;
  final Data? data;
  final String id;
  final Kind kind;

  ///Capture sequence number; required for source=extension.
  final int? seq;
  final Source source;

  ///Seconds from session_start.
  final double t;
  final double? tUncertainty;

  Event({
    this.confidence,
    this.data,
    required this.id,
    required this.kind,
    this.seq,
    required this.source,
    required this.t,
    this.tUncertainty,
  });

  factory Event.fromJson(Map<String, dynamic> json) => Event(
    confidence: json["confidence"]?.toDouble(),
    data: json["data"] == null ? null : Data.fromJson(json["data"]),
    id: json["id"],
    kind: kindValues.map[json["kind"]]!,
    seq: json["seq"],
    source: sourceValues.map[json["source"]]!,
    t: json["t"]?.toDouble(),
    tUncertainty: json["t_uncertainty"]?.toDouble(),
  );

  Map<String, dynamic> toJson() => {
    "confidence": confidence,
    "data": data?.toJson(),
    "id": id,
    "kind": kindValues.reverse[kind],
    "seq": seq,
    "source": sourceValues.reverse[source],
    "t": t,
    "t_uncertainty": tUncertainty,
  };
}

///One burst of editor-scoped keys. `t` is the burst start. Never raw characters.
///
///Size only; the pasted text is visible in the next code snapshot.
///
///Transcript segment. `t` is the segment start; `end` is on the same session clock.
class Data {
  final String? url;
  final Reason? reason;
  final List<String>? constraints;
  final Difficulty? difficulty;
  final List<Example>? examples;
  final String? platform;

  ///Platform problem slug; platform + slug keys repeat attempts.
  final String? slug;
  final String? statement;
  final String? title;

  ///Full editor text.
  final String? code;

  ///Editor language of this snapshot. Set when it differs from Capabilities.language, and on
  ///every snapshot taken before the session language is locked (at the first edit, run or
  ///submit). Absent means Capabilities.language.
  final String? language;
  final int? addedLines;
  final int? deletedLines;
  final String? fromId;
  final String? toId;
  final String? unifiedDiff;
  final KeyCounts? counts;
  final double? durationS;
  final int? chars;
  final int? lines;
  final int? count;
  final Trigger? trigger;
  final String? actualOutput;
  final String? errorMessage;
  final String? expectedOutput;
  final String? failingInput;
  final double? memoryMb;
  final int? passedCases;

  ///Id of the `run` event this result answers.
  final String? runId;
  final double? runtimeMs;
  final String? stdout;
  final int? totalCases;
  final Verdict? verdict;

  ///Verdict text as the platform shows it.
  final String? verdictRaw;

  ///Id of the `submit` event this result answers.
  final String? submitId;
  final State? state;
  final Target? target;

  ///Cue phrases, e.g. "wait".
  final List<String>? cues;
  final double? end;

  ///Spoken phrase, for origin=speech.
  final String? text;
  final List<Word>? words;
  final Label? label;
  final Origin? origin;

  Data({
    this.url,
    this.reason,
    this.constraints,
    this.difficulty,
    this.examples,
    this.platform,
    this.slug,
    this.statement,
    this.title,
    this.code,
    this.language,
    this.addedLines,
    this.deletedLines,
    this.fromId,
    this.toId,
    this.unifiedDiff,
    this.counts,
    this.durationS,
    this.chars,
    this.lines,
    this.count,
    this.trigger,
    this.actualOutput,
    this.errorMessage,
    this.expectedOutput,
    this.failingInput,
    this.memoryMb,
    this.passedCases,
    this.runId,
    this.runtimeMs,
    this.stdout,
    this.totalCases,
    this.verdict,
    this.verdictRaw,
    this.submitId,
    this.state,
    this.target,
    this.cues,
    this.end,
    this.text,
    this.words,
    this.label,
    this.origin,
  });

  factory Data.fromJson(Map<String, dynamic> json) => Data(
    url: json["url"],
    reason: reasonValues.map[json["reason"]],
    constraints: json["constraints"] == null
        ? []
        : List<String>.from(json["constraints"]!.map((x) => x)),
    difficulty: difficultyValues.map[json["difficulty"]],
    examples: json["examples"] == null
        ? []
        : List<Example>.from(json["examples"]!.map((x) => Example.fromJson(x))),
    platform: json["platform"],
    slug: json["slug"],
    statement: json["statement"],
    title: json["title"],
    code: json["code"],
    language: json["language"],
    addedLines: json["added_lines"],
    deletedLines: json["deleted_lines"],
    fromId: json["from_id"],
    toId: json["to_id"],
    unifiedDiff: json["unified_diff"],
    counts: json["counts"] == null ? null : KeyCounts.fromJson(json["counts"]),
    durationS: json["duration_s"]?.toDouble(),
    chars: json["chars"],
    lines: json["lines"],
    count: json["count"],
    trigger: triggerValues.map[json["trigger"]],
    actualOutput: json["actual_output"],
    errorMessage: json["error_message"],
    expectedOutput: json["expected_output"],
    failingInput: json["failing_input"],
    memoryMb: json["memory_mb"]?.toDouble(),
    passedCases: json["passed_cases"],
    runId: json["run_id"],
    runtimeMs: json["runtime_ms"]?.toDouble(),
    stdout: json["stdout"],
    totalCases: json["total_cases"],
    verdict: verdictValues.map[json["verdict"]],
    verdictRaw: json["verdict_raw"],
    submitId: json["submit_id"],
    state: stateValues.map[json["state"]],
    target: targetValues.map[json["target"]],
    cues: json["cues"] == null
        ? []
        : List<String>.from(json["cues"]!.map((x) => x)),
    end: json["end"]?.toDouble(),
    text: json["text"],
    words: json["words"] == null
        ? []
        : List<Word>.from(json["words"]!.map((x) => Word.fromJson(x))),
    label: labelValues.map[json["label"]],
    origin: originValues.map[json["origin"]],
  );

  Map<String, dynamic> toJson() => {
    "url": url,
    "reason": reasonValues.reverse[reason],
    "constraints": constraints == null
        ? []
        : List<dynamic>.from(constraints!.map((x) => x)),
    "difficulty": difficultyValues.reverse[difficulty],
    "examples": examples == null
        ? []
        : List<dynamic>.from(examples!.map((x) => x.toJson())),
    "platform": platform,
    "slug": slug,
    "statement": statement,
    "title": title,
    "code": code,
    "language": language,
    "added_lines": addedLines,
    "deleted_lines": deletedLines,
    "from_id": fromId,
    "to_id": toId,
    "unified_diff": unifiedDiff,
    "counts": counts?.toJson(),
    "duration_s": durationS,
    "chars": chars,
    "lines": lines,
    "count": count,
    "trigger": triggerValues.reverse[trigger],
    "actual_output": actualOutput,
    "error_message": errorMessage,
    "expected_output": expectedOutput,
    "failing_input": failingInput,
    "memory_mb": memoryMb,
    "passed_cases": passedCases,
    "run_id": runId,
    "runtime_ms": runtimeMs,
    "stdout": stdout,
    "total_cases": totalCases,
    "verdict": verdictValues.reverse[verdict],
    "verdict_raw": verdictRaw,
    "submit_id": submitId,
    "state": stateValues.reverse[state],
    "target": targetValues.reverse[target],
    "cues": cues == null ? [] : List<dynamic>.from(cues!.map((x) => x)),
    "end": end,
    "text": text,
    "words": words == null
        ? []
        : List<dynamic>.from(words!.map((x) => x.toJson())),
    "label": labelValues.reverse[label],
    "origin": originValues.reverse[origin],
  };
}

class KeyCounts {
  final int? delete;
  final int? insert;
  final int? navigation;
  final int? newline;
  final int? shortcut;

  KeyCounts({
    this.delete,
    this.insert,
    this.navigation,
    this.newline,
    this.shortcut,
  });

  factory KeyCounts.fromJson(Map<String, dynamic> json) => KeyCounts(
    delete: json["delete"],
    insert: json["insert"],
    navigation: json["navigation"],
    newline: json["newline"],
    shortcut: json["shortcut"],
  );

  Map<String, dynamic> toJson() => {
    "delete": delete,
    "insert": insert,
    "navigation": navigation,
    "newline": newline,
    "shortcut": shortcut,
  };
}

enum Difficulty { EASY, HARD, MEDIUM, UNKNOWN }

final difficultyValues = EnumValues({
  "easy": Difficulty.EASY,
  "hard": Difficulty.HARD,
  "medium": Difficulty.MEDIUM,
  "unknown": Difficulty.UNKNOWN,
});

class Example {
  final String? explanation;
  final String input;
  final String output;

  Example({this.explanation, required this.input, required this.output});

  factory Example.fromJson(Map<String, dynamic> json) => Example(
    explanation: json["explanation"],
    input: json["input"],
    output: json["output"],
  );

  Map<String, dynamic> toJson() => {
    "explanation": explanation,
    "input": input,
    "output": output,
  };
}

enum Label { DONE, IDEA, STUCK }

final labelValues = EnumValues({
  "done": Label.DONE,
  "idea": Label.IDEA,
  "stuck": Label.STUCK,
});

enum Origin { HOTKEY, REVIEW, SPEECH }

final originValues = EnumValues({
  "hotkey": Origin.HOTKEY,
  "review": Origin.REVIEW,
  "speech": Origin.SPEECH,
});

enum Reason {
  DEBOUNCE,
  INITIAL,
  NAVIGATED_AWAY,
  PERIODIC,
  RUN,
  SUBMIT,
  TAB_CLOSED,
  TIMEOUT,
  USER_STOP,
}

final reasonValues = EnumValues({
  "debounce": Reason.DEBOUNCE,
  "initial": Reason.INITIAL,
  "navigated_away": Reason.NAVIGATED_AWAY,
  "periodic": Reason.PERIODIC,
  "run": Reason.RUN,
  "submit": Reason.SUBMIT,
  "tab_closed": Reason.TAB_CLOSED,
  "timeout": Reason.TIMEOUT,
  "user_stop": Reason.USER_STOP,
});

enum State { AWAY, BACK }

final stateValues = EnumValues({"away": State.AWAY, "back": State.BACK});

enum Target { EDITOR, TAB, WINDOW }

final targetValues = EnumValues({
  "editor": Target.EDITOR,
  "tab": Target.TAB,
  "window": Target.WINDOW,
});

enum Trigger { CLICK, SHORTCUT }

final triggerValues = EnumValues({
  "click": Trigger.CLICK,
  "shortcut": Trigger.SHORTCUT,
});

enum Verdict {
  ACCEPTED,
  COMPILE_ERROR,
  MEMORY_LIMIT_EXCEEDED,
  OUTPUT_LIMIT_EXCEEDED,
  RUNTIME_ERROR,
  TIME_LIMIT_EXCEEDED,
  UNKNOWN,
  WRONG_ANSWER,
}

final verdictValues = EnumValues({
  "accepted": Verdict.ACCEPTED,
  "compile_error": Verdict.COMPILE_ERROR,
  "memory_limit_exceeded": Verdict.MEMORY_LIMIT_EXCEEDED,
  "output_limit_exceeded": Verdict.OUTPUT_LIMIT_EXCEEDED,
  "runtime_error": Verdict.RUNTIME_ERROR,
  "time_limit_exceeded": Verdict.TIME_LIMIT_EXCEEDED,
  "unknown": Verdict.UNKNOWN,
  "wrong_answer": Verdict.WRONG_ANSWER,
});

class Word {
  final double end;
  final double? p;
  final double start;
  final String w;

  Word({required this.end, this.p, required this.start, required this.w});

  factory Word.fromJson(Map<String, dynamic> json) => Word(
    end: json["end"]?.toDouble(),
    p: json["p"]?.toDouble(),
    start: json["start"]?.toDouble(),
    w: json["w"],
  );

  Map<String, dynamic> toJson() => {"end": end, "p": p, "start": start, "w": w};
}

enum Kind {
  CODE_DIFF,
  CODE_SNAPSHOT,
  FOCUS_CHANGE,
  IDLE,
  KEYSTROKE,
  MARKER,
  PASTE,
  PROBLEM_LOADED,
  RUN,
  RUN_RESULT,
  SESSION_END,
  SESSION_START,
  SPEECH,
  SUBMIT,
  SUBMIT_RESULT,
  UNDO,
}

final kindValues = EnumValues({
  "code_diff": Kind.CODE_DIFF,
  "code_snapshot": Kind.CODE_SNAPSHOT,
  "focus_change": Kind.FOCUS_CHANGE,
  "idle": Kind.IDLE,
  "keystroke": Kind.KEYSTROKE,
  "marker": Kind.MARKER,
  "paste": Kind.PASTE,
  "problem_loaded": Kind.PROBLEM_LOADED,
  "run": Kind.RUN,
  "run_result": Kind.RUN_RESULT,
  "session_end": Kind.SESSION_END,
  "session_start": Kind.SESSION_START,
  "speech": Kind.SPEECH,
  "submit": Kind.SUBMIT,
  "submit_result": Kind.SUBMIT_RESULT,
  "undo": Kind.UNDO,
});

enum Source { ENGINE, EXTENSION, USER, WHISPER }

final sourceValues = EnumValues({
  "engine": Source.ENGINE,
  "extension": Source.EXTENSION,
  "user": Source.USER,
  "whisper": Source.WHISPER,
});

class MediaInfo {
  final MediaStreamInfo? audio;
  final MediaStreamInfo? video;

  MediaInfo({this.audio, this.video});

  factory MediaInfo.fromJson(Map<String, dynamic> json) => MediaInfo(
    audio: json["audio"] == null
        ? null
        : MediaStreamInfo.fromJson(json["audio"]),
    video: json["video"] == null
        ? null
        : MediaStreamInfo.fromJson(json["video"]),
  );

  Map<String, dynamic> toJson() => {
    "audio": audio?.toJson(),
    "video": video?.toJson(),
  };
}

class MediaStreamInfo {
  ///MediaRecorder mime type, e.g. "audio/webm;codecs=opus".
  final String mime;

  ///Start of the stream on the session clock (first chunk start).
  final double? offsetS;

  MediaStreamInfo({required this.mime, this.offsetS});

  factory MediaStreamInfo.fromJson(Map<String, dynamic> json) =>
      MediaStreamInfo(
        mime: json["mime"],
        offsetS: json["offset_s"]?.toDouble(),
      );

  Map<String, dynamic> toJson() => {"mime": mime, "offset_s": offsetS};
}

enum ClientMessageType { END, EVENT, HELLO, PING, PONG }

final clientMessageTypeValues = EnumValues({
  "end": ClientMessageType.END,
  "event": ClientMessageType.EVENT,
  "hello": ClientMessageType.HELLO,
  "ping": ClientMessageType.PING,
  "pong": ClientMessageType.PONG,
});

class Manifest {
  final Capabilities capabilities;
  final ClockOrigin clockOrigin;
  final EndInfo? end;
  final MediaInfo? media;
  final String? schemaVersion;
  final String sessionId;
  final UserInputs? userInputs;

  Manifest({
    required this.capabilities,
    required this.clockOrigin,
    this.end,
    this.media,
    this.schemaVersion,
    required this.sessionId,
    this.userInputs,
  });

  factory Manifest.fromJson(Map<String, dynamic> json) => Manifest(
    capabilities: Capabilities.fromJson(json["capabilities"]),
    clockOrigin: ClockOrigin.fromJson(json["clock_origin"]),
    end: json["end"] == null ? null : EndInfo.fromJson(json["end"]),
    media: json["media"] == null ? null : MediaInfo.fromJson(json["media"]),
    schemaVersion: json["schema_version"],
    sessionId: json["session_id"],
    userInputs: json["user_inputs"] == null
        ? null
        : UserInputs.fromJson(json["user_inputs"]),
  );

  Map<String, dynamic> toJson() => {
    "capabilities": capabilities.toJson(),
    "clock_origin": clockOrigin.toJson(),
    "end": end?.toJson(),
    "media": media?.toJson(),
    "schema_version": schemaVersion,
    "session_id": sessionId,
    "user_inputs": userInputs?.toJson(),
  };
}

///Written when the extension sends `end`. Absent means the session never closed cleanly.
class EndInfo {
  final Map<String, int>? finalChunk;
  final int finalSeq;

  EndInfo({this.finalChunk, required this.finalSeq});

  factory EndInfo.fromJson(Map<String, dynamic> json) => EndInfo(
    finalChunk: Map.from(json["final_chunk"]!)
        .map((k, v) => MapEntry<String, int>(k, v)),
    finalSeq: json["final_seq"],
  );

  Map<String, dynamic> toJson() => {
    "final_chunk": Map.from(finalChunk!)
        .map((k, v) => MapEntry<String, dynamic>(k, v)),
    "final_seq": finalSeq,
  };
}

///Small inputs inline; larger ones are files under `inputs/`, referenced by relative path.
class UserInputs {
  ///Path under inputs/.
  final String? referenceSolution;
  final String? selfAssessment;
  final double? targetTimeS;

  ///Path under inputs/.
  final String? tests;

  UserInputs({
    this.referenceSolution,
    this.selfAssessment,
    this.targetTimeS,
    this.tests,
  });

  factory UserInputs.fromJson(Map<String, dynamic> json) => UserInputs(
    referenceSolution: json["reference_solution"],
    selfAssessment: json["self_assessment"],
    targetTimeS: json["target_time_s"]?.toDouble(),
    tests: json["tests"],
  );

  Map<String, dynamic> toJson() => {
    "reference_solution": referenceSolution,
    "self_assessment": selfAssessment,
    "target_time_s": targetTimeS,
    "tests": tests,
  };
}

class Report {
  final Communication communication;
  final Complexity complexity;
  final Correctness correctness;
  final Metrics metrics;
  final List<String>? nextPractice;
  final String? schemaVersion;
  final String sessionId;
  final List<Finding> strengths;

  ///Edge cases to consider; never executed.
  final List<String>? suggestedTests;
  final String summary;
  final List<TimeSink> timeSinks;

  ///Most recent confirmed repeat only; null otherwise.
  final String? vsPreviousAttempts;

  ///Where your read differs from the evidence.
  final String vsSelfAssessment;
  final List<Finding> weaknesses;

  Report({
    required this.communication,
    required this.complexity,
    required this.correctness,
    required this.metrics,
    this.nextPractice,
    this.schemaVersion,
    required this.sessionId,
    required this.strengths,
    this.suggestedTests,
    required this.summary,
    required this.timeSinks,
    this.vsPreviousAttempts,
    required this.vsSelfAssessment,
    required this.weaknesses,
  });

  factory Report.fromJson(Map<String, dynamic> json) => Report(
    communication: Communication.fromJson(json["communication"]),
    complexity: Complexity.fromJson(json["complexity"]),
    correctness: Correctness.fromJson(json["correctness"]),
    metrics: Metrics.fromJson(json["metrics"]),
    nextPractice: json["next_practice"] == null
        ? []
        : List<String>.from(json["next_practice"]!.map((x) => x)),
    schemaVersion: json["schema_version"],
    sessionId: json["session_id"],
    strengths: List<Finding>.from(
      json["strengths"].map((x) => Finding.fromJson(x)),
    ),
    suggestedTests: json["suggested_tests"] == null
        ? []
        : List<String>.from(json["suggested_tests"]!.map((x) => x)),
    summary: json["summary"],
    timeSinks: List<TimeSink>.from(
      json["time_sinks"].map((x) => TimeSink.fromJson(x)),
    ),
    vsPreviousAttempts: json["vs_previous_attempts"],
    vsSelfAssessment: json["vs_self_assessment"],
    weaknesses: List<Finding>.from(
      json["weaknesses"].map((x) => Finding.fromJson(x)),
    ),
  );

  Map<String, dynamic> toJson() => {
    "communication": communication.toJson(),
    "complexity": complexity.toJson(),
    "correctness": correctness.toJson(),
    "metrics": metrics.toJson(),
    "next_practice": nextPractice == null
        ? []
        : List<dynamic>.from(nextPractice!.map((x) => x)),
    "schema_version": schemaVersion,
    "session_id": sessionId,
    "strengths": List<dynamic>.from(strengths.map((x) => x.toJson())),
    "suggested_tests": suggestedTests == null
        ? []
        : List<dynamic>.from(suggestedTests!.map((x) => x)),
    "summary": summary,
    "time_sinks": List<dynamic>.from(timeSinks.map((x) => x.toJson())),
    "vs_previous_attempts": vsPreviousAttempts,
    "vs_self_assessment": vsSelfAssessment,
    "weaknesses": List<dynamic>.from(weaknesses.map((x) => x.toJson())),
  };
}

class Communication {
  final String clarifying;
  final List<String>? evidence;
  final String testingOutLoud;
  final String thinkingAloud;

  Communication({
    required this.clarifying,
    this.evidence,
    required this.testingOutLoud,
    required this.thinkingAloud,
  });

  factory Communication.fromJson(Map<String, dynamic> json) => Communication(
    clarifying: json["clarifying"],
    evidence: json["evidence"] == null
        ? []
        : List<String>.from(json["evidence"]!.map((x) => x)),
    testingOutLoud: json["testing_out_loud"],
    thinkingAloud: json["thinking_aloud"],
  );

  Map<String, dynamic> toJson() => {
    "clarifying": clarifying,
    "evidence": evidence == null
        ? []
        : List<dynamic>.from(evidence!.map((x) => x)),
    "testing_out_loud": testingOutLoud,
    "thinking_aloud": thinkingAloud,
  };
}

class Complexity {
  final String? betterApproach;
  final List<String>? evidence;
  final bool? optimal;
  final String space;

  ///e.g. "O(n)"
  final String time;

  Complexity({
    this.betterApproach,
    this.evidence,
    this.optimal,
    required this.space,
    required this.time,
  });

  factory Complexity.fromJson(Map<String, dynamic> json) => Complexity(
    betterApproach: json["better_approach"],
    evidence: json["evidence"] == null
        ? []
        : List<String>.from(json["evidence"]!.map((x) => x)),
    optimal: json["optimal"],
    space: json["space"],
    time: json["time"],
  );

  Map<String, dynamic> toJson() => {
    "better_approach": betterApproach,
    "evidence": evidence == null
        ? []
        : List<dynamic>.from(evidence!.map((x) => x)),
    "optimal": optimal,
    "space": space,
    "time": time,
  };
}

class Correctness {
  final bool accepted;
  final List<String>? evidence;

  ///AI reasoning about failures and correctness.
  final String explanation;
  final int failedRuns;

  ///Final submit verdict; null if never submitted.
  final Verdict? platformVerdict;
  final int runs;
  final int submits;

  Correctness({
    required this.accepted,
    this.evidence,
    required this.explanation,
    required this.failedRuns,
    required this.platformVerdict,
    required this.runs,
    required this.submits,
  });

  factory Correctness.fromJson(Map<String, dynamic> json) => Correctness(
    accepted: json["accepted"],
    evidence: json["evidence"] == null
        ? []
        : List<String>.from(json["evidence"]!.map((x) => x)),
    explanation: json["explanation"],
    failedRuns: json["failed_runs"],
    platformVerdict: verdictValues.map[json["platform_verdict"]],
    runs: json["runs"],
    submits: json["submits"],
  );

  Map<String, dynamic> toJson() => {
    "accepted": accepted,
    "evidence": evidence == null
        ? []
        : List<dynamic>.from(evidence!.map((x) => x)),
    "explanation": explanation,
    "failed_runs": failedRuns,
    "platform_verdict": verdictValues.reverse[platformVerdict],
    "runs": runs,
    "submits": submits,
  };
}

///Computed deterministically by the engine (pipeline step 7).
class Metrics {
  ///Deleted / added lines, session-wide.
  final double? churn;
  final double? longestIdleS;
  final int? runsBeforeAccept;

  ///Speech time / session time; null without audio.
  final double? talkRatio;
  final Map<String, double>? timePerPhaseS;
  final double? timeToFirstPassingRunS;
  final double? timeToFirstRunS;
  final double totalTimeS;

  Metrics({
    this.churn,
    this.longestIdleS,
    this.runsBeforeAccept,
    this.talkRatio,
    this.timePerPhaseS,
    this.timeToFirstPassingRunS,
    this.timeToFirstRunS,
    required this.totalTimeS,
  });

  factory Metrics.fromJson(Map<String, dynamic> json) => Metrics(
    churn: json["churn"]?.toDouble(),
    longestIdleS: json["longest_idle_s"]?.toDouble(),
    runsBeforeAccept: json["runs_before_accept"],
    talkRatio: json["talk_ratio"]?.toDouble(),
    timePerPhaseS: Map.from(json["time_per_phase_s"]!)
        .map((k, v) => MapEntry<String, double>(k, v?.toDouble())),
    timeToFirstPassingRunS: json["time_to_first_passing_run_s"]?.toDouble(),
    timeToFirstRunS: json["time_to_first_run_s"]?.toDouble(),
    totalTimeS: json["total_time_s"]?.toDouble(),
  );

  Map<String, dynamic> toJson() => {
    "churn": churn,
    "longest_idle_s": longestIdleS,
    "runs_before_accept": runsBeforeAccept,
    "talk_ratio": talkRatio,
    "time_per_phase_s": Map.from(timePerPhaseS!)
        .map((k, v) => MapEntry<String, dynamic>(k, v)),
    "time_to_first_passing_run_s": timeToFirstPassingRunS,
    "time_to_first_run_s": timeToFirstRunS,
    "total_time_s": totalTimeS,
  };
}

class Finding {
  final String detail;
  final double end;

  ///Cited event ids.
  final List<String> evidence;
  final double start;
  final String title;

  Finding({
    required this.detail,
    required this.end,
    required this.evidence,
    required this.start,
    required this.title,
  });

  factory Finding.fromJson(Map<String, dynamic> json) => Finding(
    detail: json["detail"],
    end: json["end"]?.toDouble(),
    evidence: List<String>.from(json["evidence"].map((x) => x)),
    start: json["start"]?.toDouble(),
    title: json["title"],
  );

  Map<String, dynamic> toJson() => {
    "detail": detail,
    "end": end,
    "evidence": List<dynamic>.from(evidence.map((x) => x)),
    "start": start,
    "title": title,
  };
}

class TimeSink {
  final Category category;
  final double end;

  ///Cited event ids.
  final List<String> evidence;
  final double start;
  final String suggestion;
  final double timeLostS;
  final String whatHappened;

  TimeSink({
    required this.category,
    required this.end,
    required this.evidence,
    required this.start,
    required this.suggestion,
    required this.timeLostS,
    required this.whatHappened,
  });

  factory TimeSink.fromJson(Map<String, dynamic> json) => TimeSink(
    category: categoryValues.map[json["category"]]!,
    end: json["end"]?.toDouble(),
    evidence: List<String>.from(json["evidence"].map((x) => x)),
    start: json["start"]?.toDouble(),
    suggestion: json["suggestion"],
    timeLostS: json["time_lost_s"]?.toDouble(),
    whatHappened: json["what_happened"],
  );

  Map<String, dynamic> toJson() => {
    "category": categoryValues.reverse[category],
    "end": end,
    "evidence": List<dynamic>.from(evidence.map((x) => x)),
    "start": start,
    "suggestion": suggestion,
    "time_lost_s": timeLostS,
    "what_happened": whatHappened,
  };
}

enum Category {
  ALGORITHM_CHOICE,
  COMMUNICATION,
  DEBUGGING,
  EDGE_CASES,
  IMPLEMENTATION,
  INPUT_PARSING,
  OUTPUT_FORMAT,
  SYNTAX_API_RECALL,
  UNDERSTANDING,
}

final categoryValues = EnumValues({
  "algorithm_choice": Category.ALGORITHM_CHOICE,
  "communication": Category.COMMUNICATION,
  "debugging": Category.DEBUGGING,
  "edge_cases": Category.EDGE_CASES,
  "implementation": Category.IMPLEMENTATION,
  "input_parsing": Category.INPUT_PARSING,
  "output_format": Category.OUTPUT_FORMAT,
  "syntax_api_recall": Category.SYNTAX_API_RECALL,
  "understanding": Category.UNDERSTANDING,
});

///Text frame sent by the engine.
///
///What the engine already holds: the highest seq / chunk index with no gaps below it.
///
///Origin and token failures close the socket with code 4403 instead of sending an error.
class ServerMessage {
  final Map<String, int>? lastChunk;

  ///0 when nothing has been received.
  final int? lastSeq;
  final String? sessionId;
  final ServerMessageType type;
  final ChunkRef? chunk;

  ///Every event with seq <= this is stored.
  final int? seq;
  final Code? code;
  final String? message;
  final bool? retryable;

  ServerMessage({
    this.lastChunk,
    this.lastSeq,
    this.sessionId,
    required this.type,
    this.chunk,
    this.seq,
    this.code,
    this.message,
    this.retryable,
  });

  factory ServerMessage.fromJson(Map<String, dynamic> json) => ServerMessage(
    lastChunk: Map.from(json["last_chunk"]!)
        .map((k, v) => MapEntry<String, int>(k, v)),
    lastSeq: json["last_seq"],
    sessionId: json["session_id"],
    type: serverMessageTypeValues.map[json["type"]]!,
    chunk: json["chunk"] == null ? null : ChunkRef.fromJson(json["chunk"]),
    seq: json["seq"],
    code: codeValues.map[json["code"]],
    message: json["message"],
    retryable: json["retryable"],
  );

  Map<String, dynamic> toJson() => {
    "last_chunk": Map.from(lastChunk!)
        .map((k, v) => MapEntry<String, dynamic>(k, v)),
    "last_seq": lastSeq,
    "session_id": sessionId,
    "type": serverMessageTypeValues.reverse[type],
    "chunk": chunk?.toJson(),
    "seq": seq,
    "code": codeValues.reverse[code],
    "message": message,
    "retryable": retryable,
  };
}

class ChunkRef {
  final int index;
  final Stream stream;

  ChunkRef({required this.index, required this.stream});

  factory ChunkRef.fromJson(Map<String, dynamic> json) =>
      ChunkRef(index: json["index"], stream: streamValues.map[json["stream"]]!);

  Map<String, dynamic> toJson() => {
    "index": index,
    "stream": streamValues.reverse[stream],
  };
}

enum Stream { AUDIO, VIDEO }

final streamValues = EnumValues({"audio": Stream.AUDIO, "video": Stream.VIDEO});

enum Code {
  BAD_MESSAGE,
  DISK_FULL,
  FRAME_TOO_LARGE,
  INTERNAL,
  RATE_LIMITED,
  SCHEMA_MISMATCH,
  SESSION_MISMATCH,
}

final codeValues = EnumValues({
  "bad_message": Code.BAD_MESSAGE,
  "disk_full": Code.DISK_FULL,
  "frame_too_large": Code.FRAME_TOO_LARGE,
  "internal": Code.INTERNAL,
  "rate_limited": Code.RATE_LIMITED,
  "schema_mismatch": Code.SCHEMA_MISMATCH,
  "session_mismatch": Code.SESSION_MISMATCH,
});

enum ServerMessageType { ACK, ERROR, PING, PONG, WELCOME }

final serverMessageTypeValues = EnumValues({
  "ack": ServerMessageType.ACK,
  "error": ServerMessageType.ERROR,
  "ping": ServerMessageType.PING,
  "pong": ServerMessageType.PONG,
  "welcome": ServerMessageType.WELCOME,
});

class EnumValues<T> {
  Map<String, T> map;
  late Map<T, String> reverseMap;

  EnumValues(this.map);

  Map<T, String> get reverse {
    reverseMap = map.map((k, v) => MapEntry(v, k));
    return reverseMap;
  }
}

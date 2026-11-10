# engine

Engine v0 (build-plan step 3) is a command-line tool that turns a session bundle into a segmented, measured timeline. The design is in `docs/design.md` (Component 2), and the decisions are in `docs/decisions/003-engine-v0.md`.

```
uv run interview-coach run ~/Downloads/session_<id>.zip     # import + process
uv run interview-coach show <session id>                    # facts, phases, metrics, warnings
uv run interview-coach process <session> --from signals     # re-run from a stage
uv run interview-coach process <session> --only transcribe  # or one stage
```

- **Data directory:** sessions go under `~/Library/Application Support/InterviewCoach/sessions/`. Override with `--data-dir` or `IC_DATA_DIR`.
- **Transcription:** needs the optional extra: run `make engine-transcribe-deps`. The first run downloads the `small.en` model (about 480 MB) into the Hugging Face cache. Without the extra, or with `--no-transcribe`, that stage is skipped and any existing transcript is kept.

## Stages

Every stage reads the bundle and earlier `derived/` files, writes only under `derived/`, and can be re-run alone.

| Stage | Writes |
| --- | --- |
| ingest | `ingest.json`, `audio.webm` (joined chunks) |
| normalize | `diffs.jsonl` (code_diff events), `normalize.json` |
| transcribe | `transcript.jsonl` (speech + marker events) |
| signals | `idle.jsonl` (idle events), `signals.json` |
| phases | `phases.json` |
| metrics | `metrics.json` (contract `Metrics`), `facts.json` |
| timeline | `timeline.json` |

Each run's status per stage is saved to `derived/pipeline.json`.

## Tests

```
uv run pytest                        # all stages, replaying fixtures/; recorded transcripts only
IC_WHISPER=1 uv run pytest -m whisper  # opt-in: real small.en on the fixture's silent audio
```

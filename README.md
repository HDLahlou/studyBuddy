# Interview Coach

Reviews recorded LeetCode-style practice sessions and returns timed, evidence-backed feedback. The design is in [`docs/design.md`](docs/design.md), and contract decisions are in [`docs/decisions/`](docs/decisions/).

## Layout

| Path | What |
| --- | --- |
| `schema/` | Shared contract (Python package `ic_schema`): events, manifest, WebSocket protocol, report, bundle I/O, replay harness. This is the source of truth. |
| `schema/generated/` | JSON Schema generated from the Pydantic models |
| `extension/` | Chrome MV3 extension (capture). Generated TS types are in `src/generated/`. |
| `engine/` | Python engine (prepare + `ai/`) |
| `gui/` | Flutter desktop app. Generated Dart types are in `lib/generated/`. |
| `fixtures/` | Sample session bundles for replay tests |

## Setup

You need `uv`, Node 20+, and optionally Dart or Flutter (for formatting and analyzing the generated Dart). You also need ffmpeg, but only to rebuild fixture audio.

```
make test                 # contract tests (pytest)
make lint typecheck       # ruff, mypy --strict
make schema               # regenerate JSON Schema, then TS and Dart types
make schema-check         # tsc + dart analyze on the generated types
make check                # all of the above, minus regeneration
```

If `dart` isn't on your PATH, pass it explicitly: `make schema DART=~/develop/flutter/bin/dart`.

## Changing the contract

1. Edit the Pydantic models in `schema/src/ic_schema/`.
2. Bump `SCHEMA_VERSION` in `version.py`: the major version for breaking changes, the minor version for additive ones.
3. Run `make schema`, update `fixtures/`, then run `make check`.
4. Record the decision in `docs/design.md` (Decisions) and in `docs/decisions/`.

Never hand-edit anything under a `generated/` folder. A test fails if `schema/generated/` drifts from the models.

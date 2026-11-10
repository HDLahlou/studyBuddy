# Interview Coach. See README.md and docs/design.md.
# Tools not on PATH can be overridden, e.g. `make schema DART=~/develop/flutter/bin/dart`.

UV   ?= uv
NPM  ?= npm
DART ?= dart

CODEGEN := schema/codegen

.PHONY: schema schema-json schema-ts schema-dart schema-check codegen-deps \
        test lint typecheck check fixtures-audio clean \
        extension-deps extension-build extension-test extension-typecheck \
        engine-test engine-transcribe-deps

## Regenerate JSON Schema, then TypeScript and Dart types from it.
schema: schema-json schema-ts schema-dart

schema-json:
	cd schema && $(UV) run python -m ic_schema.export

codegen-deps: $(CODEGEN)/node_modules/.package-lock.json

$(CODEGEN)/node_modules/.package-lock.json: $(CODEGEN)/package.json $(CODEGEN)/package-lock.json
	cd $(CODEGEN) && $(NPM) ci

schema-ts: codegen-deps
	cd $(CODEGEN) && $(NPM) run -s ts && $(NPM) run -s version

schema-dart: codegen-deps
	cd $(CODEGEN) && $(NPM) run -s dart
	@if command -v $(DART) >/dev/null 2>&1; then $(DART) format gui/lib/generated >/dev/null; \
	else echo "note: '$(DART)' not found, skipped dart format"; fi

## Compile-check the generated types (tsc; dart analyze if Dart is available).
schema-check: codegen-deps
	cd $(CODEGEN) && $(NPM) run -s check-ts
	@if command -v $(DART) >/dev/null 2>&1; then $(DART) analyze gui/lib/generated; \
	else echo "note: '$(DART)' not found, skipped dart analyze"; fi

## Extension tests run first: they write the zip that schema/tests/test_extension_bundle.py reads.
test: extension-test
	cd schema && $(UV) run pytest
	cd engine && $(UV) run pytest

engine-test:
	cd engine && $(UV) run pytest

## Install faster-whisper (heavy) for real transcription; the default tests don't need it.
engine-transcribe-deps:
	$(UV) sync --all-packages --all-extras --all-groups

extension-deps: extension/node_modules/.package-lock.json

extension/node_modules/.package-lock.json: extension/package.json extension/package-lock.json
	cd extension && $(NPM) ci

extension-build: extension-deps
	cd extension && $(NPM) run -s build

extension-test: extension-deps
	cd extension && $(NPM) test

extension-typecheck: extension-deps
	cd extension && $(NPM) run -s typecheck

lint:
	$(UV) run --directory schema ruff check src tests ../fixtures/tools
	$(UV) run --directory schema ruff format --check src tests ../fixtures/tools
	$(UV) run --directory engine ruff check src tests
	$(UV) run --directory engine ruff format --check src tests

typecheck: extension-typecheck
	cd schema && $(UV) run mypy src
	cd engine && $(UV) run mypy src

check: lint typecheck test schema-check extension-build

## Rebuild the silent audio chunks of fixtures/two_sum_basic (needs ffmpeg).
fixtures-audio:
	cd schema && $(UV) run python ../fixtures/tools/make_silent_audio.py ../fixtures/two_sum_basic

clean:
	rm -rf .venv schema/.pytest_cache schema/.mypy_cache .ruff_cache $(CODEGEN)/node_modules \
	       extension/node_modules extension/dist extension/test-output

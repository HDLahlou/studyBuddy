"""The extension's exported zip reads cleanly with the Python bundle reader.

The zip is produced by extension/test/fixture-replay.test.ts (run `make extension-test`, which
`make test` does first). It replays fixtures/two_sum_basic through the extension's session code
and exporter, so this test proves the TypeScript writer and the Python reader agree.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ic_schema.bundle import read_bundle

from .helpers import FIXTURES, REPO

ZIP = REPO / "extension" / "test-output" / "two_sum_basic.zip"


@pytest.fixture
def exported(tmp_path: Path) -> Path:
    if not ZIP.exists():
        pytest.skip(f"{ZIP.relative_to(REPO)} missing: run `make extension-test` first")
    with zipfile.ZipFile(ZIP) as zf:
        names = zf.namelist()
        assert names and all(n.startswith("session_fx_two_sum_basic/") for n in names)
        assert all(not n.startswith("/") and ".." not in n for n in names)
        zf.extractall(tmp_path)
    return tmp_path / "session_fx_two_sum_basic"


def test_extension_bundle_matches_fixture(exported: Path) -> None:
    mine = read_bundle(exported)
    fixture = read_bundle(FIXTURES / "two_sum_basic")
    assert mine.complete and not mine.gaps and mine.duplicates == 0 and not mine.conflicts
    assert not mine.torn_tail
    assert mine.events == fixture.events
    assert mine.manifest.model_dump(exclude={"user_inputs"}) == fixture.manifest.model_dump(
        exclude={"user_inputs"}
    )
    assert mine.media["audio"].join() == fixture.media["audio"].join()
    assert [r.model_dump() for r in mine.media["audio"].records] == [
        r.model_dump() for r in fixture.media["audio"].records
    ]

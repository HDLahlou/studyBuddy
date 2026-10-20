from __future__ import annotations

import pytest

from ic_schema.manifest import Manifest

from .helpers import make_manifest


@pytest.fixture
def manifest() -> Manifest:
    return make_manifest()

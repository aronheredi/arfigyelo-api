from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    """Parsed JSON fixture by file name, fresh on every call."""

    def _load_fixture(name: str) -> Any:
        with (FIXTURES_DIR / name).open(encoding="utf-8") as fh:
            return json.load(fh)

    return _load_fixture

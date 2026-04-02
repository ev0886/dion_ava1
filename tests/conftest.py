from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    base_dir = Path("tests") / "_tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = (base_dir / uuid.uuid4().hex).resolve()
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

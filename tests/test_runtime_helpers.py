from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path

from app.runtime import render_json, settings_from_args


def test_settings_from_args_returns_none_without_overrides() -> None:
    assert settings_from_args(Namespace()) is None


def test_settings_from_args_maps_common_runtime_overrides(tmp_path: Path) -> None:
    settings = settings_from_args(
        Namespace(
            data_dir=tmp_path,
            sqlite_filename="runtime.sqlite3",
            alembic_config_path=Path("alembic.ini"),
            host="0.0.0.0",
            port=9000,
        )
    )

    assert settings is not None
    assert settings.data_dir == tmp_path
    assert settings.sqlite_filename == "runtime.sqlite3"
    assert settings.alembic_config_path == Path("alembic.ini")
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9000


def test_render_json_serializes_paths_and_sorts_keys(tmp_path: Path) -> None:
    payload = {"path": tmp_path / "file.txt", "value": 1}

    rendered = render_json(payload)
    decoded = json.loads(rendered)

    assert '"path"' in rendered
    assert decoded["path"] == str(tmp_path / "file.txt")

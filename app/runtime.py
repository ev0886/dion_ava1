from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.config import AppSettings


def add_common_settings_arguments(parser: argparse.ArgumentParser, *, include_api: bool = False) -> None:
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--sqlite-filename", type=str, default=None)
    parser.add_argument("--alembic-config-path", type=Path, default=None)
    if include_api:
        parser.add_argument("--host", type=str, default=None)
        parser.add_argument("--port", type=int, default=None)


def settings_from_args(args: argparse.Namespace) -> AppSettings | None:
    settings_kwargs: dict[str, Any] = {}
    for arg_name, setting_name in (
        ("data_dir", "data_dir"),
        ("sqlite_filename", "sqlite_filename"),
        ("alembic_config_path", "alembic_config_path"),
        ("host", "api_host"),
        ("port", "api_port"),
    ):
        if hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                settings_kwargs[setting_name] = value

    if not settings_kwargs:
        return None
    return AppSettings(**settings_kwargs)


def render_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True)


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value

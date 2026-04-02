from __future__ import annotations

from pathlib import Path

from app.bootstrap import bootstrap
from app.config import AppSettings


def test_bootstrap_runs_with_temp_sqlite(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="bootstrap.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    result = bootstrap(settings)

    assert result.sqlite_path.exists()

from __future__ import annotations


def test_import_main_entrypoint() -> None:
    from app.main import main

    assert callable(main)

from __future__ import annotations

from app.bootstrap import bootstrap


def main() -> None:
    settings = bootstrap()
    print(f"{settings.app_name} backend foundation initialized")


if __name__ == "__main__":
    main()

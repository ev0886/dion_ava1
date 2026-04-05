# DION ABA1

ПО управления вендинг-аппаратом DION ABA1.

## Состав

- RFID/PIN авторизация
- выдача
- возврат
- пополнение
- инвентаризация
- журналы и аудит
- recovery after crash
- интеграция с барабаном, замками и RFID

## Полезные команды

```bash
python -m app.cli --help
python -m app.cli startup-check
python -m app.cli hardware-health
python -m app.cli recovery-scan
python -m pytest
```

## Документация

Документы проекта находятся в папке `docs/`.


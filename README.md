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

## Raspberry Pi OS deployment baseline

Production deployment is currently packaged only for:

- clean Raspberry Pi OS
- Raspberry Pi 5
- repo path `/opt/dion_ava1`
- systemd unit `dion-api.service`
- runtime env file `/etc/default/dion_ava1`

Fresh install on a new stand:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone <repo-url> dion_ava1
cd /opt/dion_ava1
sudo bash deploy/raspberry-pi/install.sh
sudoedit /etc/default/dion_ava1
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
sudo systemctl status dion-api.service --no-pager
```

Update an existing deployed machine after the repo is already updated in place:

```bash
cd /opt/dion_ava1
sudo bash deploy/raspberry-pi/update.sh
```

Important deployment notes:

- keep `/etc/default/dion_ava1` as the runtime source of truth
- install does not overwrite an existing `/etc/default/dion_ava1`
- update preserves `/etc/default/dion_ava1`
- drum and lock must use `/dev/serial/by-path/...`
- do not configure drum or lock as `ttyUSB0` or `ttyUSB1`
- on a cloned or newly wired stand, verify whether drum and lock paths must be swapped before production use

Deployment details and first-use checks are documented in:

- `docs/runtime.md`
- `docs/runtime-baseline-rpi.md`
- `docs/hardware-diagnostics.md`

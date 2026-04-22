# Stand Smoke Checklist

This checklist is for the current confirmed live stand baseline on Raspberry Pi.

## 1. API and service are up

```bash
sudo systemctl status dion-api.service --no-pager
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/readiness
cd /opt/dion_ava1 && .venv/bin/python -m app.cli startup-check
```

Expected:

- `systemctl status` shows `active (running)`
- `/health` returns `{"status":"ok"}`
- `/readiness` does not report `NOT_READY`
- `startup-check` exits with code `0`

## 2. Hardware health

```bash
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
ls -l /dev/serial/by-path
```

Expected:

- `hardware-health` exits with code `0`
- drum and lock transports are present in `/dev/serial/by-path`
- configured hardware uses `/dev/serial/by-path/...`, not `ttyUSB0` or `ttyUSB1`

## 3. Auth by RFID

Checks:

- Open `/ui/user?v=smoke1`
- Present a known active user RFID card
- Confirm the user screen resolves the card and allows the expected role flow
- Present a blocked or unauthorized card and confirm blocked-auth messaging is shown

## 4. Operator prepare, replenish, remove

Checks:

- Open `/ui/operator?v=smoke1`
- Authenticate with an operator/admin RFID card
- Run replenish prepare for a known slot and confirm quarter-positioning happens before confirm
- Confirm replenish on that slot
- Run remove prepare for a known slot and confirm quarter-positioning happens before confirm
- Confirm remove on that slot

Expected:

- no unexpected UI errors
- slot prepare completes before final confirm
- final replenish/remove action completes and inventory updates

## 5. User dispense

Checks:

- Open `/ui/user?v=smoke1`
- Authenticate with a known allowed user card
- Select a known in-stock item
- Complete one real dispense on hardware
- Confirm success screen is shown after dispense

Expected:

- real hardware dispense completes
- success screen appears
- no stuck loading state after dispense

## 6. Open-door safety

Checks:

- Start a known user dispense flow
- Trigger the door-open condition on the target lock
- Confirm the UI shows the expected open-door safety behavior/message
- Close the door and verify the system returns to a normal ready state

Optional API spot check for one controlled lock:

```bash
curl -fsS "http://127.0.0.1:8000/user/door-status?board_address=0&lock_number=1"
```

## 7. Quick UI cache-bust checks

Open both pages with an explicit version suffix after deploy or restart:

```text
http://stand-ip:8000/ui/operator?v=20260422a
http://stand-ip:8000/ui/user?v=20260422a
```

Checks:

- hard refresh each page once
- confirm the latest UI is loaded on the operator page
- confirm the latest UI is loaded on the user page
- if a stale page remains, close the browser tab or restart Chromium kiosk and reopen with a new `v=` value

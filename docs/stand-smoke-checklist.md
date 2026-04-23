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
grep -E 'DION_HARDWARE_PROVIDER|DION_HARDWARE_REAL_ENDPOINTS' /etc/default/dion_ava1
```

Expected:

- `hardware-health` exits with code `0`
- drum and lock transports are present in `/dev/serial/by-path`
- configured hardware uses `/dev/serial/by-path/...`, not `ttyUSB0` or `ttyUSB1`
- RFID path matches the connected reader

## 3. Admin web auth and exports

Checks:

- Open `/ui/admin?v=smoke1`
- Login with the current admin password
- On a fresh/reset stand, default credentials are `admin` / `dionava`
- Confirm the password change UI is visible
- Export operations CSV for a small date range
- Export balances CSV

Password reset over SSH if needed:

```bash
cd /opt/dion_ava1 && .venv/bin/python -m app.cli reset-admin-password
```

## 4. Auth by RFID

Checks:

- Open `/ui/user?v=smoke1`
- Present a known active user RFID card
- Confirm the user screen resolves the card and allows the expected role flow
- Present a known operator/admin RFID card and confirm the operator/admin role flow opens as expected
- Present a blocked or unauthorized card and confirm blocked-auth messaging is shown

## 5. Operator board and hardware-assisted flow

Checks:

- Open `/ui/operator?v=smoke1`
- Authenticate with an operator/admin RFID card
- Confirm the operator board loads with corrected sector/cell numbering
- Confirm logical quarter mapping by screen behavior: `1/4 -> POS 26`, `2/4 -> POS 18`, `3/4 -> POS 10`, `4/4 -> POS 2`
- Run replenish prepare for a known slot and confirm quarter-positioning happens before confirm
- Confirm the filled-cell hint appears for an already filled cell
- Confirm replenish on that slot
- Run remove prepare for a known slot and confirm quarter-positioning happens before confirm
- Confirm remove on that slot
- Leave the execution screen idle and confirm the 2-minute presence/timeout behavior

Expected:

- no unexpected UI errors
- slot prepare completes before final confirm
- final replenish/remove action completes and inventory updates

## 6. User dispense

Checks:

- Open `/ui/user?v=smoke1`
- Authenticate with a known allowed user card
- Select a known in-stock item
- Confirm the displayed logical cell/sector numbering is sane for the selected item
- Complete one real dispense on hardware
- Confirm success screen is shown after dispense

Expected:

- real hardware dispense completes
- success screen appears
- no stuck loading state after dispense

## 7. Open-door safety

Checks:

- Start a known user dispense flow
- Trigger the door-open condition on the target lock
- Confirm the UI shows the expected open-door safety behavior/message
- Close the door and verify the system returns to a normal ready state

Optional API spot check for one controlled lock:

```bash
curl -fsS "http://127.0.0.1:8000/user/door-status?board_address=0&lock_number=1"
```

## 8. Drum timeout / mechanical jam sanity

Checks:

- Review recent logs for drum timeout or move failures:

```bash
sudo journalctl -u dion-api.service -n 200 --no-pager | grep -Ei 'drum|timeout|hardware'
```

- If a timeout followed a failed move, inspect mechanics for a jam before retry loops.
- If mechanics are clear but the drum controller still times out, power-cycle the controller, restart the service, and rerun `hardware-health`.

## 9. Quick UI cache-bust checks

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

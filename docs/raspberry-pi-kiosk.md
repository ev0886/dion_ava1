# Raspberry Pi UI MVP Kiosk Setup

This repo includes a narrow Raspberry Pi OS desktop kiosk setup for the existing UI MVP page:

- UI URL: `http://127.0.0.1:8000/ui/mvp`
- Browser: Chromium-compatible kiosk launch
- Backend: preferred as a systemd system service
- Desktop autostart: `.desktop` entry that starts the browser after the local API is healthy

## Repo-managed assets

- `deploy/raspberry-pi/dion-api.service`
- `deploy/raspberry-pi/launch_ui_mvp_kiosk.sh`
- `deploy/raspberry-pi/dion-ui-mvp-kiosk.desktop`

## Recommended runtime shape

1. Keep the API managed by systemd.
2. Keep the browser launch in the Raspberry Pi desktop autostart layer.
3. Let the kiosk launcher wait for `http://127.0.0.1:8000/health` before opening Chromium.

That keeps backend logs in `journalctl`, keeps the kiosk launch easy to disable by removing one autostart file, and avoids mixing API lifetime management into the desktop session.

## Install on Raspberry Pi

These commands assume:

- repo path: `/opt/dion_ava1`
- Python environment: `/opt/dion_ava1/.venv`
- desktop user: `pi`

Mark the launcher executable:

```bash
sudo chmod +x /opt/dion_ava1/deploy/raspberry-pi/launch_ui_mvp_kiosk.sh
```

Install the API systemd unit:

```bash
sudo cp /opt/dion_ava1/deploy/raspberry-pi/dion-api.service /etc/systemd/system/dion-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now dion-api.service
```

If the Python binary is not `/opt/dion_ava1/.venv/bin/python`, override it in `/etc/default/dion_ava1`:

```bash
echo 'DION_PYTHON_BIN=/path/to/python' | sudo tee /etc/default/dion_ava1
sudo systemctl restart dion-api.service
```

Install the desktop autostart entry for the session user:

```bash
mkdir -p /home/pi/.config/autostart
cp /opt/dion_ava1/deploy/raspberry-pi/dion-ui-mvp-kiosk.desktop /home/pi/.config/autostart/dion-ui-mvp-kiosk.desktop
chmod 644 /home/pi/.config/autostart/dion-ui-mvp-kiosk.desktop
```

If the desktop session runs under another user, replace `/home/pi` with that user's home directory.

## Debugging

Check API status and logs:

```bash
systemctl status dion-api.service
journalctl -u dion-api.service -b
```

Check kiosk browser logs written by the launcher:

```bash
tail -n 200 ~/.local/state/dion_ava1/kiosk-browser.log
```

Run the kiosk launcher manually inside the desktop session:

```bash
/opt/dion_ava1/deploy/raspberry-pi/launch_ui_mvp_kiosk.sh
```

Disable kiosk autostart without touching the API service:

```bash
rm -f ~/.config/autostart/dion-ui-mvp-kiosk.desktop
```

Disable the API service:

```bash
sudo systemctl disable --now dion-api.service
```

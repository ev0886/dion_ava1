#!/bin/sh
set -eu

DION_UI_MVP_URL="${DION_UI_MVP_URL:-http://127.0.0.1:8000/ui/mvp}"
DION_API_HEALTH_URL="${DION_API_HEALTH_URL:-http://127.0.0.1:8000/health}"
DION_API_WAIT_TIMEOUT_SECONDS="${DION_API_WAIT_TIMEOUT_SECONDS:-90}"
DION_BROWSER_BIN="${DION_BROWSER_BIN:-}"
DION_BROWSER_PROFILE_DIR="${DION_BROWSER_PROFILE_DIR:-$HOME/.config/dion-kiosk-chromium}"
DION_KIOSK_LOG_DIR="${DION_KIOSK_LOG_DIR:-$HOME/.local/state/dion_ava1}"
DION_KIOSK_WINDOW_SIZE="${DION_KIOSK_WINDOW_SIZE:-1080,1920}"

mkdir -p "$DION_BROWSER_PROFILE_DIR" "$DION_KIOSK_LOG_DIR"

LOG_FILE="$DION_KIOSK_LOG_DIR/kiosk-browser.log"

find_browser() {
    if [ -n "$DION_BROWSER_BIN" ] && command -v "$DION_BROWSER_BIN" >/dev/null 2>&1; then
        printf '%s\n' "$DION_BROWSER_BIN"
        return 0
    fi

    for candidate in chromium-browser chromium google-chrome; do
        if command -v "$candidate" >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    printf '%s\n' "ERROR: no Chromium-compatible browser found." >&2
    return 1
}

wait_for_api() {
    python3 - "$DION_API_HEALTH_URL" "$DION_API_WAIT_TIMEOUT_SECONDS" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

health_url = sys.argv[1]
timeout_seconds = int(sys.argv[2])
deadline = time.monotonic() + timeout_seconds

while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(health_url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") == "ok":
            raise SystemExit(0)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        time.sleep(1)

print(f"ERROR: API health check did not become ready within {timeout_seconds} seconds: {health_url}", file=sys.stderr)
raise SystemExit(1)
PY
}

BROWSER_BIN="$(find_browser)"
wait_for_api

exec "$BROWSER_BIN" \
    --kiosk \
    --app="$DION_UI_MVP_URL" \
    --window-size="$DION_KIOSK_WINDOW_SIZE" \
    --start-fullscreen \
    --no-first-run \
    --no-default-browser-check \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate,MediaRouter,AutofillServerCommunication \
    --check-for-update-interval=31536000 \
    --overscroll-history-navigation=0 \
    --user-data-dir="$DION_BROWSER_PROFILE_DIR" \
    >>"$LOG_FILE" 2>&1

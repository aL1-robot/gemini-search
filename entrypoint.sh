#!/bin/bash
set -e

PROFILE=/data/profile
mkdir -p "$PROFILE"

# Stale locks after a power cut / hard stop stop Chromium from launching
rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonCookie "$PROFILE"/SingletonSocket

# Virtual screen + VNC + browser-based viewer (noVNC) so you can see the browser
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
sleep 1
fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 -quiet &
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

if [ "$MODE" = "login" ]; then
  echo "=== LOGIN MODE ==="
  echo "Open http://127.0.0.1:6080/vnc.html , click Connect, sign in to Google,"
  echo "open https://gemini.google.com/app to confirm it works, then CLOSE the browser window."
  CHROME=$(python -c "from playwright.sync_api import sync_playwright as s; p=s().start(); print(p.chromium.executable_path); p.stop()")
  # Plain Chromium with NO automation flags, so Google doesn't refuse the sign-in
  "$CHROME" --user-data-dir="$PROFILE" --no-sandbox --password-store=basic \
    --no-first-run --no-default-browser-check --window-size=1280,900 \
    "https://accounts.google.com/" || true
  echo "Browser closed. Login saved. Now run: docker compose up -d"
  exit 0
fi

exec uvicorn app:app --host 0.0.0.0 --port 8001
#!/bin/bash
# Installs a launchd job that runs the Gmail summary every day at 08:00.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
UV_BIN="$(command -v uv)"
LABEL="com.gmail.morning-summary"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ -z "$UV_BIN" ]; then
  echo "uv not found on PATH. Install it first: https://docs.astral.sh/uv/"
  exit 1
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$UV_BIN</string>
    <string>run</string>
    <string>gmail_summarizer.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>8</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$PROJECT_DIR/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$PROJECT_DIR/launchd.err.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. The summary will run daily at 08:00."
echo "Logs: $PROJECT_DIR/launchd.out.log / launchd.err.log"
echo "To uninstall: launchctl unload '$PLIST' && rm '$PLIST'"

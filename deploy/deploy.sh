#!/usr/bin/env bash
# Deploy fotobox from Mac to Raspberry Pi and restart the application.
# Usage: ./deploy/deploy.sh [--restart]

PI_USER="admin"
PI_HOST="fotobox.local"        # or 192.168.178.69
PI_DIR="/home/admin/fotobox"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

set -e

echo ">>> Syncing files to ${PI_USER}@${PI_HOST}:${PI_DIR} …"
# config/ is excluded: the configuration is managed on the device (admin UI)
# and must not be overwritten on every deploy. On first run the app creates
# default config files automatically.
# NOTE: assets/ IS mirrored (incl. --delete) – media files added only on the
# Pi will be removed. Keep all assets in the project on the Mac.
rsync -avz --delete \
  --exclude '.git' \
  --exclude '.DS_Store' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'fotobox.log*' \
  --exclude '*.log' \
  --exclude 'config/' \
  --exclude 'dist/' \
  --exclude 'build/' \
  --exclude '*.spec' \
  "${LOCAL_DIR}/" \
  "${PI_USER}@${PI_HOST}:${PI_DIR}/"

echo ">>> Sync complete."

if [[ "$1" == "--restart" ]]; then
  echo ">>> Restarting fotobox service on Pi…"
  # DISPLAY/XDG_RUNTIME_DIR: when started via SSH the desktop session
  # environment is missing – without XDG_RUNTIME_DIR the app cannot reach
  # PipeWire/PulseAudio and ALL audio stays silent (see FIX_AUDIO.md).
  ssh "${PI_USER}@${PI_HOST}" "
    pkill -f 'python.*main.py' 2>/dev/null || true
    sleep 1
    cd '${PI_DIR}'
    export DISPLAY=\${DISPLAY:-:0}
    export XDG_RUNTIME_DIR=\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}
    nohup python3 src/main.py > /tmp/fotobox.log 2>&1 &
    echo 'Fotobox started. Logs: /tmp/fotobox.log'
  "
else
  echo ">>> Done. Run with --restart to also restart the app on the Pi."
fi

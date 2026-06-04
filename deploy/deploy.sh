#!/usr/bin/env bash
# Deploy fotobox from Mac to Raspberry Pi and restart the application.
# Usage: ./deploy/deploy.sh [--restart]

PI_USER="admin"
PI_HOST="fotobox.local"        # or 192.168.178.69
PI_DIR="/home/admin/fotobox"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

set -e

echo ">>> Syncing files to ${PI_USER}@${PI_HOST}:${PI_DIR} …"
rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.log' \
  --exclude 'dist/' \
  --exclude 'build/' \
  --exclude '*.spec' \
  "${LOCAL_DIR}/" \
  "${PI_USER}@${PI_HOST}:${PI_DIR}/"

echo ">>> Sync complete."

if [[ "$1" == "--restart" ]]; then
  echo ">>> Restarting fotobox service on Pi…"
  ssh "${PI_USER}@${PI_HOST}" "
    pkill -f 'python.*main.py' 2>/dev/null || true
    sleep 1
    cd '${PI_DIR}'
    nohup python3 src/main.py > /tmp/fotobox.log 2>&1 &
    echo 'Fotobox started. Logs: /tmp/fotobox.log'
  "
else
  echo ">>> Done. Run with --restart to also restart the app on the Pi."
fi

#!/bin/bash
# Deploy a new version using "version folders + a `current` link".
#
# Usage:    deploy.sh <folder-with-the-new-version>
# Example:  deploy.sh /tmp/build-a1b2c3d
#
# Settings come from environment variables:
#   APP_DIR      - project root on the server (default /opt/my-service)
#   RESTART_CMD  - how to restart the service. Run through `bash -c`, so quotes and pipes work
#   CHECK_CMD    - how to tell the service works (exit code 0 = works). Also run through `bash -c`
#   KEEP         - how many versions to keep (default 5)
#   TRIES, PAUSE - how many times to check after a restart and the pause in seconds
#
# Exit codes: 0 deployed, 1 new version failed and was rolled back (or there was
# nothing to roll back to), 3 frozen by a FREEZE file, 4 the layout is not what
# this script expects, 5 another deploy is running.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/my-service}"
RESTART_CMD="${RESTART_CMD:-sudo systemctl restart my-service.service}"
CHECK_CMD="${CHECK_CMD:-curl --fail --silent --max-time 5 http://127.0.0.1:8080/health}"
KEEP="${KEEP:-5}"
TRIES="${TRIES:-6}"
PAUSE="${PAUSE:-5}"
SRC="${1:?give the folder with the new version}"

[ -d "$SRC" ] || { echo "Not a folder: $SRC" >&2; exit 4; }

# Emergency brake: while a FREEZE file is present, nothing is deployed.
if [ -e "$APP_DIR/FREEZE" ]; then
  echo "Deploy stopped: found $APP_DIR/FREEZE" >&2
  exit 3
fi

# `current` must be a link (or absent). A real folder there means the service
# was installed some other way; switching would silently do nothing useful.
if [ -e "$APP_DIR/current" ] && [ ! -L "$APP_DIR/current" ]; then
  echo "$APP_DIR/current is a real folder, not a link. Move it into releases/ by hand first." >&2
  exit 4
fi

mkdir -p "$APP_DIR/releases"

# One deploy at a time. `mkdir` either creates the lock or fails: no race.
lock="$APP_DIR/.deploy.lock"
if ! mkdir "$lock" 2>/dev/null; then
  echo "Another deploy is running (lock: $lock). If it crashed, remove the folder by hand." >&2
  exit 5
fi
trap 'rmdir "$lock" 2>/dev/null || true' EXIT

run() { bash -c "$1"; }
check() {
  local n
  for n in $(seq 1 "$TRIES"); do
    if run "$CHECK_CMD" >/dev/null 2>&1; then return 0; fi
    [ "$n" -lt "$TRIES" ] && sleep "$PAUSE"
  done
  return 1
}

previous="$(readlink "$APP_DIR/current" 2>/dev/null || true)"

# 1. The new version goes into a new folder. The running one is untouched.
#    Plain `mkdir` fails if the folder exists, so two deploys never share one.
release="$APP_DIR/releases/$(date -u +%Y-%m-%d-%H%M%S)"
mkdir "$release" 2>/dev/null || { release="$release-$$"; mkdir "$release"; }
cp -R "$SRC"/. "$release"/
chmod -R a-w "$release"            # a version is immutable: nothing to edit in it

# 2. The link switches to the new folder. `-n` keeps ln from descending into the old target.
ln -sfn "$release" "$APP_DIR/current"

# 3. Restart, then ask the service itself. The restart command's own message is not trusted.
#    If the restart returns an error, skip the check and go straight to rollback.
ok=0
if run "$RESTART_CMD"; then
  if check; then ok=1; fi
fi

# 4. Check failed: put the link back and remove the failed version, so that
#    failed attempts never push good versions out during cleanup.
if [ "$ok" -ne 1 ]; then
  echo "The new version did not pass the check." >&2
  if [ -n "$previous" ]; then
    ln -sfn "$previous" "$APP_DIR/current"
    echo "Link returned to $previous" >&2
    if run "$RESTART_CMD" && check; then
      echo "The previous version is running again." >&2
    else
      echo "The previous version did not come back up either: a human is needed." >&2
    fi
  else
    rm -f "$APP_DIR/current"
    echo "There is no previous version, nothing to roll back to." >&2
  fi
  chmod -R u+w "$release" && rm -rf "$release"
  exit 1
fi

# 5. Cleanup: keep the last KEEP versions. The current one is never removed.
total=$(find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
if [ "$total" -gt "$KEEP" ]; then
  find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d | sort | head -n "$((total - KEEP))" |
    while read -r old; do
      [ "$old" = "$release" ] && continue
      chmod -R u+w "$old" && rm -rf "$old"
    done
fi

echo "Deployed: $release"

#!/bin/bash
# Scenarios for templates/deploy.sh.
# Usage: tests/test_deploy.sh   (run from the harness-guide folder)
# Everything happens in a temp folder; the "service" is a file the commands write to.
set -u
DEPLOY="$(cd "$(dirname "$0")/.." && pwd)/templates/deploy.sh"
WORK="$(mktemp -d)"
trap 'chmod -R u+w "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
fail=0

ok()  { echo "ok    $1"; }
bad() { echo "FAIL  $1"; fail=1; }
is()  { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$3', got '$2')"; fi; }

build() { mkdir -p "$WORK/src/$1" && echo "$1" > "$WORK/src/$1/app.txt"; echo "$WORK/src/$1"; }
# The check passes only when the deployed app.txt holds a version that starts with "good".
deploy() {
  local app="$1" src="$2"; shift 2
  APP_DIR="$app" KEEP="${KEEP:-5}" TRIES=2 PAUSE=0 \
    RESTART_CMD="${RESTART_CMD:-true}" \
    CHECK_CMD="${CHECK_CMD:-grep -q '^good' '$app/current/app.txt'}" \
    bash "$DEPLOY" "$src" >"$WORK/out.txt" 2>&1
}
live() { cat "$1/current/app.txt" 2>/dev/null; }
count() { find "$1/releases" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' '; }

A="$WORK/app1"; mkdir -p "$A"
deploy "$A" "$(build good1)";            is "first deploy succeeds" "$?" 0
is "first version is live" "$(live "$A")" good1
[ -L "$A/current" ] && ok "current is a link" || bad "current is a link"
if echo x >> "$A/current/app.txt" 2>/dev/null; then bad "deployed version is read-only"; else ok "deployed version is read-only"; fi

sleep 1
deploy "$A" "$(build bad2)";             is "failed check gives exit 1" "$?" 1
is "rolled back to the previous version" "$(live "$A")" good1
is "failed version was removed" "$(count "$A")" 1

sleep 1
RESTART_CMD="false" deploy "$A" "$(build good3)"; is "failed restart gives exit 1" "$?" 1
is "rolled back after a failed restart" "$(live "$A")" good1

sleep 1
RESTART_CMD='sh -c "echo restarted > '"$WORK"'/restart.log"' deploy "$A" "$(build good4)"
is "restart command with quotes works" "$?" 0
is "restart command really ran" "$(cat "$WORK/restart.log" 2>/dev/null)" restarted
CHECK_CMD="cat '$A/current/app.txt' | grep -q good" deploy "$A" "$(build good5)" ; is "check command with a pipe works" "$?" 0

touch "$A/FREEZE"
deploy "$A" "$(build good6)";            is "FREEZE gives exit 3" "$?" 3
is "FREEZE left the live version alone" "$(live "$A")" good5
rm "$A/FREEZE"

B="$WORK/app2"; mkdir -p "$B"
deploy "$B" "$(build bad1)";             is "first deploy failing gives exit 1" "$?" 1
[ ! -e "$B/current" ] && ok "no dangling current after a failed first deploy" || bad "no dangling current after a failed first deploy"
is "nothing left in releases" "$(count "$B")" 0

C="$WORK/app3"; mkdir -p "$C/current" && echo old > "$C/current/app.txt"
deploy "$C" "$(build good7)";            is "real folder as current gives exit 4" "$?" 4
is "the real folder was not touched" "$(cat "$C/current/app.txt")" old

D="$WORK/app4"; mkdir -p "$D/.deploy.lock"
deploy "$D" "$(build good8)";            is "held lock gives exit 5" "$?" 5
rmdir "$D/.deploy.lock"

E="$WORK/app5"; mkdir -p "$E"
( deploy "$E" "$(build good9)" ) & ( deploy "$E" "$(build good10)" ) & wait
n=$(find "$E/releases" -name app.txt | wc -l | tr -d ' ')
dirs=$(count "$E")
is "two deploys in the same second do not share a folder" "$n" "$dirs"

F="$WORK/app6"; mkdir -p "$F"
KEEP=2 deploy "$F" "$(build good11)"; sleep 1
KEEP=2 deploy "$F" "$(build bad12)";  sleep 1
KEEP=2 deploy "$F" "$(build bad13)";  sleep 1
KEEP=2 deploy "$F" "$(build good14)"; sleep 1
is "failed versions do not push good ones out" "$(count "$F")" 2
KEEP=2 deploy "$F" "$(build good15)"
is "cleanup keeps exactly KEEP versions" "$(count "$F")" 2
is "newest version is live after cleanup" "$(live "$F")" good15

bash "$DEPLOY" >/dev/null 2>&1;          [ "$?" -ne 0 ] && ok "no argument is an error" || bad "no argument is an error"
APP_DIR="$WORK/app7" bash "$DEPLOY" "$WORK/nope" >/dev/null 2>&1; is "missing source folder gives exit 4" "$?" 4

exit "$fail"

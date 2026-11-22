#!/bin/bash
# Scenarios for templates/claude-hooks/guard-main.sh.
# Usage: tests/test_guard.sh   (run from the harness-guide folder)
# Builds throwaway repositories in a temp folder; touches nothing else.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/templates/claude-hooks/guard-main.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0

G() { git -c user.name=t -c user.email=t@example.invalid "$@"; }

# expect <code> <label> <dir> <command string as the agent would send it>
expect() {
  local want="$1" label="$2" dir="$3" cmd="$4" got
  ( cd "$dir" && CMD="$cmd" DIR="$dir" python3 -c '
import json, os
print(json.dumps({"tool_name": "Bash", "cwd": os.environ["DIR"], "tool_input": {"command": os.environ["CMD"]}}))' \
    | bash "$HOOK" >/dev/null 2>&1 )
  got=$?
  if [ "$got" -eq "$want" ]; then echo "ok    $label"; else echo "FAIL  $label (want $want, got $got)"; fail=1; fi
}
raw() {
  local want="$1" label="$2" dir="$3" payload="$4" got
  ( cd "$dir" && printf '%s' "$payload" | bash "$HOOK" >/dev/null 2>&1 ); got=$?
  if [ "$got" -eq "$want" ]; then echo "ok    $label"; else echo "FAIL  $label (want $want, got $got)"; fail=1; fi
}

EMPTY="$WORK/empty";  mkdir "$EMPTY"  && G -C "$EMPTY" init -q -b main
MAIN="$WORK/onmain";  mkdir "$MAIN"   && G -C "$MAIN" init -q -b main && G -C "$MAIN" commit -q --allow-empty -m init
TASK="$WORK/ontask";  mkdir "$TASK"   && G -C "$TASK" init -q -b main && G -C "$TASK" commit -q --allow-empty -m init && G -C "$TASK" checkout -q -b anna/1-x
DET="$WORK/detached"; mkdir "$DET"    && G -C "$DET" init -q -b main && G -C "$DET" commit -q --allow-empty -m init && G -C "$DET" checkout -q --detach
PLAIN="$WORK/plain";  mkdir "$PLAIN"

echo "-- must block (2)"
expect 2 "commit on main"                         "$MAIN" 'git commit -m x'
expect 2 "two spaces"                             "$MAIN" 'git  commit -m x'
expect 2 "git -C . commit"                        "$MAIN" 'git -C . commit -m x'
expect 2 "git -c k=v commit"                      "$MAIN" 'git -c user.name=a commit -m x'
expect 2 "git --no-pager commit"                  "$MAIN" 'git --no-pager commit -m x'
expect 2 "/usr/bin/git commit"                    "$MAIN" '/usr/bin/git commit -m x'
expect 2 "merge on main"                          "$MAIN" 'git merge feature'
expect 2 "cherry-pick on main"                    "$MAIN" 'git cherry-pick abc123'
expect 2 "revert on main"                         "$MAIN" 'git revert HEAD'
expect 2 "push on main, no refspec"               "$MAIN" 'git push'
expect 2 "push origin main"                       "$MAIN" 'git push origin main'
expect 2 "chain: add && commit"                   "$MAIN" 'git add . && git commit -m x'
expect 2 "newline chain"                          "$MAIN" $'git add .\ngit commit -m x'
expect 2 "from task branch: push HEAD:main"       "$TASK" 'git push origin HEAD:main'
expect 2 "from task branch: push x:refs/heads/main" "$TASK" 'git push origin anna/1-x:refs/heads/main'
expect 2 "from task branch: push +main"           "$TASK" 'git push origin +main'
expect 2 "from task branch: push --all"           "$TASK" 'git push --all'
expect 2 "from task branch: checkout main && commit" "$TASK" 'git checkout main && git commit -m x'
expect 2 "cd into repo on main && commit"         "$PLAIN" "cd $MAIN && git commit -m x"
expect 2 "git -C repo-on-main commit from elsewhere" "$PLAIN" "git -C $MAIN commit -m x"
raw    2 "input is not JSON"                      "$MAIN" 'garbage'
raw    2 "input is a JSON list"                   "$MAIN" '[1,2]'

echo "-- must allow (0)"
expect 0 "commit on task branch"                  "$TASK" 'git commit -m x'
expect 0 "push task branch"                       "$TASK" 'git push -u origin anna/1-x'
expect 0 "on main: checkout -b && commit"         "$MAIN" 'git checkout -b anna/2-y && git commit -m x'
expect 0 "on main: switch -c && commit"           "$MAIN" 'git switch -c anna/2-y && git commit -m x'
expect 0 "on main: push a task branch by name"    "$MAIN" 'git push origin anna/1-x'
expect 0 "on main: pull"                          "$MAIN" 'git pull --rebase origin main'
expect 0 "on main: status and log"                "$MAIN" 'git status && git log --oneline -3'
expect 0 "echo that mentions git commit"          "$MAIN" 'echo "how to git commit"'
expect 0 "log --grep mentions git push"           "$MAIN" 'git log --grep="git push"'
expect 0 "unrelated command"                      "$MAIN" 'ls -la'
expect 0 "first commit in an empty repository"    "$EMPTY" 'git commit -m init'
expect 0 "detached HEAD commit"                   "$DET" 'git commit -m x'
expect 0 "outside any repository"                 "$PLAIN" 'git commit -m x'
raw    0 "no command field"                       "$MAIN" '{"tool_name":"Bash"}'
raw    0 "command is null"                        "$MAIN" '{"tool_input":{"command":null}}'

echo "-- without python3: crude but closed"
NOPY="$WORK/nopy-bin"; mkdir "$NOPY"
for tool in bash git cat sh; do ln -s "$(command -v "$tool")" "$NOPY/$tool"; done
nopy() {
  local want="$1" label="$2" dir="$3" payload="$4" got
  ( cd "$dir" && printf '%s' "$payload" | PATH="$NOPY" bash "$HOOK" >/dev/null 2>&1 ); got=$?
  if [ "$got" -eq "$want" ]; then echo "ok    $label"; else echo "FAIL  $label (want $want, got $got)"; fail=1; fi
}
nopy 0 "no python3: ls is not blocked"            "$MAIN" '{"tool_input":{"command":"ls"}}'
nopy 2 "no python3: commit on main is blocked"    "$MAIN" '{"tool_input":{"command":"git commit -m x"}}'
nopy 0 "no python3: commit on task branch passes" "$TASK" '{"tool_input":{"command":"git commit -m x"}}'

exit "$fail"

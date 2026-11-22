#!/bin/bash
# Scenarios for templates/git-hooks/commit-msg and pre-push, run through real git.
# Usage: tests/test_git_hooks.sh   (run from the harness-guide folder)
set -u
SRC="$(cd "$(dirname "$0")/.." && pwd)/templates/git-hooks"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0
G() { git -c user.name=t -c user.email=t@example.invalid "$@"; }

[ -x "$SRC/commit-msg" ] && [ -x "$SRC/pre-push" ] && echo "ok    templates are executable" || { echo "FAIL  templates are executable"; fail=1; }

R="$WORK/repo"; REMOTE="$WORK/remote.git"
G init -q --bare -b main "$REMOTE"
mkdir "$R" && cd "$R" && G init -q -b main && G commit -q --allow-empty -m "chore: init (#1)"
G remote add origin "$REMOTE" && G push -q origin main        # first push happens before the hooks are on
mkdir .githooks && cp "$SRC"/* .githooks/ && G config core.hooksPath .githooks

commit() {  # commit <want: pass|reject> <label> <title>
  local want="$1" label="$2" got
  if G commit -q --allow-empty -m "$3" >/dev/null 2>&1; then got=pass; else got=reject; fi
  if [ "$got" = "$want" ]; then echo "ok    $label"; else echo "FAIL  $label (want $want, got $got)"; fail=1; fi
}
push() {
  local want="$1" label="$2" got; shift 2
  if G push -q "$@" >/dev/null 2>&1; then got=pass; else got=reject; fi
  if [ "$got" = "$want" ]; then echo "ok    $label"; else echo "FAIL  $label (want $want, got $got)"; fail=1; fi
}

G checkout -q -b anna/12-login
commit pass   "well-formed title with the branch number" "fix(auth): handle empty password (#12)"
commit pass   "title without a scope"                    "docs: describe login (#12)"
commit reject "no task number"                           "fix(auth): handle empty password"
commit reject "number of another task"                   "fix(auth): handle empty password (#13)"
commit reject "zero as a task number"                    "fix: wip (#0)"
commit reject "no type"                                  "handle empty password (#12)"
commit reject "unknown type"                             "wip: something (#12)"
commit reject "hand-written Merge title"                 "Merge whatever I like"
commit pass   "title git writes for a merge"             "Merge branch 'main' into anna/12-login"

G checkout -q -b 14-plain
commit reject "branch without an owner still checks the number" "fix: thing (#15)"
commit pass   "branch without an owner, right number"           "fix: thing (#14)"
G checkout -q -b team/anna/16-nested
commit reject "nested branch name still checks the number"      "fix: thing (#17)"

push pass   "push of a task branch"        origin team/anna/16-nested
push reject "push of HEAD into main"       origin HEAD:main
G checkout -q main && G merge -q --ff-only anna/12-login
push reject "push of main itself"          origin main
push reject "push --all"                   --all origin

exit "$fail"

#!/bin/bash
# Claude Code hook (PreToolUse event, Bash tool).
# Stops the agent from writing to main/master: commit, merge, cherry-pick,
# revert, am on that branch, and any push whose target is that branch.
#
# How it works: Claude Code passes the planned action as JSON on stdin.
# Exit code 2 blocks the action and shows stderr to the agent. Any other
# non-zero code does NOT block, so on its own failures this script exits 2:
# better to stop once too often than to let something through.
#
# What it does not catch: a git command hidden inside `bash -c "..."`, a
# script file, an alias, or a variable. It is a guard against a slip, not a
# security boundary. The real boundary is branch protection on the hosting site.
#
# Needs python3 to read the command properly. Without python3 it falls back to
# a plain text match: cruder, may block a harmless command that only mentions
# "git commit", but never lets a real one through unchecked.

input=$(cat)

if ! command -v python3 >/dev/null 2>&1; then
  case "$input" in
    *git*commit*|*git*push*|*git*merge*|*git*cherry-pick*|*git*revert*|*"git am"*) ;;
    *) exit 0 ;;
  esac
  branch=$(git symbolic-ref --short -q HEAD 2>/dev/null || true)
  if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    echo "guard-main: branch $branch is open and the command touches git history. python3 is missing, so the check is crude; create a task branch first." >&2
    exit 2
  fi
  exit 0
fi

read -r -d '' checker <<'PY'
import json, os, re, shlex, subprocess, sys

PROTECTED = {"main", "master"}
WRITES = {"commit", "merge", "cherry-pick", "revert", "am"}
# git options that take a separate value
VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"}
SEPARATORS = {"&&", "||", ";", "|", "&", "\n"}


def block(reason):
    print(reason, file=sys.stderr)
    print("Create a task branch first: git checkout -b <owner>/<number>-<slug>", file=sys.stderr)
    sys.exit(2)


def git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def current_branch(cwd):
    """Branch name, '' for a detached HEAD, None outside a repository or before the first commit."""
    if git(cwd, "rev-parse", "--git-dir") is None:
        return None
    if git(cwd, "rev-parse", "--verify", "-q", "HEAD") is None:
        return None  # no commits yet: the very first commit has to land somewhere
    return git(cwd, "symbolic-ref", "--short", "-q", "HEAD") or ""


def split_segments(command):
    # a newline separates commands just like ';'
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segment, segments = [], []
    for token in lexer:
        if token in SEPARATORS or set(token) <= set("&|;"):
            if segment:
                segments.append(segment)
            segment = []
        else:
            segment.append(token)
    if segment:
        segments.append(segment)
    return segments


def parse_git(tokens):
    """Returns (directory given with -C or None, subcommand, its arguments) or None if not git."""
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1  # VAR=value prefixes
    while i < len(tokens) and tokens[i] in {"command", "exec", "sudo", "env", "time", "nice"}:
        i += 1
    if i >= len(tokens) or os.path.basename(tokens[i]) != "git":
        return None
    i += 1
    directory = None
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] == "-C" and i + 1 < len(tokens):
            directory = tokens[i + 1]
        i += 2 if tokens[i] in VALUE_OPTS else 1
    if i >= len(tokens):
        return None
    return directory, tokens[i], tokens[i + 1:]


def push_targets(args):
    """Destination branch names named on the push command line."""
    positional = [a for a in args if not a.startswith("-")]
    targets = []
    for spec in positional[1:]:  # positional[0] is the remote
        dest = spec.lstrip("+").split(":")[-1]
        targets.append(dest.replace("refs/heads/", ""))
    return targets


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("guard-main: could not read the hook input, action stopped", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print("guard-main: unexpected hook input, action stopped", file=sys.stderr)
        sys.exit(2)
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or "git" not in command:
        sys.exit(0)

    cwd = data.get("cwd") or os.getcwd()
    try:
        segments = split_segments(command)
    except ValueError:
        # unbalanced quotes: cannot parse, fall back to a text match
        if re.search(r"\bgit\b.*\b(commit|push|merge|cherry-pick|revert|am)\b", command, re.S):
            if current_branch(cwd) in PROTECTED:
                block("guard-main: could not parse the command, and a protected branch is open.")
        sys.exit(0)

    switched = {}  # directory -> branch the command itself switched to earlier in the chain
    for tokens in segments:
        if tokens and tokens[0] == "cd" and len(tokens) > 1:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(tokens[1])))
            continue
        parsed = parse_git(tokens)
        if parsed is None:
            continue
        directory, sub, args = parsed
        where = os.path.normpath(os.path.join(cwd, directory)) if directory else cwd

        if sub in {"checkout", "switch"}:
            names = [a for a in args if not a.startswith("-")]
            if names:
                switched[where] = names[0]
            continue

        branch = switched.get(where)
        if branch is None:
            branch = current_branch(where)
        if branch is None:
            continue  # not a repository, or no commits yet

        if sub in WRITES and branch in PROTECTED:
            block(f"Branch {branch} is open. `git {sub}` straight into it is not allowed.")

        if sub == "push":
            if any(a in {"--all", "--mirror"} for a in args):
                block("`git push --all/--mirror` would also push the protected branch.")
            targets = push_targets(args)
            if not targets and branch in PROTECTED:
                block(f"Branch {branch} is open. Pushing it directly is not allowed.")
            for target in targets:
                if target in PROTECTED or (target == "HEAD" and branch in PROTECTED):
                    block(f"This push targets {target if target != 'HEAD' else branch}. Open a merge request instead.")
    sys.exit(0)


main()
PY

printf '%s' "$input" | python3 -c "$checker"
code=$?
# 0 = allow, 2 = block. Anything else means the checker itself crashed: block.
if [ "$code" -ne 0 ] && [ "$code" -ne 2 ]; then
  echo "guard-main: the checker failed (exit $code), action stopped" >&2
  exit 2
fi
exit "$code"

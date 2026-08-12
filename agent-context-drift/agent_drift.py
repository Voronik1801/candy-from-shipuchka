#!/usr/bin/env python3
"""Detect drift between agent instruction files and the actual repository.

An out-of-date README annoys a human — they notice the mismatch and go look for
themselves. An out-of-date CLAUDE.md changes what an AI agent *does*: it walks a
dead path with full confidence, reads last quarter's plan, and reproduces the
mess you asked it to clean up. So instruction files deserve to be checked like
code — deterministically, fast, with a number.

    agent-drift                      # JSON report for the whole repo
    agent-drift --explain            # same, human-readable
    agent-drift --summary            # one line, empty when nothing is wrong
    agent-drift --fail-over 40       # exit 1 if any file drifts past 40 (CI)
    agent-drift --file docs/AGENTS.md
    agent-drift --candidates         # TSV of every finding, for labelling

No LLM, no network, no writes to your repo — the report goes to stdout.
Python 3.9+, standard library only.

How it works: every path mentioned in an instruction file runs a funnel —
zone (code span / tree block / link) → is it even a path? → is it a template?
→ resolve against a cascade of bases. Filtering early is what keeps false
positives down; see README for the calibration story.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

__version__ = "0.1.0"

# Instruction files understood out of the box. Override with --name.
DEFAULT_NAMES = [
    "CLAUDE.md",                        # Claude Code
    "AGENTS.md",                        # open agent-instruction convention
    "GEMINI.md",                        # Gemini CLI
    ".cursorrules",                     # Cursor
    "copilot-instructions.md",          # GitHub Copilot (.github/)
]

# Skipped when discovering owners and when hunting undocumented directories.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox",
             ".pytest_cache", ".mypy_cache", ".next", "dist", "build", ".idea",
             ".playwright-mcp", ".remember"}
# ...but they still go into the "what exists" index: instruction files
# legitimately document hidden folders, and without this their contents
# would look missing.
INDEX_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv"}
# Frozen projects should not ring forever.
SKIP_PARTS = {"archive", "vendor", "third_party"}

KNOWN_EXTS = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".csv", ".txt",
              ".html", ".css", ".png", ".jpg", ".jpeg", ".svg", ".tsx", ".ts",
              ".js", ".jsx", ".sql", ".toml", ".ini", ".cfg", ".xml", ".rs",
              ".go", ".rb", ".java", ".kt", ".php", ".c", ".h", ".cpp", ".pdf"}

PLACEHOLDER_RE = [
    re.compile(r"\{[^}]*\}"),           # {date}, {name}, {slug}
    re.compile(r"<[^>]+>"),             # <name>
    re.compile(r"\bYYYY\b|\bMM\b|\bDD\b"),
    re.compile(r"\$\{?\w+\}?"),         # $VAR
    re.compile(r"\*"),                  # ACTIVE_*.md
    re.compile(r"\.\.\."),
]
# Placeholders people write without brackets: `YYYY-MM-DD_slug.md`.
# Word boundary here excludes "_" and "-" on purpose — they are separators.
WORD_PLACEHOLDER = re.compile(
    r"(?<![A-Za-z0-9])(slug|name|title|filename|topic|date)(?![A-Za-z0-9])", re.I)

CMD_START = re.compile(
    r"^(npm|npx|yarn|pnpm|bun|deno|python3?|pip3?|poetry|uv|bash|sh|zsh|make|"
    r"git|cd|ls|cat|echo|jq|curl|wget|docker|kubectl|terraform|cargo|go|mvn|"
    r"gradle|rm|cp|mv|mkdir|chmod|open|source|export|claude)\b")
URL_START = re.compile(r"^(https?://|mailto:|git@|ssh://|ftp://)")
BARE_DOMAIN = re.compile(
    r"^[\w-]+(\.[\w-]+)*\.(com|org|net|io|dev|ai|me|sh|ru|co|app)(/|$)", re.I)
SHOUTY = re.compile(r"^[A-Z][A-Z_/ ]{1,}$")     # CREATE, DROP/UPDATE, TEMP TABLE

DEPTH_LIMIT = 2      # architecture, not an inventory of every leaf folder
TREE_CHARS = ("├──", "└──", "│")

IGNORE_NAMES = [".drift-ignore", ".claude/claude-md-drift.ignore"]


# ── repository root ──────────────────────────────────────────────────────────

def repo_root(start: Path) -> Path:
    """Git root, falling back to cwd. Keeps the tool portable across repos."""
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=start, capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:
        pass
    return start


# ── ownership: which file answers for which subtree ──────────────────────────

def find_instruction_files(root: Path, names: list[str]) -> list[Path]:
    found = []
    for name in names:
        for p in root.rglob(name):
            parts = set(p.parts)
            if parts & SKIP_DIRS or parts & SKIP_PARTS:
                continue
            found.append(p)
    return sorted(set(found))


def scope_of(owner: Path, owners: list[Path]) -> tuple[Path, list[Path]]:
    """Owner's subtree minus the subtrees of nested owners.

    Without this a parent and its nested instruction file blame each other for
    the same folders, and both look rotten.
    """
    base = owner.parent
    nested = [o.parent for o in owners if o != owner and base in o.parents]
    return base, nested


def in_scope(path: Path, base: Path, nested: list[Path]) -> bool:
    if not (path == base or base in path.parents):
        return False
    return not any(path == n or n in path.parents for n in nested)


# ── zones: where candidates come from ────────────────────────────────────────

def split_fences(text: str):
    """Returns (prose_lines, fenced_blocks), both carrying line numbers."""
    lines = text.splitlines()
    prose, blocks, cur, start = [], [], None, 0
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            if cur is None:
                cur, start = [], i
            else:
                blocks.append((start, cur))
                cur = None
            continue
        (cur if cur is not None else prose).append((i, ln))
    if cur is not None:
        blocks.append((start, cur))
    return prose, blocks


def parse_tree_block(lines: list[tuple[int, str]]):
    """ASCII tree → full paths, using a stack keyed on indent column.

    The first line of the block is the tree's own root and must be dropped,
    otherwise every entry comes out as `myproject/src/` instead of `src/` and
    the whole block reads as broken.
    """
    out, stack = [], []
    for lineno, raw in lines:
        if not raw.strip():
            continue
        m = re.search(r"(├──|└──)\s*", raw)
        if not m:
            continue                                # root line or a comment
        depth = m.start() // 4
        name = raw[m.end():]
        name = re.split(r"\s*←|\s*#|\s{2,}", name)[0].strip().strip("`\"' ")
        if not name or name.startswith(("…", "...")):
            continue
        del stack[depth:]
        stack.append(name.rstrip("/"))
        out.append(("/".join(stack), lineno, "tree"))
    return out


def extract_candidates(text: str):
    """Only from marked-up zones. Prose is never scanned."""
    prose, blocks = split_fences(text)
    cands: list[tuple[str, int, str]] = []
    for lineno, ln in prose:
        for m in re.finditer(r"`([^`\n]{2,160})`", ln):
            cands.append((m.group(1), lineno, "code"))
        for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", ln):
            cands.append((m.group(1), lineno, "link"))
    for _, lines in blocks:
        if sum(1 for _, l in lines if any(c in l for c in TREE_CHARS)) >= 2:
            cands.extend(parse_tree_block(lines))
        # non-tree blocks are shell examples — skipped wholesale
    return cands


# ── "is this even a path?" ───────────────────────────────────────────────────

def is_path_like(s: str) -> tuple[bool, str]:
    s = s.strip().strip("`\"'’ ")
    if not s or len(s) < 3:
        return False, "too_short"
    if URL_START.match(s) or BARE_DOMAIN.match(s):
        return False, "url"
    if s.startswith("-"):
        return False, "cli_flag"
    if CMD_START.match(s):
        return False, "command"
    if SHOUTY.match(s):
        return False, "shouty"                      # CREATE, DROP/UPDATE
    if s.startswith("/") and not s.startswith(("/Users", "/home", "/opt",
                                               "/etc", "/var", "/usr", "/srv")):
        return False, "slash_command"               # /review — a command
    if " " in s and "/" not in s:
        return False, "phrase"
    if s.count(" ") >= 2:
        # "notes/1:1 with the team about health" describes contents, not a path
        return False, "phrase"
    if "/" not in s and os.path.splitext(s)[1].lower() not in KNOWN_EXTS:
        return False, "bare_word"                   # a skill name, a concept
    return True, ""


def is_template(s: str) -> bool:
    return any(rx.search(s) for rx in PLACEHOLDER_RE) or bool(WORD_PLACEHOLDER.search(s))


def template_to_glob(s: str) -> str:
    g = re.sub(r"\{[^}]*\}", "*", s)
    g = re.sub(r"<[^>]+>", "*", g)
    g = g.replace("YYYY", "[0-9][0-9][0-9][0-9]")
    g = g.replace("MM", "[0-9][0-9]").replace("DD", "[0-9][0-9]")
    g = WORD_PLACEHOLDER.sub("*", g)
    return re.sub(r"\*{3,}", "*", g).rstrip("/")


# ── resolution ───────────────────────────────────────────────────────────────

def clean(s: str) -> str:
    s = s.strip().strip("`\"'’ ")
    s = re.split(r"\s*←|\s+#|\s{2,}", s)[0].strip().rstrip("/")
    while s.startswith("./"):
        s = s[2:]
    return s


def ancestors(d: Path, root: Path):
    """Walk up to the repo root, never past it.

    When the instruction file sits at the root itself, `d` is already outside
    the repository — yielding it would resolve paths against the user's home
    directory and then crash on relative_to().
    """
    if d != root and root not in d.parents:
        return
    cur = d
    while True:
        yield cur
        if cur == root or cur.parent == cur:
            break
        cur = cur.parent


def build_fs_index(root: Path) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in INDEX_SKIP]
        rel = Path(dirpath).relative_to(root)
        for name in list(dirnames) + filenames:
            idx.setdefault(name, []).append(str(rel / name))
    return idx


def resolve(cand: str, owner_dir: Path, root: Path,
            fs_index: dict) -> tuple[str, str]:
    """→ (verdict, reason): ok | ambiguous | broken | template_unused | descriptive."""
    s = clean(cand)
    if not s:
        return "skip", "empty"

    # "scripts/setup.sh --force": check the first token, not the whole line
    if " " in s:
        head = s.split()[0]
        if "/" in head or os.path.splitext(head)[1]:
            s = head

    # A path written from the repo name down ("myrepo/docs") is stripped first,
    # templates included — otherwise `myrepo/src/**` matches no glob at all.
    root_named = False
    if s.startswith(root.name + "/"):
        tail = s[len(root.name) + 1:]
        if (root / tail).exists() or is_template(tail):
            s, root_named = tail, True

    if is_template(s):
        pat = template_to_glob(s)
        for base in (owner_dir, root):
            try:
                if any(base.glob(pat)):
                    return ("ambiguous" if root_named else "ok"), "template_matched"
            except (ValueError, OSError):
                pass
        parent = os.path.dirname(pat.replace("**", "").rstrip("/"))
        if parent and ((owner_dir / parent).exists() or (root / parent).exists()):
            return "template_unused", "dir_exists_no_files"
        return "template_unused", "no_match"

    if root_named:
        return "ambiguous", "root_named_prefix"

    if s.startswith("~"):
        p = Path(os.path.expanduser(s))
        return ("ok", "home") if p.exists() else ("external", "home_missing")
    if s.startswith("/"):
        # An absolute path outside the repo is usually somewhere else entirely:
        # a deploy target (`/opt/myservice`), a system config, another machine.
        # We cannot verify those and must not call them broken.
        if Path(s).exists():
            return "ok", "absolute"
        try:
            Path(s).relative_to(root)
        except ValueError:
            return "external", "outside_repo"
        return "broken", "absolute_missing"

    if (owner_dir / s).exists():
        return "ok", "owner_relative"

    if s.startswith(".."):
        p = (owner_dir / s).resolve()
        return ("ok", "explicit_parent") if p.exists() else ("broken", "parent_missing")

    for base in ancestors(owner_dir.parent, root):
        if (base / s).exists():
            rel = base.relative_to(root) if base != root else Path(".")
            return "ambiguous", f"resolved_at:{rel}"

    tail = os.path.basename(s)
    if tail in fs_index:
        return "ambiguous", "found_by_basename"

    # A tree leaf with no extension whose parent exists: trees list *topics*
    # under a folder ("notes/onboarding"), not necessarily files.
    parent = os.path.dirname(s)
    if parent and not os.path.splitext(tail)[1]:
        if any((b / parent).exists() for b in (owner_dir, root)):
            return "descriptive", "leaf_describes_content"

    # A lone filename found nowhere ("status.md" in "the agent keeps plan.md
    # and status.md") is a concept in an explanation, not an address.
    if "/" not in s:
        return "descriptive", "bare_name_concept"

    return "broken", "not_found"


# ── ignore rules ─────────────────────────────────────────────────────────────

def load_ignore(root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """`value` / `file::value` mute a finding; `skip: <glob>` drops a whole file."""
    rules: list[tuple[str, str]] = []
    skips: list[str] = []
    for name in IGNORE_NAMES:
        f = root / name
        if not f.exists():
            continue
        for ln in f.read_text(errors="ignore").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if ln.startswith("skip:"):
                skips.append(ln[5:].strip())
                continue
            scope, _, value = ln.rpartition("::")
            rules.append((scope or "*", value))
    return rules, skips


def ignored(rules, owner_rel: str, value: str) -> bool:
    for scope, pat in rules:
        if scope != "*" and not fnmatch.fnmatch(owner_rel, scope):
            continue
        if fnmatch.fnmatch(value, pat) or value == pat or \
           (pat.endswith("*") and value.startswith(pat.rstrip("*"))):
            return True
    return False


# ── secondary signals ────────────────────────────────────────────────────────

def load_gitignore(root: Path) -> list[str]:
    f = root / ".gitignore"
    if not f.exists():
        return []
    return [ln.strip().rstrip("/") for ln in f.read_text(errors="ignore").splitlines()
            if ln.strip() and not ln.startswith("#")]


def undocumented_dirs(base: Path, nested: list[Path], text: str,
                      gitignore: list[str], rules, owner_rel: str):
    """Directories the instructions never mention.

    Depth is capped on purpose: an instruction file describes architecture, it
    does not inventory every leaf. Empty folders are skipped — nothing to say.
    """
    out, considered = [], 0
    for d in sorted(base.rglob("*")):
        if not d.is_dir():
            continue
        rel = d.relative_to(base)
        if len(rel.parts) > DEPTH_LIMIT:
            continue
        if any(p in SKIP_DIRS or p in SKIP_PARTS or p.startswith(".") for p in rel.parts):
            continue
        if not in_scope(d, base, nested):
            continue
        if any(fnmatch.fnmatch(str(rel), g) or rel.parts[0] == g for g in gitignore):
            continue
        # A nested git repository is someone else's territory: instructions
        # describe it as a whole, not its innards.
        if any((base / Path(*rel.parts[:i + 1]) / ".git").exists()
               for i in range(len(rel.parts) - 1)):
            continue
        # Parent already documented → this is inventory, not architecture.
        if len(rel.parts) > 1 and (rel.parts[-2] in text or (d.parent / "README.md").exists()):
            continue
        entries = [x for x in d.iterdir() if not x.name.startswith(".")]
        if not entries:
            continue
        considered += 1
        if d.name in text or ignored(rules, owner_rel, str(rel)):
            continue
        significant = len(entries) >= 3 or any(x.suffix == ".md" for x in entries)
        out.append({"kind": "undocumented_dir", "value": str(rel) + "/",
                    "files": len(entries), "significant": bool(significant)})
    return out, considered


# Files that belong in a repository root by convention. Not clutter.
ROOT_STAPLES = {
    "readme.md", "readme.ru.md", "license", "license.md", "licence",
    "claude.md", "agents.md", "gemini.md", "contributing.md", "changelog.md",
    "code_of_conduct.md", "security.md", "makefile", "dockerfile",
    "pyproject.toml", "package.json", "cargo.toml", "go.mod", "setup.py",
    "requirements.txt", "pytest.ini", "tox.ini", "mkdocs.yml", "index.html",
}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".mov", ".mp4"}
CODE_EXT = {".py", ".sh", ".js", ".ts", ".rb", ".go", ".rs", ".sql"}
# "file 2.md" — what iCloud/Dropbox leave behind after a sync conflict
SYNC_DUP_RE = re.compile(r"^(?P<stem>.+) (?P<n>\d+)(?P<ext>\.[^.]+)$")


def classify_loose(p: Path) -> str:
    """What kind of stray file this is, so the report can suggest an action."""
    ext = p.suffix.lower()
    if ext in DOC_EXT:
        return "doc"        # → document it in the tree, or move it to docs/
    if ext in ASSET_EXT:
        return "asset"      # → assets/
    if ext in CODE_EXT:
        return "code"       # → scripts/ or src/
    return "unknown"


def loose_files(base: Path, text: str, gitignore: list[str], rules, owner_rel: str):
    """Files scattered in the root of a documented folder.

    Depth 0 on purpose: inside `output/` or `notes/` files are *supposed* to pile
    up, that is the job of those folders. The root is where a file lands when
    nobody decided where it belongs.
    """
    out = []
    for p in sorted(base.glob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.name.lower() in ROOT_STAPLES or p.name in text:
            continue
        if any(fnmatch.fnmatch(p.name, g) for g in gitignore):
            continue
        if ignored(rules, owner_rel, p.name):
            continue
        m = SYNC_DUP_RE.match(p.name)
        if m:
            twin = base / (m.group("stem") + m.group("ext"))
            if twin.exists() and twin.stat().st_size == p.stat().st_size:
                out.append({"kind": "loose_file", "value": p.name,
                            "bucket": "sync_duplicate", "reason": "copy of " + twin.name})
                continue
        out.append({"kind": "loose_file", "value": p.name,
                    "bucket": classify_loose(p), "reason": ""})
    return out


def duplicate_docs(base: Path, text: str):
    """Documents next door that duplicate the instruction file's job."""
    out = []
    for p in sorted(base.glob("*.md")):
        if p.name in text or p.name.lower() in {"readme.md", "claude.md", "agents.md"}:
            continue
        if re.match(r"^(STRUCTURE|NOTES|AUDIT|REVIEW|ARCHITECTURE|LAYOUT)", p.name, re.I):
            out.append(p.name)
    return out


def missing_skills(text: str, root: Path):
    """Skills the instructions point at that do not exist.

    Rename a skill and the instruction silently sends the agent nowhere. Only
    explicit `/name` mentions inside backticks count: a loose search for
    "/word" picks up commit types and model names and drowns the report.
    """
    names = set(re.findall(r"`/([a-z][a-z0-9:-]{2,40})`", text))
    homes = [root / ".claude" / "skills", Path.home() / ".claude" / "skills",
             root / ".cursor" / "rules"]
    builtin = {"loop", "schedule", "init", "help", "config", "clear", "run",
               "compact", "review", "test", "build", "deploy"}
    return [n for n in sorted(names)
            if ":" not in n and n not in builtin
            and not any((h / n / "SKILL.md").exists() or (h / f"{n}.md").exists()
                        for h in homes)]


def staleness(owner: Path, base: Path, nested: list[Path]):
    """Not "the file is old" but "the project moved on and the docs did not".

    A frozen project cannot go stale by definition: if nothing changed after
    the instructions were written, there is no lag.
    """
    mtime = owner.stat().st_mtime
    newest, churn = 0.0, 0
    for p in base.rglob("*"):
        if p.is_dir() or p == owner:
            continue
        rel = p.relative_to(base).parts
        if any(x in SKIP_DIRS or x.startswith(".") for x in rel):
            continue
        if not in_scope(p.parent, base, nested):
            continue
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > mtime:
            churn += 1
            newest = max(newest, m)
    return (round((newest - mtime) / 86400, 1) if newest else 0.0), churn


def score(counts, undoc, sig_dirs, lag, churn):
    """A ratio of what rotted, not a sum of errors: 40 paths and 7 aren't comparable."""
    def rate(a, b):
        return a / b if b else 0.0

    counts = {"verified": 0, "broken": 0, "ambiguous": 0, "templates": 0,
              "template_unused": 0, "skills_missing": 0, "skills_mentioned": 0,
              "loose": 0, "sync_duplicates": 0, "duplicate_docs": 0, **counts}
    verified = counts["verified"]
    # Broken paths count both as a share and in absolute terms: six dead
    # addresses are bad on their own, even in a file with fifty live ones.
    broken_rate = max(rate(counts["broken"], verified), min(counts["broken"] / 6, 1.0))
    n_undoc = sum(1 for u in undoc if u["significant"])
    undoc_rate = max(rate(n_undoc, sig_dirs), min(n_undoc / 8, 1.0))
    tmpl_rate = rate(counts["template_unused"], max(counts["templates"], 1))
    ambig_rate = rate(counts["ambiguous"], verified)
    stale = min(lag / 60, 1.0) * max(min(churn / 20, 1.0), 0.25) if churn else 0.0
    skill_rate = rate(counts["skills_missing"], max(counts["skills_mentioned"], 1))
    # Sync duplicates are pure garbage and count fully; other stray files are a
    # milder smell, so a handful of them cannot dominate the score.
    clutter = min((counts["sync_duplicates"] + 0.5 * (counts["loose"]
                   - counts["sync_duplicates"]) + counts["duplicate_docs"]) / 8, 1.0)

    drift = 100 * (0.34 * broken_rate + 0.21 * undoc_rate + 0.15 * stale
                   + 0.10 * tmpl_rate + 0.10 * skill_rate + 0.06 * clutter
                   + 0.04 * ambig_rate)
    if churn == 0:
        drift *= 0.5                      # frozen project stays quiet
    drift = round(min(drift, 100), 1)
    status = ("fresh" if drift < 20 else "drifting" if drift < 40
              else "stale" if drift < 60 else "broken")
    if churn == 0 and status in ("stale", "broken"):
        status = "drifting"
    return drift, status


# ── per-file analysis ────────────────────────────────────────────────────────

def analyze(owner: Path, owners: list[Path], root: Path, fs_index: dict,
            rules, gitignore: list[str]) -> dict:
    base, nested = scope_of(owner, owners)
    owner_rel = str(owner.relative_to(root))
    text = owner.read_text(errors="ignore")

    findings: list[dict] = []
    counts = {"candidates": 0, "verified": 0, "ok": 0, "broken": 0, "ambiguous": 0,
              "templates": 0, "template_unused": 0, "descriptive": 0,
              "external": 0, "not_a_path": 0, "ignored": 0,
              "loose": 0, "sync_duplicates": 0, "duplicate_docs": 0,
              "skills_mentioned": 0, "skills_missing": 0}

    seen = set()
    for raw, lineno, zone in extract_candidates(text):
        counts["candidates"] += 1
        ok, _why = is_path_like(raw)
        if not ok:
            counts["not_a_path"] += 1
            continue
        value = clean(raw)
        if (value, zone) in seen:
            continue
        seen.add((value, zone))
        if ignored(rules, owner_rel, value):
            counts["ignored"] += 1
            continue

        verdict, reason = resolve(raw, base, root, fs_index)
        if verdict == "skip":
            continue
        if verdict.startswith("template"):
            counts["templates"] += 1
        counts["verified"] += 1

        if verdict == "ok":
            counts["ok"] += 1
        elif verdict == "descriptive":
            counts["descriptive"] += 1
        elif verdict == "external":
            counts["external"] += 1
            findings.append({"kind": "external_ref", "value": value,
                             "line": lineno, "zone": zone, "reason": reason})
        elif verdict == "ambiguous":
            counts["ambiguous"] += 1
            findings.append({"kind": "ambiguous_ref", "value": value,
                             "line": lineno, "zone": zone, "reason": reason})
        elif verdict == "template_unused":
            counts["template_unused"] += 1
            findings.append({"kind": "template_unused", "value": value,
                             "line": lineno, "zone": zone, "reason": reason})
        else:
            counts["broken"] += 1
            findings.append({"kind": "broken_path", "value": value,
                             "line": lineno, "zone": zone, "reason": reason})

    undoc, sig_dirs = undocumented_dirs(base, nested, text, gitignore, rules, owner_rel)
    findings.extend(undoc)

    loose = loose_files(base, text, gitignore, rules, owner_rel)
    findings.extend(loose)

    dups = duplicate_docs(base, text)
    findings.extend({"kind": "duplicate_doc", "value": d} for d in dups)

    mentioned = set(re.findall(r"`/([a-z][a-z0-9:-]{2,40})`", text))
    miss = missing_skills(text, root)
    findings.extend({"kind": "missing_skill", "value": "/" + m} for m in miss)

    lag, churn = staleness(owner, base, nested)

    counts["undocumented"] = len(undoc)
    counts["dirs_considered"] = sig_dirs
    counts["loose"] = len(loose)
    counts["sync_duplicates"] = sum(1 for f in loose if f["bucket"] == "sync_duplicate")
    counts["duplicate_docs"] = len(dups)
    counts["skills_mentioned"] = len(mentioned)
    counts["skills_missing"] = len(miss)

    drift, status = score(counts, undoc, max(sig_dirs, 1), lag, churn)
    return {
        "path": owner_rel, "drift": drift, "status": status,
        "mtime": datetime.fromtimestamp(owner.stat().st_mtime).strftime("%Y-%m-%d"),
        "lag_days": lag, "churn": churn, "counts": counts, "findings": findings,
    }


# ── renderers ────────────────────────────────────────────────────────────────

LABELS = [("broken_path", "BROKEN"), ("undocumented_dir", "undocumented"),
          ("missing_skill", "no such skill"),
          ("loose_file", "loose in the root"),
          ("duplicate_doc", "duplicates the instruction file"),
          ("template_unused", "template matches nothing"),
          ("ambiguous_ref", "ambiguous"),
          ("external_ref", "outside this repo (unverifiable)")]


def render_explain(reports, skipped, root):
    for r in reports:
        c = r["counts"]
        print(f"\n{'-' * 72}\n{r['path']}   drift {r['drift']} [{r['status']}]"
              f"   lag {r['lag_days']}d · {r['churn']} changes since")
        print(f"  candidates {c['candidates']} · not paths {c['not_a_path']} · "
              f"checked {c['verified']} · ok {c['ok']} · broken {c['broken']} · "
              f"ambiguous {c['ambiguous']} · muted {c['ignored']}")
        for kind, label in LABELS:
            items = [f for f in r["findings"] if f["kind"] == kind]
            if not items:
                continue
            print(f"    {label}:")
            for f in items[:12]:
                loc = f"line {f['line']:>4}" if "line" in f else "         "
                tail = f.get("reason") or f.get("bucket") or ""
                extra = f"   [{tail}]" if tail else ""
                print(f"      {loc}  {f['value']}{extra}")
            if len(items) > 12:
                print(f"      ... {len(items) - 12} more")
    if skipped:
        print(f"\n{'-' * 72}\nnot checked (skip rules): "
              + ", ".join(str(p.relative_to(root)) for p in skipped))


def render_summary(reports):
    """One line for a hook. Silent unless it is genuinely worth interrupting."""
    bad = sorted([r for r in reports if r["drift"] >= 40], key=lambda r: -r["drift"])
    if not bad or (len(bad) < 2 and bad[0]["drift"] < 60):
        return
    names = ", ".join(f"{Path(r['path']).parent.name or 'root'} {int(r['drift'])}"
                      for r in bad[:3])
    fp = hashlib.sha1("|".join(f"{r['path']}:{r['status']}" for r in bad)
                      .encode()).hexdigest()[:12]
    noun = "file has" if len(bad) == 1 else "files have"
    print(f"{fp}\t{len(bad)} instruction {noun} drifted from the tree ({names})")


def render_candidates(reports):
    print("file\tline\tzone\tvalue\tverdict\treason")
    for r in reports:
        for f in r["findings"]:
            print(f"{r['path']}\t{f.get('line', '')}\t{f.get('zone', '')}\t"
                  f"{f['value']}\t{f['kind']}\t{f.get('reason', '')}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agent-drift", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="repository root (default: git root)")
    ap.add_argument("--name", action="append", default=None,
                    help=f"instruction file name; repeatable. "
                         f"Default: {', '.join(DEFAULT_NAMES)}")
    ap.add_argument("--file", default=None, help="check a single instruction file")
    ap.add_argument("--explain", action="store_true", help="human-readable report")
    ap.add_argument("--summary", action="store_true", help="one line, empty when clean")
    ap.add_argument("--candidates", action="store_true", help="TSV of all findings")
    ap.add_argument("--fail-over", type=float, default=None, metavar="N",
                    help="exit 1 if any file drifts past N (for CI)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root(Path.cwd())
    names = args.name or DEFAULT_NAMES
    owners_all = find_instruction_files(root, names)

    rules, skips = load_ignore(root)
    skipped = [o for o in owners_all
               if any(fnmatch.fnmatch(str(o.relative_to(root)), g) for g in skips)]
    owners = [o for o in owners_all if o not in skipped]

    if args.file:
        target = Path(args.file).resolve()
        owners = [o for o in owners if o == target] or [target]
        if not target.exists():
            sys.exit(f"no such file: {target}")

    fs_index = build_fs_index(root)
    gitignore = load_gitignore(root)
    reports = [analyze(o, owners_all, root, fs_index, rules, gitignore) for o in owners]
    reports.sort(key=lambda r: -r["drift"])

    if args.candidates:
        render_candidates(reports)
    elif args.summary:
        render_summary(reports)
    elif args.explain:
        render_explain(reports, skipped, root)
    else:
        print(json.dumps({
            "schema": 1, "version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "root": str(root),
            "skipped": [str(p.relative_to(root)) for p in skipped],
            "files": reports,
        }, ensure_ascii=False, indent=1))

    if args.fail_over is not None:
        worst = max((r["drift"] for r in reports), default=0)
        if worst > args.fail_over:
            print(f"drift {worst} exceeds threshold {args.fail_over}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

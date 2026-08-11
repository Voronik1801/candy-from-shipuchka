#!/usr/bin/env python3
"""The dice for creative-wander: random fragments out of your own archive.

The randomness is external to the model on purpose. Ask an LLM to "pick
something at random" and it picks something thematically related — coherence is
its whole job, and here we need the opposite. The OS random number generator
does not know what the files are about, so it will happily drop oncology next
to radishes, and that collision is where an idea comes from.

Probability is skewed towards what you have not opened in a long time. A file
you touched yesterday is already in your head — the idea in it has been had.

    python3 wander.py                    # 5 fragments, 40 lines each
    python3 wander.py 8 60               # 8 fragments, 60 lines each
    python3 wander.py 5 40 --seed 42     # reproducible run
    python3 wander.py --root ~/notes     # any directory; default: git root
    python3 wander.py --exclude work     # steer away from a heavy area
    python3 wander.py --max-per-area 1   # maximum spread

Point it at anything textual: a notes vault, a repository, a folder of drafts.
"""
import os
import random
import subprocess
import sys
import time
from pathlib import Path

def _default_root() -> Path:
    """Git root, then WANDER_ROOT, then the current directory."""
    env = os.environ.get("WANDER_ROOT")
    if env:
        return Path(env).expanduser()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


ROOT = _default_root()

# Everything readable is in play. A config file can spark an idea just as
# well as an essay — sometimes better, because nobody expects it to.
EXTENSIONS = {
    ".md", ".txt", ".py", ".json", ".yml", ".yaml", ".sh",
    ".html", ".css", ".js", ".ts", ".toml", ".cfg", ".ini", ".sql",
}

# Not an ideological filter, a physical one: nothing to pull out of these.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    "site-packages", ".next", "dist", "build", ".playwright-mcp", ".DS_Store",
    ".ruff_cache", ".mypy_cache", "coverage", ".cache",
}

MIN_BYTES = 500
MAX_BYTES = 400_000


def git_touch_dates():
    """Last-commit date per file, in a single pass over history.

    Needed because mtime lies: after a clone or a bulk copy half the archive
    shares one date and "forgottenness" cannot be measured from it. Git history
    remembers when a file was actually touched.

    Files of nested repositories (gitignored here) fall back to mtime.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--format=%ct", "--name-only", "--no-renames"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}

    dates = {}
    stamp = None
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isdigit() and len(line) == 10:
            stamp = int(line)
        elif stamp is not None:
            dates.setdefault(line, stamp)   # first hit = most recent commit
    return dates


def collect():
    """Every readable file under root, with its age in days."""
    now = time.time()
    git_dates = git_touch_dates()
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".venv")]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if not (MIN_BYTES <= stat.st_size <= MAX_BYTES):
                continue
            try:
                rel = str(path.relative_to(ROOT))
            except ValueError:
                rel = None
            touched = git_dates.get(rel, stat.st_mtime) if rel else stat.st_mtime
            found.append((path, (now - touched) / 86400))
    return found


def area_of(path):
    """The area a file belongs to: first two path components."""
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return str(path.parent)
    parts = rel.parts
    if len(parts) >= 3:
        return "/".join(parts[:2])
    return parts[0] if parts else "."


def pick(files, n, rng, max_per_area=2, exclude=()):
    """Pick with a bias towards the forgotten and a per-area quota.

    The bias: files are sorted oldest-first and the index is drawn as r**2 —
    squaring pushes the draw towards the front of the list. Recent files stay
    possible, just less likely.

    The quota: any real archive is lopsided. One project can easily hold a
    third of all files, and without a cap every third roll lands there — you
    get ten ideas about the same corner of your life. No more than
    max_per_area fragments from one area.
    """
    files = [(p, age) for p, age in files
             if not any(ex.lower() in area_of(p).lower() for ex in exclude)]
    files.sort(key=lambda item: -item[1])
    total = len(files)
    if not total:
        return []

    chosen = []
    seen = set()
    per_area = {}
    attempts = 0
    # first pass honours the quota; if it cannot fill n, top up without it
    while len(chosen) < min(n, total) and attempts < n * 120:
        attempts += 1
        idx = min(int(total * (rng.random() ** 2)), total - 1)
        if idx in seen:
            continue
        path, age = files[idx]
        area = area_of(path)
        if per_area.get(area, 0) >= max_per_area:
            continue
        seen.add(idx)
        per_area[area] = per_area.get(area, 0) + 1
        chosen.append((path, age))
    return chosen


def fragment(path, lines_wanted, rng):
    """A random slice from the middle of a file.

    A fragment, not the whole file: a torn-out piece gives more distance and
    less temptation to summarise the source instead of colliding it with
    something far away.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    if len(lines) <= lines_wanted:
        return "\n".join(lines)
    start = rng.randint(0, len(lines) - lines_wanted)
    return "\n".join(lines[start:start + lines_wanted])


def main():
    flags = {"--seed", "--exclude", "--max-per-area"}
    args, skip = [], False
    for i, a in enumerate(sys.argv[1:], start=1):
        if skip:
            skip = False
            continue
        if a in flags:
            skip = True
            continue
        if not a.startswith("--"):
            args.append(a)

    args = [a for a in args if a.isdigit()]
    n = int(args[0]) if args else 5
    lines_wanted = int(args[1]) if len(args) > 1 else 40

    seed = None
    exclude = ()
    max_per_area = 2
    for i, arg in enumerate(sys.argv):
        if arg == "--root" and i + 1 < len(sys.argv):
            globals()["ROOT"] = Path(sys.argv[i + 1]).expanduser().resolve()
        elif arg == "--seed" and i + 1 < len(sys.argv):
            seed = int(sys.argv[i + 1])
        elif arg == "--exclude" and i + 1 < len(sys.argv):
            exclude = tuple(x.strip() for x in sys.argv[i + 1].split(",") if x.strip())
        elif arg == "--max-per-area" and i + 1 < len(sys.argv):
            max_per_area = int(sys.argv[i + 1])
    rng = random.Random(seed)

    if not ROOT.exists():
        sys.exit(f"No such directory: {ROOT}")

    files = collect()
    if not files:
        sys.exit(f"No readable files under {ROOT}")

    picked = pick(files, n, rng, max_per_area=max_per_area, exclude=exclude)

    print(f"# Wander over {ROOT.name} — {len(picked)} fragments out of {len(files)} files")
    if seed is not None:
        print(f"\nseed: {seed}")
    print()

    for i, (path, age_days) in enumerate(picked, 1):
        text = fragment(path, lines_wanted, rng)
        if text is None:
            continue
        rel = path.relative_to(ROOT) if ROOT in path.parents else path
        print(f"## Fragment {i}")
        print(f"**Source:** `{rel}` · untouched for {int(age_days)}d")
        print()
        print("```")
        print(text)
        print("```")
        print()


if __name__ == "__main__":
    main()

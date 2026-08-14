#!/usr/bin/env python3
"""The corpus of named false positives.

Every bug report in this repository ends by naming one thing the tool must
never claim again — *locally excluded directory reported as undocumented*,
*plugin-installed skill reported as missing*. Those names are the asset. This
module keeps them in one enumerable place, so the honest answer to "why should
I trust this on my repo" is a list rather than a promise.

Each case is a directory under `fixtures/false-positives/`:

    case.json   what the tool must not say, and what it must still catch
    tree/       the repository to build, copied verbatim

`case.json` fields:

    claim        the false positive, named the way the bug report named it
    why          why this class is frequent, not incidental
    args         extra CLI flags the case needs
    git          build a git repository (needed for exclude files, blame)
    gitignore    lines written to `.gitignore`
    git_exclude  lines written to `.git/info/exclude`
    absent       findings that must NOT appear
    present      findings that MUST appear

`present` is what stops a case from passing for the wrong reason. Silence is
easy to buy by disabling a signal, and a corpus that only checks for silence
would applaud that. Each case therefore also names a real defect the same run
has to keep catching.

    python3 tests/corpus.py        # print the pinned claims
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "false-positives"


def load_cases() -> list[dict]:
    out = []
    for d in sorted(CORPUS_DIR.iterdir()):
        if not d.is_dir():
            continue
        case = json.loads((d / "case.json").read_text())
        case["slug"] = d.name
        case["dir"] = d
        out.append(case)
    return out


def build(case: dict, dest: Path) -> Path:
    """Materialise a case's repository at `dest`."""
    shutil.copytree(case["dir"] / "tree", dest, dirs_exist_ok=True)
    if case.get("gitignore"):
        (dest / ".gitignore").write_text("\n".join(case["gitignore"]) + "\n")
    if case.get("git"):
        subprocess.run(["git", "init", "-q", "."], cwd=dest, check=True,
                       capture_output=True)
        if case.get("git_exclude"):
            (dest / ".git" / "info" / "exclude").write_text(
                "\n".join(case["git_exclude"]) + "\n")
    return dest


def findings(root: Path, args: list[str], script: Path) -> list[dict]:
    out = subprocess.run([sys.executable, str(script), "--root", str(root), *args],
                         capture_output=True, text=True, check=True)
    return [f for file in json.loads(out.stdout)["files"] for f in file["findings"]]


def main() -> None:
    cases = load_cases()
    print(f"{len(cases)} false positives pinned:\n")
    for c in cases:
        print(f"  {c['slug']}")
        print(f"      must not say: {c['claim']}")
        if c.get("present"):
            kinds = ", ".join(sorted({p["kind"] for p in c["present"]}))
            print(f"      still catches: {kinds}")
        print()


if __name__ == "__main__":
    main()

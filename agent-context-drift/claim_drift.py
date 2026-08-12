#!/usr/bin/env python3
"""Claim drift: paths are not the only thing that rots.

The path checker asks "does this file still exist?". It cannot ask anything
about a sentence like *"median reach is 950"* — that claim has no address, so
it goes stale in silence while the agent keeps building on it.

This module checks claims instead, using a lightweight markup the instruction
file opts into:

    Median reach is 950 [source: tools/analytics/]
    Goodhart's law came out of British statistics [?]

`[источник: …]` works as an alias for `[source: …]`, for Russian-language
instruction files.

Four checks, from precise to noisy:

  broken_source    `[source: path]` points at nothing — same class as a dead link
  stale_unknown    a `[?]` has been sitting there longer than the TTL
  unmarked_claim   a measured number carrying no marker at all
  no_stake_level   a project that never declared how much its claims matter

**Stake level** decides how strict the file is. It is read from a
`Stake level: T{0,1,2}` line in the file header (`Уровень ставки:` also works),
otherwise inherited from the nearest parent instruction file, otherwise T1.

  T0  drafts, brainstorms — claims are not checked at all
  T1  working documents — the default
  T2  anything leaving the building: clients, money, publications

The point is not to decorate every number with a marker. It is to make the
difference between *checked* and *assumed* visible, so a reader can tell them
apart without re-deriving the whole file.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ── markup ───────────────────────────────────────────────────────────────────

SOURCE_RE = re.compile(r"\[(?:source|источник):\s*([^\]]+)\]", re.I)
UNKNOWN_RE = re.compile(r"\[\?\]")
STAKE_RE = re.compile(r"(?:stake level|уровень ставки):\s*\**\s*(T[012])", re.I)

# How long a `[?]` stays a fresh doubt rather than a forgotten one.
UNKNOWN_TTL_DAYS = 30

# Folders that are raw material: T0 regardless of what the project declared.
# A draft is a place to be wrong out loud; that is what it is for.
DRAFT_PARTS = {"ideas", "drafts", "archive", "capture", "raw", ".remember"}

HEADER_LINES = 20     # a stake declaration lives in the header, not mid-prose

# ── what counts as a factual claim ───────────────────────────────────────────

# A measured number: thousands, percentages, money, dates, durations.
# "8 slides" and "step 2" are counts of things, not measurements of the world.
FACT_NUM_RE = re.compile(
    r"(?<![\w.\-/])("
    r"\d{4}-\d{2}-\d{2}"                        # 2026-08-12
    r"|\d{1,2}\.\d{2}\.\d{4}"                   # 12.08.2026
    r"|\d[\d\s  ]{2,}\d"              # 1 835, 33 873, 1430
    r"|\d+[.,]?\d*\s*%"                         # 78%, 7,4%
    r"|\d+[.,]?\d*\s*(₸|\$|€|£|руб|k\b|тыс|млн|млрд|bn|m\b)"
    r"|\d+[.,]\d+\s*(s|с|сек|min|мин|h|ч|d|дн)\b"
    r")"
)

# Lines where digits are legitimate and not claims about the world.
SKIP_LINE_RE = re.compile(
    r"^\s*(\||#{1,6}\s|>\s*\*?\*?(stake level|уровень ставки)"
    r"|\d+\.\s|[-*]\s*\[[ x]\])", re.I)
CODEISH_RE = re.compile(r"https?://|`[^`]*\d[^`]*`|v?\d+\.\d+\.\d+|#\d+"
                        r"|\.(py|sh|json|md|png|mp4|csv|ya?ml)\b")


def _lines_outside_fences(text: str) -> list[tuple[int, str]]:
    """Inside a code fence, digits are data, not assertions."""
    out, fence = [], False
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence:
            out.append((i, ln))
    return out


# ── stake level ──────────────────────────────────────────────────────────────

def _declared(text: str) -> str | None:
    """Header only: further down, `Stake level: T2` is usually an example of the
    syntax rather than the file declaring anything about itself."""
    m = STAKE_RE.search("\n".join(text.splitlines()[:HEADER_LINES]))
    return m.group(1).upper() if m else None


def stake_level(owner: Path, text: str, root: Path,
                owner_names: tuple[str, ...]) -> tuple[str, str]:
    """(level, where it came from). Defaults to T1."""
    declared = _declared(text)
    if declared:
        return declared, "declared"
    for parent in owner.parent.parents:
        for name in owner_names:
            pf = parent / name
            if pf.exists() and pf != owner:
                inherited = _declared(pf.read_text(errors="ignore"))
                if inherited:
                    return inherited, f"inherited from {parent.name}/"
        if parent == root:
            break
    return "T1", "default"


def is_draft_path(p: Path) -> bool:
    return bool(DRAFT_PARTS & set(p.parts))


# ── git: when did this line appear ───────────────────────────────────────────

def _blame_dates(owner: Path) -> dict[int, datetime]:
    """Line number -> last change date. Empty when git can't answer, in which
    case a `[?]` is simply never called stale — better silent than wrong."""
    try:
        out = subprocess.run(["git", "blame", "--line-porcelain", "--", owner.name],
                             cwd=owner.parent, capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    dates, lineno = {}, None
    for ln in out.stdout.splitlines():
        m = re.match(r"^[0-9a-f]{40} \d+ (\d+)", ln)
        if m:
            lineno = int(m.group(1))
        elif ln.startswith("author-time ") and lineno:
            dates[lineno] = datetime.fromtimestamp(int(ln.split()[1]), timezone.utc)
            lineno = None
    return dates


# ── the check ────────────────────────────────────────────────────────────────

def check(owner: Path, text: str, base: Path, root: Path, resolve, owner_rel: str,
          ignored, owner_names: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md"),
          now: datetime | None = None) -> tuple[list[dict], dict]:
    """Findings plus counts. `resolve(value, base, root) -> verdict` is the
    host's path resolver, so `[source: …]` is judged by exactly the same rules
    as every other address in the file and cannot drift away from them."""
    level, level_from = stake_level(owner, text, root, owner_names)
    now = now or datetime.now(timezone.utc)
    checks_claims = level != "T0" and not is_draft_path(owner.parent)

    findings: list[dict] = []
    n_sources = n_unknown = n_marked = n_unmarked = 0
    blame: dict[int, datetime] | None = None

    for lineno, ln in _lines_outside_fences(text):
        marked = False

        for raw in SOURCE_RE.findall(ln):
            n_sources += 1
            marked = True
            value = raw.strip().strip("`").rstrip(".,;")
            if value.startswith(("http://", "https://", "mailto:")):
                continue
            if ignored(owner_rel, value):
                continue
            if resolve(value, base, root) in ("broken", "template_unused"):
                findings.append({"kind": "broken_source", "value": value,
                                 "line": lineno, "zone": "claim",
                                 "reason": "source not found"})

        if UNKNOWN_RE.search(ln):
            n_unknown += 1
            marked = True
            if checks_claims:
                if blame is None:
                    blame = _blame_dates(owner)
                born = blame.get(lineno)
                age = (now - born).days if born else None
                if age is not None and age > UNKNOWN_TTL_DAYS:
                    findings.append({"kind": "stale_unknown",
                                     "value": ln.strip()[:90], "line": lineno,
                                     "zone": "claim",
                                     "reason": f"open for {age}d · {level}"})

        if marked:
            n_marked += 1
            continue
        if not checks_claims:
            continue
        if SKIP_LINE_RE.match(ln) or CODEISH_RE.search(ln):
            continue
        hit = FACT_NUM_RE.search(ln)
        if not hit:
            continue
        value = hit.group(1).strip()
        if ignored(owner_rel, value):
            continue
        n_unmarked += 1
        findings.append({"kind": "unmarked_claim", "value": value,
                         "line": lineno, "zone": "claim",
                         "reason": ln.strip()[:70]})

    if level_from == "default" and owner.parent.parent == root / "projects":
        findings.append({"kind": "no_stake_level", "value": owner.parent.name,
                         "reason": "no `Stake level: T…` line"})

    counts = {
        "stake_level": level, "stake_from": level_from,
        "sources": n_sources, "unknowns": n_unknown,
        "claims_marked": n_marked, "claims_unmarked": n_unmarked,
        "broken_sources": sum(1 for f in findings if f["kind"] == "broken_source"),
        "stale_unknowns": sum(1 for f in findings if f["kind"] == "stale_unknown"),
        "no_stake_level": sum(1 for f in findings if f["kind"] == "no_stake_level"),
    }
    return findings, counts


def rate(counts: dict) -> float:
    """Share of unverifiable claims, 0..1, for the drift score.

    A share rather than a count: a detailed plan always holds more numbers than
    a short instruction, and detail must not be punished as decay. Dead sources
    and forgotten `[?]` get their own absolute floor — six of those are bad on
    their own, whatever the file's size.
    """
    counts = {"claims_marked": 0, "claims_unmarked": 0,
              "broken_sources": 0, "stale_unknowns": 0, **counts}
    total = counts["claims_marked"] + counts["claims_unmarked"]
    unmarked = counts["claims_unmarked"] / total if total else 0.0
    hard = min((counts["broken_sources"] + counts["stale_unknowns"]) / 6, 1.0)
    return min(max(unmarked * 0.6, hard), 1.0)

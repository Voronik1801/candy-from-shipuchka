#!/usr/bin/env python3
"""Skill drift: an agent skill is an instruction file that also runs code.

`agent_drift` asks whether a CLAUDE.md still describes the tree. A SKILL.md has
a harder job: it has to *get selected* out of a hundred siblings, stay small
enough not to crowd the context window, and hand the fragile steps to code
rather than to a guess. None of that is visible by reading the file approvingly
— it needs measuring.

Five checks, one per practice, ordered the way a skill actually fails:

  trigger      the description is the only thing the agent sees at startup.
               Vague description → the skill never runs, and nobody notices,
               because a skill that does not fire produces no error.
  expertise    a skill written by asking an LLM to write a skill is generic
               mush: "handle errors appropriately", "validate inputs". The
               model already knew that. What it cannot know is the gotchas.
  context      the body is loaded whole on selection and competes for
               attention with everything else. Over ~500 lines, split into
               `references/` and disclose progressively.
  determinism  a step that must be exactly right every time should be a
               script, not a paragraph the model re-improvises each run.
  trust        a skill folder can execute code with your file system and your
               API keys. Skills from elsewhere are dependencies, and get read
               like dependencies.

Origin decides strictness. A skill you wrote inside your own repository is held
to all five; a vendored plugin skill you cannot edit is checked for trust and
context only — reporting missing gotchas in somebody else's package is how a
tool teaches its user to ignore it.

Sources for the numbers: agentskills.io for the field limits, IBM Technology,
"5 Best Practices for Building AI Agent Skills" (2026-08-10) for the 500-line
budget and the audit figures.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# ── field limits, from the open standard at agentskills.io ───────────────────

NAME_MAX = 64
DESC_MAX = 1024
DESC_MIN = 40           # below this a description cannot say what *and* when

# The context budget. Not a hard rule of the format — a rule of attention.
BODY_MAX_LINES = 500
TOKENS_PER_CHAR = 0.25  # rough, and deliberately so: the point is the order

# ── practice 1: the description is the trigger ───────────────────────────────

# A description earns its keep by answering "when", not only "what". These are
# the ways people actually write that clause, in both languages.
WHEN_RE = re.compile(
    # Plurals spelled out on purpose. The closing `\b` means a bare `trigger`
    # alternative cannot match inside "Triggers —", which is how most skills
    # actually write the clause: the check reported its own skill as
    # trigger-less while the word sat in its description.
    r"\b(use (this )?(skill )?when|used when|invoke when|triggers?"
    r"|when the user|whenever|call this when"
    r"|используй когда|используй, когда|запускается|триггеры?|когда пользователь"
    r"|вызывается когда|применяется когда)\b", re.I)

# Words that describe a category rather than a job. A description made only of
# these is the "generates reports" case from the video.
VAGUE_ONLY_RE = re.compile(
    r"^[^.]{0,60}\b(helper|utility|tools?|assistant|manager|handler"
    r"|хелпер|утилита|инструмент|помощник)\b[^.]{0,20}$", re.I)

# ── practice 2: build from real expertise ────────────────────────────────────

GOTCHA_RE = re.compile(
    r"^#{1,6}\s*.*\b(gotchas?|pitfalls?|caveats?|known issues|troubleshooting"
    r"|common mistakes|edge cases"
    r"|грабл\w*|подводн\w+|ловушк\w+|частые ошибки|что может пойти не так)\b",
    re.I | re.M)

# Advice the model already had before it read your skill. Each of these is a
# sentence that survives deletion without loss — which is the test.
MUSH_RE = [
    re.compile(r"\bhandle errors? (appropriately|properly|gracefully)\b", re.I),
    re.compile(r"\bvalidate (the )?inputs?\b(?!\s+(against|with|using|by))", re.I),
    re.compile(r"\bfollow (industry )?best practices\b", re.I),
    re.compile(r"\bensure (high )?(quality|correctness|accuracy)\b", re.I),
    re.compile(r"\bwrite clean,? (readable|maintainable) code\b", re.I),
    re.compile(r"\bbe (helpful|thorough|concise) (and|&) (clear|accurate)\b", re.I),
    re.compile(r"\buse appropriate (naming|formatting|structure)\b", re.I),
    re.compile(r"\bобрабатыва\w+ ошибки\b(?!\s+(так|через|по))", re.I),
    re.compile(r"\bсоблюда\w+ лучшие практики\b", re.I),
]

# ── practice 4: deterministic scripts ────────────────────────────────────────

RUN_VERB_RE = re.compile(
    r"\b(run|execute|call|invoke|запусти\w*|выполни\w*|вызови|прогони)\b", re.I)
READ_VERB_RE = re.compile(
    r"\b(read|see|refer to|reference|consult|прочит\w+|смотри|см\.|сверься)\b", re.I)

SCRIPT_EXT = {".py", ".sh", ".js", ".ts", ".rb", ".pl", ".bash", ".zsh"}

# ── practice 5: vet before you run ───────────────────────────────────────────

# Two different questions, kept apart on purpose. "Reaches out" is a fact about
# the script; "dangerous" is a judgement. The tool reports the first and only
# escalates when a reach is paired with a secret.
REACH_RE = [
    ("pipe_to_shell", re.compile(r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b")),
    ("eval", re.compile(r"\b(eval|exec)\s*\(", re.I)),
    ("net_post", re.compile(r"\b(requests\.(post|put)|urllib\.request\.urlopen"
                            r"|httpx\.(post|put)|fetch\()", re.I)),
    ("net_shell", re.compile(r"\b(curl|wget|nc|ncat|scp|rsync)\b")),
    ("subprocess_shell", re.compile(r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True")),
    ("destructive", re.compile(r"\brm\s+-[rf]{1,2}\b|shutil\.rmtree\(")),
    ("chmod_exec", re.compile(r"\bchmod\s+[0-7]*7[0-7]*\b|\bchmod\s+\+x\b")),
]
SECRET_RE = [
    ("ssh_keys", re.compile(r"~/\.ssh|/\.ssh/|id_rsa|id_ed25519")),
    ("cloud_creds", re.compile(r"~/\.aws|~/\.config/gcloud|\.kube/config")),
    ("env_dump", re.compile(r"os\.environ\b(?!\.get\(\s*[\"'][A-Z_]+[\"']\s*[,)])"
                            r"|printenv\b|\benv\s*\|")),
    ("dotenv", re.compile(r"\.env\b|credentials\.json|token\.json")),
    ("keychain", re.compile(r"\bsecurity find-generic-password\b|keyring\.")),
    ("browser_cookies", re.compile(r"cookies?[-_]from[-_]browser|Cookies\.sqlite")),
]

# Reading one named API key out of `.env` and POSTing to that vendor is the
# definition of an API client, not of exfiltration. In code its author wrote,
# that pairing is the normal case and reporting it trains the author to ignore
# the whole check. Sweeping up credentials that were never meant for this script
# — ssh keys, cloud profiles, the browser's cookie jar, the whole environment —
# has no benign reading regardless of who wrote it.
HARD_SECRETS = {"ssh_keys", "cloud_creds", "keychain", "browser_cookies", "env_dump"}

# A file that *describes* dangerous patterns — a linter, a test corpus, a
# security doc — matches every one of them. Regex definitions are stripped
# before scanning, so a detector does not indict itself. (It did, on the first
# run: this module reported its own `~/.ssh` pattern as touching ssh keys.)
RE_DEF = re.compile(r"re\.compile\s*\(", re.I)


def strip_pattern_defs(code: str) -> str:
    """Remove `re.compile(...)` calls, brackets balanced. Cheap and exact
    enough: it is the one construct whose contents are quoted, never executed."""
    out, i = [], 0
    for m in RE_DEF.finditer(code):
        if m.start() < i:
            continue
        out.append(code[i:m.start()])
        depth, j = 1, m.end()
        while j < len(code) and depth:
            depth += (code[j] == "(") - (code[j] == ")")
            j += 1
        i = j
    out.append(code[i:])
    return "".join(out)

# Instructions aimed at the agent's operator model rather than at the task.
# A skill has no legitimate reason to tell the agent to conceal its actions.
INJECTION_RE = [
    ("override", re.compile(r"\bignore (all )?(previous|prior|above|earlier)"
                            r"\s+(instructions?|rules?|prompts?)\b", re.I)),
    # "Don't tell the user **about** the upload" conceals. "Don't tell the user
    # **to** register an OAuth app" is advice about what to recommend — the same
    # five words, opposite meanings, separated by one preposition. Requiring the
    # object of the concealment is what keeps them apart.
    ("conceal", re.compile(r"\b(do not|don't|never)\s+(tell|inform|mention|show|"
                           r"report)\s+(the\s+)?(user|human|operator)\b"
                           r"(?!\s+to\s)(\s+(about|that|what|which|anything|if|"
                           r"когда|про)\b|\s*[.,;]|\s*$)", re.I | re.M)),
    ("silent_exfil", re.compile(r"\b(without|no)\s+(asking|confirmation|prompting)"
                                r"[^.\n]{0,40}\b(send|upload|post|transmit)\b", re.I)),
    ("role_break", re.compile(r"\byou are (now |actually )?(not|no longer) "
                              r"(an? )?(assistant|claude|ai)\b", re.I)),
    ("bypass_perm", re.compile(r"--dangerously-skip-permissions"
                               r"|bypassPermissions", re.I)),
]

# HTML comments are invisible in every rendered view of a markdown file, which
# makes them the natural hiding place for text meant only for the model. But
# authoring notes live there too — "Required template: decision record" is the
# overwhelmingly common case. Only a comment that *also* reads as an injection
# is worth reporting; a bare imperative inside one is not evidence of anything.
HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)

# A rule that *names* an attack in order to defend against it matches every
# pattern for that attack. Defensive prose is the single largest source of
# false positives in any injection scanner, and it clusters: the payload is
# quoted, and the sentence around it says what to do about it.
DEFENSIVE_RE = re.compile(
    r"\b(treat|reject|refuse|flag|ignore\s+such|beware|guard against|watch for"
    r"|as hostile|considered hostile|injection|malicious|adversarial|attack"
    r"|do not follow|never obey|враждебн\w+|вредоносн\w+|инъекци\w+|атак\w+)\b",
    re.I)
QUOTED_RE = re.compile(r"[\"'«`]")


def _is_defensive(text: str, at: int) -> bool:
    """Whether a match sits inside prose that is warning about the pattern.

    Window rather than sentence split: instruction files write these as list
    items and tables as often as sentences. Quoting the payload counts too —
    a real injection has no reason to put itself in quotation marks.
    """
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    line = text[start:end if end != -1 else len(text)]
    return bool(DEFENSIVE_RE.search(line)) or bool(QUOTED_RE.search(line[:at - start]))


# Test suites and fixtures contain the malicious samples on purpose — that is
# what a positive control *is*. Scanning them reports the corpus as the threat.
TEST_PARTS = {"tests", "test", "fixtures", "__tests__", "spec", "examples"}


def _is_test_file(rel: Path) -> bool:
    return bool(TEST_PARTS & set(rel.parts)) or rel.name.startswith("test_") \
        or rel.stem.endswith("_test")


# ── frontmatter ──────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, int]:
    """→ (fields, body_start_line). Hand-rolled: stdlib only, and the shape is
    fixed — `key: value` with optional folded continuations. A YAML dependency
    for six keys would cost more than it explains."""
    lines = text.splitlines()
    if not lines or lines[0].strip() not in ("---", "---\n"):
        return {}, 0
    fields, key = {}, None
    for i, ln in enumerate(lines[1:], start=2):
        if ln.strip() == "---":
            return fields, i
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", ln)
        if m:
            key = m.group(1).lower()
            value = m.group(2).strip()
            # Block scalars (`description: >` / `|`) carry their text on the
            # following indented lines. Keeping the marker as the value made
            # every folded description look 1 char long and trigger-less.
            fields[key] = "" if value in (">", "|", ">-", "|-", ">+", "|+") \
                else value.strip("\"'")
        elif key and ln.startswith((" ", "\t")) and ln.strip():
            fields[key] = (fields[key] + " " + ln.strip()).strip()
    return fields, len(lines)          # unterminated frontmatter


# ── origin ───────────────────────────────────────────────────────────────────

VENDOR_PARTS = {"plugins", "node_modules", ".venv", "site-packages", "vendor"}


def origin_of(skill_dir: Path, root: Path) -> str:
    """`own` — inside the repository under audit. `vendor` — anything installed:
    a plugin, a package, a marketplace download. `external` — elsewhere on the
    machine entirely (a global `~/.claude/skills`)."""
    if VENDOR_PARTS & set(skill_dir.parts):
        return "vendor"
    try:
        skill_dir.resolve().relative_to(root.resolve())
    except ValueError:
        return "external"
    return "own"


# Which practices apply to which origin. Vendored code cannot be edited by the
# reader, so telling them their gotchas section is missing is pure noise —
# but what that code reaches for is exactly what they need to know.
APPLIES = {
    "own":      {"trigger", "expertise", "context", "determinism", "trust"},
    "external": {"trigger", "context", "determinism", "trust"},
    "vendor":   {"context", "trust"},
}


# ── the checks ───────────────────────────────────────────────────────────────

def check_trigger(fields: dict, skill_dir: Path) -> list[dict]:
    out = []
    name = fields.get("name", "")
    desc = fields.get("description", "")

    if not fields:
        return [{"kind": "skill_no_frontmatter", "value": skill_dir.name,
                 "practice": "trigger",
                 "reason": "no YAML header — the agent has nothing to match on"}]
    # A missing `name` is not reported. The standard lists the field, but every
    # runtime that loads these falls back to the folder name, so the skill is
    # invoked correctly regardless — and 90 findings that change nothing are how
    # a report gets skimmed instead of read. A *wrong* name is different: it
    # makes the declaration and the invocation disagree, which is a real bug.
    if name:
        if len(name) > NAME_MAX:
            out.append({"kind": "skill_name_too_long", "value": name[:50],
                        "practice": "trigger",
                        "reason": f"{len(name)} chars, limit {NAME_MAX}"})
        if name != skill_dir.name:
            out.append({"kind": "skill_name_mismatch", "value": name,
                        "practice": "trigger",
                        "reason": f"folder is `{skill_dir.name}` — invocation and "
                                  f"declaration disagree"})
    if not desc:
        out.append({"kind": "skill_no_description", "value": skill_dir.name,
                    "practice": "trigger",
                    "reason": "nothing decides whether this skill ever runs"})
        return out

    if len(desc) > DESC_MAX:
        out.append({"kind": "skill_description_too_long", "value": desc[:60] + "…",
                    "practice": "trigger",
                    "reason": f"{len(desc)} chars, limit {DESC_MAX} — the tail is "
                              f"silently dropped"})
    if len(desc) < DESC_MIN:
        out.append({"kind": "skill_description_thin", "value": desc,
                    "practice": "trigger",
                    "reason": f"{len(desc)} chars — too short to say what and when"})
    elif not WHEN_RE.search(desc):
        out.append({"kind": "skill_description_no_trigger", "value": desc[:70] + "…",
                    "practice": "trigger",
                    "reason": "says what it does, never says when to use it — "
                              "models under-trigger, so this one will be skipped"})
    if VAGUE_ONLY_RE.match(desc.strip()):
        out.append({"kind": "skill_description_vague", "value": desc[:70],
                    "practice": "trigger",
                    "reason": "names a category, not a job"})
    return out


def check_expertise(body: str, skill_dir: Path) -> list[dict]:
    out = []
    if not GOTCHA_RE.search(body):
        out.append({"kind": "skill_no_gotchas", "value": skill_dir.name,
                    "practice": "expertise",
                    "reason": "no gotchas section — every correction you make by "
                              "hand you will make again next week"})
    for rx in MUSH_RE:
        m = rx.search(body)
        if m:
            line = body[:m.start()].count("\n") + 1
            out.append({"kind": "skill_generic_advice", "value": m.group(0),
                        "practice": "expertise", "line": line,
                        "reason": "the model knew this before it read your skill"})
    return out


def check_context(body: str, skill_dir: Path, body_start: int) -> list[dict]:
    out = []
    n_lines = body.count("\n") + 1
    tokens = int(len(body) * TOKENS_PER_CHAR)
    has_refs = (skill_dir / "references").is_dir()
    if n_lines > BODY_MAX_LINES:
        out.append({"kind": "skill_body_too_long", "value": f"{n_lines} lines",
                    "practice": "context", "line": body_start,
                    "reason": f"≈{tokens} tokens loaded on every selection"
                              + ("" if has_refs else " and no references/ to split into")})

    # A reference nobody points at is never opened — it is not progressive
    # disclosure, it is a file the agent will never learn exists.
    refs = skill_dir / "references"
    if refs.is_dir():
        for f in sorted(refs.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                if f.name not in body and f.stem not in body:
                    out.append({"kind": "skill_reference_unlinked",
                                "value": str(f.relative_to(skill_dir)),
                                "practice": "context",
                                "reason": "body never names it — it will never be read"})
    return out


def check_determinism(body: str, skill_dir: Path) -> list[dict]:
    """Scripts are only deterministic if the body says to run them.

    The failure this catches is quiet: a script sitting in `scripts/` that the
    body mentions in passing gets read as reference material and re-implemented
    from scratch, which is the exact guessing the script existed to remove.
    """
    out = []
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return out
    for f in sorted(scripts_dir.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f.suffix not in SCRIPT_EXT:
            continue
        rel = str(f.relative_to(skill_dir))
        # A window of a few lines, not one line: the common shape is
        # "Run the script:" followed by a fenced command block, so the verb and
        # the filename never share a line. Reading one line found the intent
        # missing in exactly the skills that stated it most clearly.
        lines = body.splitlines()
        mentions = [" ".join(lines[max(0, i - 4):i + 3])
                    for i, ln in enumerate(lines) if f.name in ln]
        if not mentions:
            out.append({"kind": "skill_script_unlinked", "value": rel,
                        "practice": "determinism",
                        "reason": "the body never mentions it"})
            continue
        if not any(RUN_VERB_RE.search(ln) for ln in mentions):
            verb = "read as reference" if any(READ_VERB_RE.search(ln)
                                              for ln in mentions) else "no verb"
            out.append({"kind": "skill_script_intent_unclear", "value": rel,
                        "practice": "determinism",
                        "reason": f"mentioned but never «run this» ({verb}) — the "
                                  f"agent may reimplement it instead"})
    return out


def _scan(text: str, table) -> list[str]:
    return [name for name, rx in table if rx.search(text)]


def check_trust(skill_dir: Path, body: str, origin: str) -> list[dict]:
    """What the folder can reach, and whether anything in it talks past you."""
    out = []
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file() or f.suffix not in SCRIPT_EXT:
            continue
        if _is_test_file(f.relative_to(skill_dir)):
            continue
        try:
            code = f.read_text(errors="ignore")
        except OSError:
            continue
        code = strip_pattern_defs(code)
        reaches, secrets = _scan(code, REACH_RE), _scan(code, SECRET_RE)
        # The escalation to "this has the shape of exfiltration" needs a hard
        # secret whoever wrote it — a vendored CLI reading its own
        # `POSTIZ_API_KEY` and calling its own API is not a finding, it is the
        # product. Soft pairings still surface below as "reaches out".
        secrets = [s for s in secrets if s in HARD_SECRETS]
        if reaches and secrets:
            out.append({"kind": "skill_script_exfil_shape",
                        "value": str(f.relative_to(skill_dir)), "practice": "trust",
                        "reason": f"touches {'+'.join(secrets)} and "
                                  f"{'+'.join(reaches)} in one file"})
        elif reaches and origin != "own":
            out.append({"kind": "skill_script_reaches_out",
                        "value": str(f.relative_to(skill_dir)), "practice": "trust",
                        "reason": f"{'+'.join(reaches)} — read it before running"})

    for f in sorted(skill_dir.rglob("*.md")):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        rel = f.relative_to(skill_dir)
        if _is_test_file(rel):
            continue
        rel = str(rel)
        for name, rx in INJECTION_RE:
            for m in rx.finditer(text):
                if _is_defensive(text, m.start()):
                    continue
                out.append({"kind": "skill_prompt_injection", "value": rel,
                            "practice": "trust", "line": text[:m.start()].count("\n") + 1,
                            "reason": f"{name}: “{m.group(0)[:60]}”"})
                break
        for m in HTML_COMMENT_RE.finditer(text):
            inner = m.group(1)
            hit = next((rx.search(inner) for _, rx in INJECTION_RE
                        if rx.search(inner)), None)
            if hit and not _is_defensive(inner, hit.start()):
                out.append({"kind": "skill_hidden_instruction", "value": rel,
                            "practice": "trust",
                            "line": text[:m.start()].count("\n") + 1,
                            "reason": f"“{hit.group(0)[:50]}” inside an HTML comment — "
                                      f"invisible in every rendered view"})
                break
    return out


# ── one skill ────────────────────────────────────────────────────────────────

# What each finding costs. Trust findings dominate because they are the only
# class where being wrong costs more than an unread file.
WEIGHT = {
    "skill_no_frontmatter": 30, "skill_no_description": 30,
    "skill_description_no_trigger": 14, "skill_description_thin": 12,
    "skill_description_vague": 10, "skill_description_too_long": 8,
    "skill_name_mismatch": 10, "skill_name_too_long": 5,
    "skill_no_gotchas": 8, "skill_generic_advice": 5,
    "skill_body_too_long": 12, "skill_reference_unlinked": 4,
    "skill_script_unlinked": 8, "skill_script_intent_unclear": 6,
    "skill_script_reaches_out": 10, "skill_script_exfil_shape": 40,
    "skill_prompt_injection": 45, "skill_hidden_instruction": 35,
}


def analyze_skill(path: Path, root: Path, ignored=None,
                  origin: str | None = None) -> dict:
    """`path` is the SKILL.md itself."""
    skill_dir = path.parent
    text = path.read_text(errors="ignore")
    fields, body_start = parse_frontmatter(text)
    body = "\n".join(text.splitlines()[body_start:])
    origin = origin or origin_of(skill_dir, root)
    applies = APPLIES[origin]

    findings: list[dict] = []
    if "trigger" in applies:
        findings += check_trigger(fields, skill_dir)
    if "expertise" in applies:
        findings += check_expertise(body, skill_dir)
    if "context" in applies:
        findings += check_context(body, skill_dir, body_start)
    if "determinism" in applies:
        findings += check_determinism(body, skill_dir)
    if "trust" in applies:
        findings += check_trust(skill_dir, body, origin)

    rel = str(path.relative_to(root)) if root in path.parents else str(path)
    if ignored:
        findings = [f for f in findings if not ignored(rel, f["value"])]

    risk = sum(WEIGHT.get(f["kind"], 5) for f in findings)
    risk = round(min(risk, 100), 1)
    status = ("clean" if risk < 15 else "weak" if risk < 40
              else "poor" if risk < 70 else "unsafe")
    n_lines = body.count("\n") + 1
    return {
        "path": rel, "name": fields.get("name", ""), "origin": origin,
        "risk": risk, "status": status,
        "body_lines": n_lines, "body_tokens": int(len(body) * TOKENS_PER_CHAR),
        "desc_chars": len(fields.get("description", "")),
        "has_references": (skill_dir / "references").is_dir(),
        "has_scripts": (skill_dir / "scripts").is_dir(),
        "findings": findings,
    }


# ── discovery ────────────────────────────────────────────────────────────────

def find_skills(root: Path, extra_roots: list[Path] | None = None) -> list[Path]:
    """Every SKILL.md under the repository, plus any explicitly named roots.

    Explicit rather than automatic: the global `~/.claude` and its plugins hold
    hundreds of skills nobody in this repository can fix, and sweeping them in
    by default would bury the handful that matter.
    """
    seen, out, bodies = set(), [], set()
    for base in [root, *(extra_roots or [])]:
        base = Path(base).expanduser()
        if not base.exists():
            continue
        for p in base.rglob("SKILL.md"):
            # `fixtures/` holds skills built to be broken — a linter that
            # lints its own test corpus reports its fixtures as defects.
            if {".git", "node_modules", "__pycache__", "fixtures"} & set(p.parts):
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            # A plugin cache keeps every version it ever fetched side by side.
            # Four identical copies of one skill are one finding repeated four
            # times, and they crowd out everything else in the report.
            try:
                fingerprint = (p.parent.name,
                               hashlib.sha1(p.read_bytes()).hexdigest())
            except OSError:
                continue
            if fingerprint in bodies:
                continue
            bodies.add(fingerprint)
            out.append(p)
    return sorted(out)


def summarize(reports: list[dict]) -> dict:
    by_practice: dict[str, int] = {}
    for r in reports:
        for f in r["findings"]:
            by_practice[f["practice"]] = by_practice.get(f["practice"], 0) + 1
    return {
        "skills": len(reports),
        "own": sum(1 for r in reports if r["origin"] == "own"),
        "vendor": sum(1 for r in reports if r["origin"] == "vendor"),
        "external": sum(1 for r in reports if r["origin"] == "external"),
        "clean": sum(1 for r in reports if r["status"] == "clean"),
        "unsafe": sum(1 for r in reports if r["status"] == "unsafe"),
        "findings": sum(len(r["findings"]) for r in reports),
        "by_practice": by_practice,
    }

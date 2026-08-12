# agent-context-drift

**Your agent instructions are code. Lint them like code.**

`CLAUDE.md`, `AGENTS.md`, `.cursorrules` — these files tell an AI agent how your
repository is laid out. Then you rename a folder, drop a file, move a script,
and nobody updates them.

A stale README annoys a human: they notice the mismatch and go look themselves.
A stale instruction file **changes what the agent does**. It walks the dead path
with total confidence, opens last quarter's plan instead of this one, and
faithfully reproduces the mess you asked it to clean up. You cannot see this by
reading the file — it looks perfectly sensible until you check every path.

This checks every path. No LLM, no network, no tokens: 3 seconds, a JSON report,
and a number.

```console
$ agent-drift --explain

------------------------------------------------------------------------
docs/AGENTS.md   drift 65.5 [broken]   lag 68.0d · 34 changes since
  candidates 61 · not paths 23 · checked 39 · ok 23 · broken 4 · ambiguous 4
    BROKEN:
      line   91  docs/skills_catalog.md   [not_found]
      line  185  docs/sla.md              [not_found]
      line  130  infra/db/init/07_tracking.sql   [not_found]
    undocumented:
                 reports/
                 migrations/
```

## Install

**The short way — one file, nothing to install:**

```bash
curl -O https://raw.githubusercontent.com/Voronik1801/candy-from-shipuchka/main/agent-context-drift/agent_drift.py
python3 agent_drift.py --explain
```

Python 3.9+, standard library only. No dependencies, so there is nothing to
resolve and nothing to break.

**If you want it as a command**, `pipx` keeps it out of your system Python:

```bash
pipx install "git+https://github.com/Voronik1801/candy-from-shipuchka.git#subdirectory=agent-context-drift"
agent-drift --explain
```

Same thing with `pip` works inside a virtualenv. Plain `pip install` into a
Homebrew or system Python will refuse, and that refusal is correct.

Not on PyPI yet.

## Use

```bash
agent-drift                    # JSON report for the whole repo
agent-drift --explain          # human-readable
agent-drift --summary          # one line, silent when nothing is wrong
agent-drift --fail-over 40     # exit 1 when any file drifts past 40 — for CI
agent-drift --file docs/AGENTS.md
```

Recognised out of the box: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
`.cursorrules`, `copilot-instructions.md`. Anything else via `--name`.

### In CI

```yaml
- name: Check agent instructions against the tree
  run: |
    curl -sO https://raw.githubusercontent.com/Voronik1801/candy-from-shipuchka/main/agent-context-drift/agent_drift.py
    python3 agent_drift.py --fail-over 40 --explain
```

No install step, because there is nothing to install.

Now a PR that renames a directory without touching the instructions fails,
instead of silently misleading every agent that reads them afterwards.

## What it looks for

| Signal | Meaning |
|---|---|
| `broken_path` | a path that exists nowhere — the agent will follow it anyway |
| `undocumented_dir` | a live directory the instructions never mention |
| `template_unused` | a rule is written (`notes/YYYY-MM-DD_slug.md`) but nothing follows it |
| `ambiguous_ref` | it exists, just not where the file says. Not an error, only untidy |
| staleness | not "the file is old" but "the project moved on and the docs did not" |

The drift score is a **ratio of what rotted**, not a count of errors — 40 paths
and 7 paths are not comparable. Bands: `<20` fresh · `20–39` drifting ·
`40–59` stale · `≥60` broken.

## Why the false positives are the whole story

Writing "check that every path exists" takes an evening. The first run of this
one, over a real 11-file repository, reported **159 broken paths**. Almost all
were wrong:

- `notes/YYYY-MM-DD_slug.md` — a naming rule, not a file
- `myrepo/docs/` — a path written from the repo name down, resolves fine
- `CREATE`, `DROP/TRUNCATE` — SQL keywords in backticks
- `myproject/src/main.py` — a tree entry, parsed without dropping the tree's root line

A checker that cries wolf 150 times gets switched off after the first run and
never comes back. So the work went into the funnel, not the idea:

1. **Only marked-up zones are scanned** — code spans, ASCII trees, markdown
   links. Prose is never touched.
2. **Templates are resolved as globs**, not as literal paths. `{date}` and
   `YYYY-MM-DD` expand; a template with no matching files is a soft signal
   ("this rule is dead"), not a broken link.
3. **A cascade of bases with three outcomes**, not two: found where stated →
   silent; found somewhere else → `ambiguous` (weight 0.05); found nowhere →
   `broken`.
4. **Trees are parsed with a stack** on the indent column, and the block's own
   root line is dropped.
5. **A directory whose parent is already documented is not "undocumented"** —
   instructions describe architecture, they do not inventory leaves. Nested git
   repositories are someone else's territory.

Result on that same repository: **8 findings, every one real** — a file renamed
months ago, a script that moved, two documents that never existed, a `../../`
one level off.

`tests/` pins each of those false-positive classes so they cannot come back.

## Muting things on purpose

`.drift-ignore` in the repository root:

```
# deliberate historical mention — this path is gone and the text says so
~/.config/old-tool/memory

# a whole file we no longer maintain
skip: legacy/**

# one finding in one file
docs/AGENTS.md::examples/*
```

Commit it — it is part of your governance, unlike a cache.

**A warning about this file:** if it grows while the detector's accuracy stays
flat, the filters are wrong and the fix belongs in the code, not here.

## Use with Claude Code

`skills/agent-drift/SKILL.md` wraps the detector for Claude Code: it runs
the scan, sorts findings into *outdated* / *undocumented* / *deliberate* /
*unclear*, proposes one concrete edit each, and **waits for your approval**
before writing anything.

Copy it into `.claude/skills/` and ask "check my instruction files".

## Limits

- Paths inside prose are invisible by design. Put them in backticks.
- It checks whether the structure is *true*, never whether it is *good* — for
  prose quality, an LLM reviewer is the right tool.
- Directory scanning stops at depth 2 on purpose.

## License

MIT

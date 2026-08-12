---
name: agent-drift
description: >
  Checks whether agent instruction files (CLAUDE.md, AGENTS.md, .cursorrules)
  still match the real folder structure: dead paths, undocumented directories,
  rules nobody follows, lag behind actual changes. Shows a report and edits only
  with approval. Triggers — "check my instructions", "is CLAUDE.md still
  accurate", "the structure drifted", "audit AGENTS.md", "/agent-drift".
allowed-tools: Bash, Read, Edit, Glob, Grep
---

# agent-drift

Instruction files rot silently. A folder gets renamed, a file deleted, a script
moved — and the file keeps confidently pointing an agent at a dead address.
You cannot spot this by reading: it looks sensible until every path is checked.

This skill runs the check and helps act on it. It does **not** judge writing
quality — for that, use an LLM reviewer. Here the question is narrower and
answerable: is what the file claims actually true?

---

## Step 1 — Scan

```bash
agent-drift --explain          # or: python3 agent_drift.py --explain
```

**Do not read the instruction files before this.** The report carries line
numbers; open them surgically afterwards. The scan takes about three seconds.

| Finding | Meaning | Treat as an error? |
|---|---|---|
| `broken_path` | exists nowhere | **yes — this is the point** |
| `undocumented_dir` | live directory, never mentioned | yes, if significant |
| `template_unused` | rule written, nothing follows it | soft |
| `ambiguous_ref` | exists, but not where stated | **no** — just untidy |
| `external_ref` | outside the repo, unverifiable | no |

---

## Step 2 — Report, tersest first

```
instruction files × 8 · checked against the tree

  65  services/api/AGENTS.md    4 dead paths · 68 days behind
  47  CLAUDE.md                 reports/, migrations/ undocumented
  ——— below threshold ———
  22  docs · 19  web · 4  infra · 1  cli   (5 files fine)

Also 28 paths written from the repo root rather than relative — they work,
they just read ambiguously. Show them?
```

Rules for presenting:
- files under 40 get one line, never expanded;
- `ambiguous_ref` stays **collapsed**, explicitly marked "works";
- no "overdue", no "you should have", no warning emoji.

Do not dump a hundred findings. Most of them are not errors, and after one
such report nobody runs the skill again.

---

## Step 3 — A diagnosis, not a list

For the 1–3 worst files, open the exact lines from the report and sort each
finding into one bucket:

| Bucket | Sign | Action |
|---|---|---|
| **outdated** | the target was renamed or removed | fix the line |
| **undocumented** | the folder is alive and used | add it to the tree |
| **deliberate** | example, historical mention, external address | add to `.drift-ignore` |
| **unclear** | intent unknown | ask |

**One concrete action per finding**, never "consider reviewing this". When an
obvious replacement exists (`docs/api.md` is gone, `docs/api/README.md` sits
right there), propose it outright.

---

## Step 4 — Approval

```
Proposed:
  1. services/api/AGENTS.md — drop docs/sla.md and skills_catalog.md,
     fix ../../../memory/… to ../../memory/feedback/…
  2. CLAUDE.md — add reports/ and migrations/ to the tree
  3. Mute /opt/deploy-target — it lives on the server, not here

Which ones? (numbers / all / none)
```

Show diffs before writing. Write **only** after an explicit answer. "None" is a
valid answer and produces no follow-up nagging.

---

## Step 5 — The mute file

`.drift-ignore` at the repository root, one rule per line, `#` for comments,
`file::value` to scope a rule, `skip: <glob>` to drop a whole file.

Commit it — it is governance, not cache.

Degeneration check: if the ignore file grows while accuracy stays flat, the
filters are wrong and the fix belongs in the detector, not in more mutes.

---

## Do not

- Edit instruction files without approval, even "obvious" typos.
- Put `ambiguous_ref` in the main list — those are not errors.
- Ask for every subfolder to be documented. Instructions describe
  architecture; they do not inventory the tree.
- Re-run the scan right after edits just to confirm. It reads the filesystem;
  the next real run will reflect the change.

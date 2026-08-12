# candy from shipuchka

Skills and scripts that fell out of running a personal operating system on top
of AI agents. Each one solves a problem I actually hit and was calibrated
against a real repository rather than a demo.

Every tool comes in two forms: a `SKILL.md` you hand to your agent, and a
script you run yourself. No libraries, no packages, no framework, nothing to
sign up for. Take one file and go.

[Читать по-русски](README.ru.md)

---

## What's in the box

### 🍬 [agent-context-drift](agent-context-drift/)

**Your agent instructions are code. Lint them like code.**

`CLAUDE.md`, `AGENTS.md`, `.cursorrules` tell an AI agent how your repository is
laid out. Then you rename a folder, and nobody updates them. A stale README
annoys a human; a stale instruction file *changes what the agent does* — it
walks the dead path with full confidence.

Checks every path mentioned against the real tree. No LLM, no network, no
tokens: ~3 seconds, a JSON report, and a drift score. Runs in CI with
`--fail-over 40`.

```bash
python3 agent-context-drift/agent_drift.py --explain
```

Python 3.9+, standard library only, one file. 18 tests pin the false-positive
classes that made the naive version report 159 broken paths where 8 were real.

### 🍬 [creative-wander](creative-wander/)

**An idea machine that rolls its own dice, because the model cannot.**

Ask an LLM for ten post ideas and you get ten variations of what you already
think. Ask it to pick something random from your notes and it picks something
*related* — coherence is its entire job, which is exactly the wrong instrument
for having an idea.

So the randomness comes from outside the model: `wander.py` pulls fragments out
of your archive using the OS random number generator, weighted towards what you
have not opened in months. Five agents smash those fragments together knowing
nothing about what "good" means; five judges score the results later, each with
a single criterion, never seeing where an idea came from.

```bash
cd creative-wander && python3 wander.py 6 40 --root ~/notes
```

A method plus the one script it needs. Works without any agent too — read the
fragments yourself, that alone does most of the work.

---

## Why the odd name

Shipuchka is Russian for the fizzy sweet — and it is what I go by online, where
I build AI-native systems out loud. The repository is the box; the tools are
what is inside it.

## Using these

Every tool is independent: its own README, its own tests, no shared runtime.

- **Skill:** copy `<tool>/SKILL.md` into `.claude/skills/<tool>/`
- **Script:** copy the `.py` file anywhere and run it with Python 3.9+

Nothing here is published to PyPI on purpose. These are not libraries — you do
not import them, you run them or give them to an agent.

Issues and pull requests are welcome, especially reports of false positives
with the snippet that triggered them. That kind of report is what turned the
first tool here from noise into something usable.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship it.

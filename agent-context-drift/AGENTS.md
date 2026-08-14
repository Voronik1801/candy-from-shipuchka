# agent-context-drift — instructions for agents

A linter that checks AI-agent instruction files against the real repository
tree. One module, standard library only, no LLM calls.

## Layout

```
agent-context-drift/
├── agent_drift.py     ← the whole detector: zones → filters → resolution → score
├── claim_drift.py     ← the claim layer: [source: …] / [?] markers, stake levels
├── SKILL.md           ← the agent-facing form; copy into .claude/skills/agent-drift/
├── tests/
│   ├── test_drift.py  ← behaviour pins, one per historical false positive
│   ├── corpus.py      ← the named false positives; run it to print the list
│   └── fixtures/
│       ├── sample/            ← a toy repo; its AGENTS.md is broken on purpose
│       └── false-positives/   ← one repository per named false positive
└── .drift-ignore      ← deliberate mutes, committed
```

## Working on this

- `python3 -m unittest discover tests` before every commit.
- `python3 agent_drift.py --explain` on this repo — it must stay under 40.
- `python3 tests/corpus.py` prints what the tool is pinned never to claim.
- New filter or heuristic → add a test naming the false positive it prevents.
  Cases needing a repository of their own (git state, an exclude file, a plugin
  layout) go in the corpus; the rest stay in `tests/test_drift.py`.
- Fixture paths under `tests/fixtures/` are broken deliberately; `.drift-ignore`
  skips them.

### Adding a corpus case

A directory with `case.json` and a `tree/` to copy. `case.json` names the claim
the tool must not make, the findings that must be `absent` — and, required, the
ones that must still be `present`.

That last field is the point. Silence is cheap: disabling a signal buys it, and
a corpus that only checked for silence would call that a pass. Every case
therefore carries a positive control, and a test enforces that none is missing.

## Design rules

Accuracy beats coverage: a checker that reports ten false alarms gets switched
off, and then it catches nothing at all. Prefer a soft category (`ambiguous`,
`descriptive`) over calling something broken when unsure.

Keep it dependency-free and under a second on a mid-sized repository — it runs
in pre-commit hooks.

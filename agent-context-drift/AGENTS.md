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
│   └── fixtures/      ← a toy repo; its AGENTS.md is broken on purpose
└── .drift-ignore      ← deliberate mutes, committed
```

## Working on this

- `python3 -m unittest discover tests` before every commit.
- `python3 agent_drift.py --explain` on this repo — it must stay under 40.
- New filter or heuristic → add a test in `tests/test_drift.py` naming the
  false positive it prevents. That file is the specification.
- Fixture paths under `tests/fixtures/` are broken deliberately; `.drift-ignore`
  skips them.

## Design rules

Accuracy beats coverage: a checker that reports ten false alarms gets switched
off, and then it catches nothing at all. Prefer a soft category (`ambiguous`,
`descriptive`) over calling something broken when unsure.

Keep it dependency-free and under a second on a mid-sized repository — it runs
in pre-commit hooks.

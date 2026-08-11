# candy-from-shipuchka — instructions for agents

A monorepo of small, independent tools. Each lives in its own directory with
its own README, tests and entry point; there is no shared runtime and no
cross-imports between them.

## Layout

```
candy-from-shipuchka/
├── agent-context-drift/   ← lints agent instruction files against the tree
├── creative-wander/       ← idea machine: random fragments → collisions → judges
└── .github/workflows/     ← one workflow per tool, path-filtered
```

## Adding a tool

One directory, and inside it: `README.md` explaining the problem before the
solution, the code, tests where behaviour is non-obvious, and a workflow in
`.github/workflows/<tool>.yml` filtered on that directory's path.

Add it to both `README.md` and `README.ru.md` — the box is only useful if the
label lists what is inside.

## Rules

Tools stay independent and dependency-free where possible: someone should be
able to copy a single file into their project and have it work.

English in code and output, README in both English and Russian.

Accuracy beats coverage in anything that reports problems. A checker that
raises ten false alarms gets switched off, and then it catches nothing at all.

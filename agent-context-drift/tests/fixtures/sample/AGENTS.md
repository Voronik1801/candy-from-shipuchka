# Sample project — agent instructions

A fixture repository. Every line below exists to pin one detector behaviour;
the suite in tests/ asserts what each of them must produce.

## Layout

```
sample/
├── src/               ← application code
│   ├── main.py
│   └── api/
│       └── routes.py
├── docs/              ← architecture.md, adr.md
└── notes/             ← meeting notes
```

## Where things go

| What | Where |
|---|---|
| Meeting note | `notes/YYYY-MM-DD_slug.md` |
| Architecture decision | `docs/adr.md` |
| Deploy config | `config/deploy.yaml` |
| Old runbook | `docs/runbook-2024.md` |

## Conventions

Read `docs/architecture.md` before touching `src/api/routes.py`.
Entry point is `src/main.py`; run it with `python3 src/main.py --verbose`.

Paths written from the repo name also occur: `sample/docs/architecture.md`.

Database statements we never run in production: `CREATE`, `DROP/TRUNCATE`,
`ALTER TABLE`. Issue tracker lives at github.com/example/sample and docs at
https://example.com/handbook.

Prefer the `fast-refresh` workflow over `manual-reload`.

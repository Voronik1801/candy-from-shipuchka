# creative-wander

**An idea machine that rolls its own dice, because the model cannot.**

Ask an LLM for ten post ideas and you get ten variations of what you already
think. Ask it to "pick something random from my notes" and it picks something
*thematically related* — coherence is its entire job. That is exactly the wrong
instrument for having an idea.

This is a method, plus the one script the method needs. It works the way
creativity actually works: **fill your head with unrelated material → wander
without a goal → catch the collision.**

## The core move

Randomness comes from **outside the model**. `wander.py` uses the OS random
number generator, which does not know what your files are about and will
happily drop an oncology note next to a recipe for radishes. Then five agents
are told to smash those fragments together — with no idea what "good" means.
Judging happens later, by different agents, on anonymised output.

```bash
python3 wander.py 6 40 --root ~/notes
```

Twelve random fragments, weighted towards what you have not opened in months.
A file you touched yesterday is already in your head — the idea in it has been
had.

## Why each rule exists

**The dice are rolled by the system, never by the model.** Never replace
`wander.py` with "think of some random topics". You will get the model's
priors back, dressed as chance.

**Generating and judging are separate passes, separate agents.** A wanderer who
knows the selection criteria starts self-censoring and collapses to the safe
option. Wanderers never see the criteria; judges never see where an idea came
from.

**An idea is born from two distant fragments colliding.** One fragment is a
summary. Minimum two.

**Do not filter while generating.** Rejects are the genre, not a failure. To
end up with ten live ideas, produce thirty to fifty.

**State an idea as a hook, not a topic.** Not "a post about context windows"
but "The model didn't forget. It had nowhere to put it."

**Keep the wild ones.** Word salad goes to a cringe log, not the bin — it is
raw material. "The machine told me to connect data labelling and radishes, and
you know what, I found the connection."

**Bias towards the forgotten, with a quota per area.** Any real archive is
lopsided: one project can hold a third of your files, and without a cap every
third roll lands there. `--max-per-area 1` for maximum spread, `--exclude work`
to steer away from a heavy corner.

**Age comes from git history, not mtime.** After a clone or a bulk copy half
the archive shares one date and "forgottenness" cannot be measured from it.

## The pipeline

| Phase | What happens |
|---|---|
| 0 — Fill the head | random fragments + what you already published (anti-context: do not reinvent last month's post) + fresh outside news |
| 1 — Wander | 5 agents in parallel, **different models**, each with its own fragments and its own stance: causal chains · contradictions · bodily and mundane metaphors · fast and wild · what turned out to be wrong. Then a sixth agent asked for "three wilder ones nobody reached" — the best idea often arrives after the formal goodbye |
| 2 — Sort the pile | mechanically: collapse duplicates (two agents landing on the same collision is a strength signal), drop repeats of published work, wild ones to the cringe log |
| 3 — Judge | 5 judges, **one single criterion each** — give a judge two criteria and everything averages out to "fine". Scores are summed; ideas with *split* verdicts get their own section, because unanimous fours usually mean "solid and boring" |
| 3.5 — Fact-check | only ideas resting on an external fact. Two different search phrasings on purpose: agreement means the claim is solid, disagreement is exactly where the comments will bite |
| 4 — Deliver | ten ideas, each as a verbatim hook |

The full prompt for each phase, including the wanderer and judge briefs, is in
[SKILL.md](SKILL.md).

## Use it

**With Claude Code:** copy `SKILL.md` into `.claude/skills/creative-wander/`
and say "I need ideas". It runs all five phases.

**Without any agent:** run `wander.py` and read the fragments yourself. That
alone does most of the work — the script is the part you cannot improvise.

```bash
python3 wander.py                    # 5 fragments, 40 lines each
python3 wander.py 8 60               # more, longer
python3 wander.py --root ~/vault     # any text directory
python3 wander.py --exclude archive  # steer away
python3 wander.py 5 40 --seed 42     # reproducible
```

Python 3.9+, standard library only.

`exa.py` is optional and needs an `EXA_API_KEY` — it is used only in phase 0.3
(fresh news) and 3.5 (fact-checking). Skip it and use whatever web search your
agent has.

## Limits

Built for a personal archive of text — notes, drafts, code, meeting records. On
a repository of pure source code the collisions are duller: the fragments are
all from one domain, and the method feeds on distance.

## License

MIT

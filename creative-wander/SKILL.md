---
name: creative-wander
description: >
  Generates content ideas through guided wandering: random fragments of your own
  archive × what you already published × fresh outside news → parallel wanderer
  agents → parallel judge agents → ten ideas stated as hooks. Triggers — "I need
  ideas", "give me post ideas", "brainstorm", "wander", "/creative-wander".
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent", "WebSearch", "WebFetch"]
---

# creative-wander — an idea machine

Built on how creativity actually works: **fill the head with context → wander
without a goal → catch the collision.**

`$ARGUMENTS` — optional. A number of ideas (default 10) or a seed topic.

---

## Principles — do not break these, everything rests on them

**The system rolls the dice, not the model.** Ask an LLM to "pick something
random" and it picks something thematically related, because coherence is its
job. Real randomness comes from `wander.py`, outside the model. Never swap it
for "think of some random topics".

**Generating and judging are separate passes with separate agents.** A wanderer
who knows the selection criteria starts self-censoring and collapses to the
safe option. Wanderers never see the criteria. Judges never see where an idea
came from.

**An idea is born when two distant fragments collide.** One fragment is a
summary. Minimum two.

**Do not filter while generating.** Rejects are the genre, not a failure. To
end up with ten live ideas, produce thirty to fifty.

**State an idea as a hook, not a topic.** Not "a post about context windows"
but "The model didn't forget. It had nowhere to put it."

**Keep the wild ones.** Word salad goes to a cringe log, never the bin. It is
raw material: "the machine told me to connect data labelling and radishes — and
you know what, I found the connection."

---

## Phase 0. Fill the head

Three sources with different roles. Gather them in parallel.

### 0.1 Personal archive — depth

```bash
python3 wander.py 12 50
python3 wander.py 12 50 --exclude work        # steer away from a heavy area
python3 wander.py 12 50 --max-per-area 1      # maximum spread
```

Twelve random fragments, weighted towards what has not been touched in a long
time.

**About corpus skew — important.** Files are never evenly spread: one project
can hold a third of the archive. Without a cap every third roll lands there and
you get ten ideas about the same corner. The script enforces a quota of two
fragments per area; lower it to 1 when the output feels repetitive.

If the user says "too much about X, I have moved on" — that is not about the
ideas, it is about the corpus. Add `--exclude X`.

A file opened yesterday is already in their head; the idea in it has been had.
The value is in what fell out: a note from February, a fragment of a March
meeting.

Age comes from git history, not mtime — after clones and syncs mtime lies for
half the archive.

### 0.2 What is already published — the anti-context

Pull the user's recent posts however you can: their site's feed, an export, a
platform API, or simply ask them to paste the last twenty headlines.

**This is anti-context, not inspiration.** The machine's main failure mode is
cheerfully reinventing something published last month. The list works as a
"already said" filter.

### 0.3 The outside world — freshness and a peg

Search for what happened in the last two or three weeks in the user's field.
`exa.py news "<query>" --days 14` if `EXA_API_KEY` is set, otherwise whatever
web search is available.

Two or three queries, different angles. The news is a peg to hang a thought on,
not the subject of the thought.

---

## Phase 1. Wander

Launch **five agents in parallel, in one message**. Each gets:

- **its own** `wander.py 6 40` call — different fragments are the main source
  of divergence between them;
- the shared news block;
- the list of recent topics as a do-not-repeat;
- **no quality criteria, no metrics, no virality formulas.**

Spread across minds is the second layer of entropy after different corpora:

| Agent | Model | Stance |
|---|---|---|
| 1 | strongest | causal chains: what grew out of what |
| 2 | mid | contradictions and conflicts between fragments |
| 3 | mid | the bodily, the mundane, the physical — metaphors from life, not from the industry |
| 4 | fastest | fast and wild: maximum collisions, quality irrelevant |
| 5 | strongest | what turned out to be outdated or untrue — "I used to think X, and then" |

**Wanderer prompt** (adapt to the stance):

> Here are several unrelated fragments from a personal archive and a few recent
> news items. Smash them together. Take at least two *distant* fragments and
> find what they share — not by topic, but by structure.
> Return 10 collisions. Each one:
> — **Hook**: the first line, 1–2 sentences, as it would be said out loud
> — **Collision**: what is joined to what, one line
> — **Source**: which fragments met
> Do not evaluate, do not select, do not think about usefulness or audience.
> Keep the wild ones. State a hook, not a topic.

**The final pass.** Once the agents return, launch a sixth with the collected
collisions and ask for **three wilder ones nobody reached**. Borrowed from a
working creative director: his best idea always arrived after the formal
"thanks, that's it".

Output: roughly fifty raw collisions.

---

## Phase 2. Sort the pile

Mechanically, no agents:

1. Collapse duplicates — the same collision from different agents. Two or more
   hits is a strength signal, mark it.
2. Drop anything repeating recent posts.
3. Obvious word salad goes to `cringe-log.md`. Do not delete it.
4. Everything else goes to judgement **anonymised**: no author model, no source
   fragments.

---

## Phase 3. Judge

Five judges in parallel, different models, each with **one single criterion**.
One criterion per judge — otherwise they average and everything becomes "fine".

| Judge | Single question |
|---|---|
| 1 | Is this genuinely non-obvious, or is everyone already saying it? |
| 2 | Does the hook hold the first 2.5 seconds? Does it carry 2–3 triggers: a common enemy, a conflict with received opinion, a result, intrigue, exclusivity, vividness? |
| 3 | Can this be made in one take, with no props and no graphics? |
| 4 | Would anyone forward this? To whom exactly, and why? |
| 5 | Where is the lie or the stretch here? If it rests on a fact, is the fact checkable? |

Each gives 1–5 and one line of reasoning. **Judges do not talk to each other**
and never see other scores.

Sum the scores. Ideas with **split verdicts** (one gave 5, another gave 1) are
not averaged — they get their own section. Contested is often the interesting
one; a unanimous four usually means "solid and boring".

---

## Phase 3.5. Fact-check — only for ideas resting on facts

Judge 5 reasons about plausibility but opens no sources. That is not enough: a
collision about history or someone else's company will be checked by readers,
and a wrong date costs more than the whole post earns.

So anything resting on an external fact — a date, a name, a number, someone
else's case — goes through a separate pass **before** delivery. Ideas from
personal experience skip it: they cannot be disputed.

One agent per idea, in parallel, searching in **two modes** — this is not
redundancy:

- a semantic search leaning on primary sources (`exa.py fact "..." --results 8`,
  add `--papers` for scientific claims);
- a plain web search on the same question, **deliberately phrased differently**,
  to catch disagreement.

Two different searches agreeing means the claim is solid. Disagreeing is
exactly the spot readers will bite. Open contested links and read them —
snippets often quote a retelling.

Per idea, a card:

| Field | What is checked |
|---|---|
| **Core** | A is connected to B — in one phrase |
| **Causality** | A real cause, or coincidence in time? The genre's most common error |
| **Names and dates** | Exact spellings and years. Separately: what historians dispute |
| **Numbers** | Each with a source. No source — remove the number, do not round it |
| **Sources** | At least two independent. Wikipedia is a starting point, not a source |
| **What gets misread** | Where the phrasing has a hole |

**Red flags:** a beautiful story with no primary source · "as is well known"
instead of a link · a number circulating between blogs with no origin · a plot
already covered in detail by large channels.

Verdict, one of three: **confirmed** (proceed) · **needs rephrasing** (the fact
is real but different — rewrite the hook to match the truth) · **collapsed**
(rejected, noting exactly what failed).

Do not mourn collapsed collisions. A beautiful untruth costs more than a
missing post.

---

## Phase 4. Deliver

Write to a dated file in the user's ideas folder. **Ten ideas**, each with:

- the hook, verbatim;
- the collision in one line;
- which of their existing formats or rubrics it fits (if none — say so, that
  may be a proposal for a new one);
- the judges' total and, when the verdict was split, both opinions.

Then, separately:

- **contested** — ideas the judges disagreed about, with both sides;
- **collapsed on facts** — with the reason, so the same collision is not
  reinvented next month;
- **cringe log** — a link, not the contents.

---

## Checking that the machine still works

Signs it has degenerated into a topic generator:

- ideas cluster in one area → corpus skew, lower `--max-per-area`;
- hooks read as topics ("a post about X") → the wanderers saw the criteria;
- everything scores 3–4 → judges got more than one criterion each;
- nothing lands in the cringe log → the wanderers are self-censoring, they are
  being over-instructed.

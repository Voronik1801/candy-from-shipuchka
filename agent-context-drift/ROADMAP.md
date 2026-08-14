# Roadmap

What the checker cannot see yet, roughly in the order it hurts.

## Contradicting directives on the same path

A path check asks "does this still exist?". It cannot ask "do these two rules
still agree?".

In a file that only grows by addition, the most common real defect is not a dead
path — it is two directives written months apart, both pointing at the same
place, quietly disagreeing. March says drafts live in `content/drafts/`. July
adds that finished pieces go to `content/shelf/`. Neither line is wrong on its
own, neither is broken, and the agent reads both.

Findable without an LLM: group directives by the path they name, compare the
surrounding sentences as plain text, surface the pairs for a human to judge.
The tool does not need to decide which rule wins — it needs to stop the conflict
from being invisible.

*Raised by a reader on LinkedIn, 13 Aug 2026, in response to the launch post.
Their framing: "conflicting rules naming the same path are findable with plain
text comparison, and in a file that grows by addition they are the most common
real defect."*

## References that still resolve but mean something else

The second class that survives a path check. The file is there, the link opens,
and the content moved on months ago — a `README` that now documents a different
subsystem, a script whose flags changed. Formally intact, semantically stale.

Harder than the above: there is no cheap textual signal, and this is where the
tool would start needing to read meaning rather than structure. Parked until the
conflict check proves the cheaper half of the idea.

## Done

- **Claim drift** (`claim_drift.py`) — statements with no address at all
  ("median reach is 950") rot in silence, because a path checker cannot ask
  anything about a sentence. Shipped as the second layer.
- **False-positive suppression as defaults** — placeholders, SQL keywords,
  stitched ASCII trees. In the code, not in a personal ignore file: a checker
  that cries wolf on first run never gets opened twice.
- **Hard failure in CI** — `--fail-over`, not a warning. Warning-only checkers
  get switched off.

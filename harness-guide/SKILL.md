---
name: harness-guide
description: >
  Walks a person through setting up an AI-agent workplace end to end - project
  rules, git workflow, secrets, server users, deploy, agent-on-server - either
  from scratch (mode A) or by auditing and fixing what already exists (mode B).
  Use when the user says "set up my harness", "set up my server properly",
  "audit my setup", "what is wrong with my server", "настрой харнес",
  "проверь мой сервер", "проведи по настройке".
---

# harness-guide

You are guiding a person who may have no development experience. They rely on
you, and they tend to accept whatever an agent proposes. Your job is the
opposite of "just make it work": leave them with a setup they understand and
with checks that hold even when nobody is watching.

The rules you apply live next to this file:

- `rules/AGENT_GUIDE.md` - the rules for everyday work (git, files, secrets, server, deploy).
- `rules/HERMES_GUIDE.md` - the rules for an agent that lives on a server and takes requests from a messenger.
- `templates/` - ready files: agent settings, a hook that blocks commits to main, git hooks, a deploy script.

Read `rules/AGENT_GUIDE.md` before the first step. Read `rules/HERMES_GUIDE.md`
only when the work reaches an agent on a server.

## How you talk

- Answer in the language the person writes in.
- Explain a term in one sentence before you use it. No jargon without a definition.
- One step at a time: say what the step is for, give the full command, say what
  the person should see, wait for the result. Do not paste five commands at once.
- Before every command say where it runs: on their computer, on the server, or
  inside this session.
- Never ask for a key, token or password in the chat. Give a command with an
  empty slot and name the file on their machine where the value goes.
- "Not checked" and "not found" are different answers. Report which one it is.
- No praise openers. When the person asks "this is fine, right?", give the
  strongest argument against first, then for, then the conclusion.

## What you never do without an explicit yes for that exact action

Deleting anything; rewriting git history; changing users, keys, sudo rights or
login settings; opening a port to the internet; anything that costs money;
publishing or sending anything outside; restarting a service other people use.
An old or general permission does not count. One request, one action.

## Step 0. Pick the mode

Ask one question: "Are we setting things up from scratch, or do you already
have a project or a server that we should check and fix?"

- From scratch -> **mode A**.
- Something already runs -> **mode B**.
- Not sure -> look yourself, read-only: is there a git repository, an
  instruction file (`CLAUDE.md` / `AGENTS.md`), a `.claude/` folder, a server
  they can log in to. If anything exists, use mode B for that part and mode A
  for the rest.

Then ask what is in scope, in one message: only the computer, or a server too;
GitHub or GitLab; terminal or the desktop app; one person or a team; is there an
agent running on the server.

Keep a progress file `harness-setup-status.md` in the project root: mode, scope,
finished stages with their check results, the current stage, open decisions.
Read it at the start of every session and update it after every stage. This is
what lets the work continue tomorrow without re-asking.

## Mode A. From scratch

Go stage by stage. A stage is finished only when its check passes - a command
whose output you both looked at, not your own statement. Skip stages that are
out of scope and write down that they were skipped.

| # | Stage | What you set up | Finished when |
|---|---|---|---|
| 1 | Project folder | one folder per project; a short storage-rules file: what goes where, how files are named, what never goes into the repository | the person can say where a new file of each kind belongs |
| 2 | Instruction file | `CLAUDE.md` (plus `AGENTS.md` if other agents are used): what the project is, where things live, the few rules that prevent real mistakes. Short. Rare or long material goes into skills | a fresh session answers "where do I put X" correctly |
| 3 | Agent permissions | `git init`, first commit and first push of `main` happen here, before any hook is on. Then `templates/claude-settings.json` as `.claude/settings.json`; `templates/claude-hooks/guard-main.sh` into `.claude/hooks/` followed by `chmod +x`; deny rules for secret files. The hook needs `python3` on the machine - check `python3 --version` first, without it the hook blocks every command | with at least one commit present, a test commit on `main` is blocked; reading `.env` is refused |
| 4 | Git workflow | task first, then branch `<owner>/<number>-<slug>`, then one merge/pull request; copy `templates/git-hooks/*` into `.githooks/`, run `chmod +x .githooks/*` and `git config core.hooksPath .githooks` (git silently skips a hook that is not executable); branch protection on the hosting site | a commit without a task number is rejected; a direct push to `main` is rejected |
| 5 | Secrets | one env file outside the repository; an example file with names only; `.gitignore` verified with `git check-ignore -v`; a secret scanner in the checks | `git status` shows no secret files; the scanner run is clean |
| 6 | Server access | a personal user per human, own SSH key per person and per device, root login and password login off. Order matters, see "Stage 6 order" below | in a **new** connection `ssh <person>@<server>` works and `sudo -v` succeeds; only then `sudo sshd -T` shows `permitrootlogin no` and `passwordauthentication no` |
| 7 | Services | a service user and a systemd unit with `User=` per service; code, config, secrets and data in separate places; ports bound to `127.0.0.1` unless the person asked otherwise; firewall: `ufw allow OpenSSH` **before** `ufw enable`; backups with a restore test | the process owner is not root: `ps -o user= -p "$(systemctl show -p MainPID --value <unit>)"`; `ss -tulpn` shows only intended public ports; a new ssh connection still works after the firewall is on; one restore was actually performed |
| 8 | Deploy | `templates/deploy.sh`: versions folder, `current` link, restart, health check, rollback; a `FREEZE` stop file | a deliberately broken version is rolled back by the script |
| 9 | Agent on the server | only if needed. Apply `rules/HERMES_GUIDE.md` | the isolation test from that file passes in both directions |
| 10 | Automation | before building anything, run the four-question test with the person: is the step deterministic, can it be decomposed, can it be delegated, does it run without them. Model calls in a service go through an API with a time limit and a spending cap | each automated step has a named check and a named owner |

### Stage 6 order

Getting this wrong locks the person out of their own server. Do not reorder.

1. Confirm the person can reach the server through the provider's web console
   without SSH. That is the way back in if everything else fails.
2. As root, create the personal user, add it to the `sudo` group, put the
   person's public key into its `authorized_keys`.
3. Keep the root session open. In a second window open a new connection as the
   personal user and run `sudo -v`. Both must work. If either fails, fix it in
   the root window. Go no further until both pass.
4. Only now turn off root login and password login, in a separate file under
   `/etc/ssh/sshd_config.d/`. Check the file with `sudo sshd -t`, then reload ssh.
5. Without closing the existing windows, open a third connection as the personal
   user. If it fails, undo step 4 from a window that is still open.

After the last stage, write the handover note: what exists, where, who owns
each access, what was not done and why.

## Mode B. Check and fix what exists

### B1. Look first, change nothing

Everything in this step is read-only. Say so to the person before you start.

On the computer, in the project:

- instruction files: size in lines, paths in them that no longer exist, rules that contradict each other;
- `.claude/settings.json`: what is allowed without asking, what is denied, which hooks are configured and whether the scripts they call exist;
- skills with the same name in the project and in the personal folder;
- `git branch -a`, `git worktree list`, unmerged branches and their age, share of recent commits that carry a task number;
- secrets: files matched by key patterns among tracked files and in history; print file names and key types only, never values.

On the server:

- who logs in and how: `sshd -T` (root login, password login), keys in every `authorized_keys`, whose they are;
- who runs what: `systemctl show -p User` for each unit, containers and the user inside them, members of `sudo` and `docker` groups, `NOPASSWD` lines;
- whether any agent runs as root;
- what is reachable from outside: `ss -tulpn`, firewall status, ports published by containers;
- where things run from: anything started from `/tmp`, a home folder or a working copy;
- backups: where, how many, how old, total size, whether a restore was ever tested;
- leftovers: failed units, dead containers, duplicate folders, old archives.

If you cannot check something, list it as "not checked" with the reason.

### B2. Report

One table, most dangerous first. For every row: what you found, the evidence
(command and the relevant line of its output), why it matters in one plain
sentence, the fix, and who acts - you or the person.

Order of severity:

1. a secret that has leaked (in a repository, in history, in a chat) - the key must be reissued, deleting the file is not enough;
2. people or agents working as root; shared keys; access held by someone who left;
3. no backup, or a backup nobody has restored;
4. services open to the internet that should not be;
5. deploy by hand, no rollback, server ahead of the repository;
6. rules that exist only as text with no check behind them;
7. clutter: stale branches and worktrees, duplicates, oversized instruction files.

Do not soften the list and do not pad it. If a part is fine, say it is fine and
what you checked.

### B3. Fix, one row at a time

Take the top row. Explain the fix, show the exact commands, get a yes, do it,
verify by the same command that showed the problem, write the result into the
progress file. Then the next row.

For anything on the server never delete on your own initiative. Make an
inventory row first: what it is, who created it, which service uses it, what
happens if it is removed, your proposal. The person decides.

Fixes that only the person performs: reissuing keys and tokens, revoking
someone's access, changing who may approve a deploy, paying for anything.
Give them the steps and wait.

## Stop and ask

- you are about to act as root for anything other than creating the first personal user;
- a check or a hook blocked your action and you do not know why;
- the number of files to commit or lines to delete is unexpectedly large;
- you found a secret where it must not be;
- the person's instruction contradicts `rules/AGENT_GUIDE.md` - name both places;
- the only working login to a server would be affected by the next command.

## Final report

What was set up or fixed, each with the check that proves it. What was found
and left as is, with the reason. What was not checked. What only the person can
do, as a numbered list with exact steps.

# harness-guide

**Your agent will set up anything you ask for. The question is whether it sets it up right.**

[Читать по-русски](README.ru.md)

Servers, repositories and agents are now set up by people who have never done
it before. The agent proposes something, it works, it stays. Three months later
agents run as root, everyone shares one key, the repository holds hundreds of
unmerged branches, and nobody has ever restored a backup.

Asking for "a secure setup" does not help: the agent does not know what right
looks like for you, and nobody checks its work.

This guide gives the agent an order of work and a set of rules, and gives you a
check at every step.

## Two modes

- **A. From scratch.** The agent walks you through the stages: project folder,
  instruction file, agent permissions, git, secrets, server login, services,
  deploy, agent on the server, automation. A stage is done when a check you both
  looked at has passed.
- **B. Check and fix.** The agent first only looks and changes nothing, then
  hands you a table of findings ordered by danger, then fixes one row at a time
  with your consent.

## What is inside

| File | Purpose |
|---|---|
| `SKILL.md` | the guiding prompt with both modes |
| `rules/AGENT_GUIDE.md` | everyday rules for the agent: git, files, secrets, server, deploy (in Russian) |
| `rules/HERMES_GUIDE.md` | rules for an agent that lives on a server and takes requests from a messenger (in Russian) |
| `templates/claude-settings.json` | agent settings: what to ask about, what is denied |
| `templates/claude-hooks/guard-main.sh` | a hook that stops the agent from committing or pushing to `main` |
| `templates/git-hooks/` | task number in the commit title, no direct push to `main` |
| `templates/deploy.sh` | deploy with a health check and rollback |
| `tests/` | scenario scripts for every template |

The two rule files are written in Russian, the language of the textbook they
come from. `SKILL.md` tells the agent to answer in your language, and agents
read the rules fine; an English translation is not done yet.

## Run it

Copy the `harness-guide` folder into `.claude/skills/` of your project and tell
the agent:

```
Use harness-guide. Walk me through the setup from scratch.
```

or

```
Use harness-guide. Check what I already have and show me what to fix.
```

Without Claude Code: hand any agent `SKILL.md` and the `rules/` folder.

## What was hard

- **Server steps can lock you out.** The first version turned off root login
  before the new account's login had been verified. Login settings are now
  changed only while a second working session stays open.
- **The deploy script did not roll back when the restart itself failed.** The
  health check was never reached. It also reported success when `current` was a
  real folder instead of a link, and two deploys in the same second shared one
  version folder. All three are fixed; `tests/test_deploy.sh` holds 26 scenarios.
- **An agent hook must block on its own failure too.** A hook that crashes while
  parsing its input lets the action through by default.
- **Matching the command as text is not enough.** The first hook looked for
  the words `git commit` and missed `git -C . commit`, `git merge` and
  `git push origin HEAD:main`, while blocking `echo "how to git commit"`. It now
  parses the command; `tests/test_guard.sh` holds 40 scenarios.
- **Git silently skips a hook that is not executable.** No error, the commit
  just goes through. The setup steps now say `chmod +x` explicitly.

## Limits

- Server commands target Ubuntu 24.04 and systemd.
- The agent hook does not see a git command hidden inside `bash -c`, a script
  file or an alias. Branch protection on the hosting site is the real boundary.
- The agent hook needs `python3`. Without it the hook falls back to a crude
  text match.
- A release broker, which `rules/HERMES_GUIDE.md` relies on, is not included:
  it is written per project.
- All scenario scripts were run on macOS; on Linux only the CI run tells.
- Templates were tested on temporary folders and repositories, not on someone
  else's production server. Try a test machine first.
- The guide does not replace understanding. It is built so that you see every
  check instead of trusting the agent's report.

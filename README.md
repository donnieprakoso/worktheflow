```
 _       __           __  ________         ________
| |     / /___  _____/ /_/_  __/ /_  ___  / ____/ /___ _      __
| | /| / / __ \/ ___/ //_// / / __ \/ _ \/ /_  / / __ \ | /| / /
| |/ |/ / /_/ / /  / ,<  / / / / / /  __/ __/ / / /_/ / |/ |/ /
|__/|__/\____/_/  /_/|_|/_/ /_/ /_/\___/_/   /_/\____/|__/|__/

  WorkTheFlow - workflow engine for AI coding tools
```

**Note:**
- Use `wtf` when you're actually building something.
- Use `wf` when you're demoing this or presenting in a meeting, so you don't have to say "wtf" out loud in front of your manager.

## What this is

`wtf` is a workflow engine for AI coding agents ([Claude Code](https://claude.com/claude-code), [Kiro](https://kiro.dev), [OpenCode](https://opencode.ai)). You write the workflow as YAML — states, transitions, guards, approval gates. `wtf` holds the run's state and decides what's allowed next. It never does the work itself — the agent does that in its own session, then `wtf` checks the claim against the guards you wrote down.

Three ways a state can move on: plain sequential transitions, **Choice** (guards pick the next step automatically once they already tell the paths apart), and **Parallel** (fork into independent branches, join once they all finish). State lives in `.wtf/`, so a run can sit waiting on a human approval for as long as it needs to — days, weeks, whatever.

## Getting started

Installed via [uv](https://docs.astral.sh/uv/) — one command, no separate dependency step:

```bash
# Install (also gives you `wf` — see the note above)
uv tool install --editable /path/to/wtf
```

Then link the `/wtf` skill into whichever tool you use (one-time, per machine):

```bash
./skills/claude.sh link      # Claude Code
./skills/kiro.sh link        # Kiro
./skills/opencode.sh link    # OpenCode
```

From there, you don't need to remember any commands — just talk to the skill, and it drives `wtf` for you:

| Say this | When | Example |
|---|---|---|
| `/wtf init` | Starting a new project, no `.wtf/` yet. | `/wtf init` |
| `/wtf build` | You have an idea for a workflow and want to write it down — all at once, or one question at a time. | `/wtf build a workflow that reviews a PR, runs tests, then waits for my approval before merging` |
| `/wtf run` | A workflow already exists and you want to start it, or pick up a run that's waiting. | `/wtf run the pr-review workflow` |

### For those who want to run it manually

```bash
# Bootstrap a project
wtf init

# Author a workflow — by hand in .wtf/workflows/<name>.yaml
wtf validate <name>
wtf graph <name> --preview   # see it as a diagram before running it

# Run it
wtf start <name> --input '{"key": "value"}'
wtf next                     # what to do, and the state's handoff file to read/write
wtf done                     # advance once the work is done
wtf log                      # the full history of a run
```

## Limitations

- **Single user, no identity.** `roles` on an approval gate is advisory only — `wtf approve` works for anyone who runs it.
- **Branches can't be individually gated.** Only a fork's own join transition can require approval; a transition inside a branch cannot. No nested forks.
- **No engine-managed data passing between states.** Each state gets its own handoff file (`.wtf/runs/<run_id>/states/<name>.md`) by convention, not enforcement — states exchange data by reading/writing files directly, not through the engine.
- **`tools`/`skills` hints are advisory**, never checked against what the agent actually does.
- **No success/fail distinction on terminal states** — both just end the run as `completed`; only the state's name tells you which outcome it was.
- **The run-state checksum has no secret key.** It catches accidental edits to `state.json`, not a determined adversary.
- Only the current **list-based** schema shape is supported — no ASL-style map shape.

## Built using Spec-First TDD 🤘

Every feature here was built through [Spec-First TDD](https://github.com/donnieprakoso/spec-first-tdd). 

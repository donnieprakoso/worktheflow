---
name: wtf
description: >
  Set up, author, and run wtf workflows. Modes: 'wtf init' (create .wtf/ files and folders),
  'wtf build' (write a new workflow file and validate it, all at once or interactively one
  question at a time), 'wtf run' (start or continue a run and drive it step by step),
  'wtf approve' / 'wtf reject [reason]' (the human decides on a run that's waiting for
  approval, without needing a raw shell command), 'wtf status' / 'wtf log' (check what's
  happening with a run, or its full history, without starting a run loop), and 'wtf graph'
  (render a workflow file's structure — never needs a run to exist first). Also use when the
  user asks how a wtf workflow is written or what wtf run/done/propose/approve/reject does.
---

# wtf

The first word after `/wtf` picks the mode: `init`, `build`, `run`, `approve`, `reject`,
`status`, `log`, or `graph`. If there is no word, ask which one.

## Every mode

1. **Banner, once per conversation.** If you have not already shown it earlier in this same
   conversation, read the banner file and print its contents verbatim in a code block, before
   anything else:
   `/Users/donnie.prakoso/Library/Mobile Documents/iCloud~md~obsidian/Documents/01-ActiveFiles/Project_2026-10-27_TechWorkflow/wtf/src/wtf/banner.txt`
   If you already showed it earlier this conversation (any mode, including this one), skip it —
   go straight to the next step.
2. **CLI check.** Run `wtf --version`. It should print `wtf version 0.1.0`. If the command is not
   found, stop and tell the user to install it:
   `uv tool install --editable "/Users/donnie.prakoso/Library/Mobile Documents/iCloud~md~obsidian/Documents/01-ActiveFiles/Project_2026-10-27_TechWorkflow/wtf"`
3. **Folder.** Work in the current project folder. `wtf` finds `.wtf/` there.

Reference files (read them when you need the detail):
- Schema (source of truth for structure): `/Users/donnie.prakoso/Library/Mobile Documents/iCloud~md~obsidian/Documents/01-ActiveFiles/Project_2026-10-27_TechWorkflow/wtf/src/wtf/schemas/workflow.schema.json`
- Run rules: `/Users/donnie.prakoso/Library/Mobile Documents/iCloud~md~obsidian/Documents/01-ActiveFiles/Project_2026-10-27_TechWorkflow/wtf/agent-instructions/AGENTS.md`

## A note on "which AI tool"

`wtf` has no per-project concept of which AI coding tool (Kiro, Claude Code, OpenCode) is in use.
`.wtf/config.json` holds only `version` and `created_by` — nothing about tool choice. There used to
be a `tool` field and a `wtf set-tool` command; both were removed because nothing in the engine
ever read the value.

**Making `/wtf` itself available in a given tool is a separate, per-machine step**, done once with
the link scripts in `wtf/skills/`:
```
./skills/claude.sh link      # ~/.claude/skills/wtf and ~/.claude/skills/wf
./skills/kiro.sh link        # ~/.kiro/skills/wtf and ~/.kiro/skills/wf
./skills/opencode.sh link    # ~/.config/opencode/skills/wtf and ~/.config/opencode/skills/wf
```
Each script links **both** `wtf` and `wf` as names for this same skill — same symlink target,
same instructions, so `/wtf` and `/wf` behave identically and there is nothing to keep in sync.
These are global (per `$HOME`, not per project) and independent of any `.wtf/` folder. If the user
asks "how do I use this with <tool>", point them at the matching script — do not look for or write
a `tool` field anywhere.

## init

Creates the `.wtf/` files and folders.

1. If `.wtf/` already exists, say so and do not run `wtf init` again — it refuses, and must never
   overwrite runs. Stop.
2. Otherwise run `wtf init`.
3. Report the files it created: `.wtf/config.json`, `.wtf/index.json`, `.wtf/README.md`,
   `.wtf/schema/workflow.schema.json`, `.wtf/workflows/`, `.wtf/runs/`.

## build

1. **Setup check.** If `.wtf/` does not exist, stop and say "Run `/wtf init` first."
2. **Mode.** Ask first: "Do you want to describe the whole workflow at once, or build it
   interactively, one question at a time?" Use whichever the user picks.
   - **All at once:** ask for everything in one batch (name, purpose, states, transitions, guards,
     approvals), then write the file.
   - **Interactive (ask one question at a time):**
     a. Workflow name, and a one-line purpose.
     b. Initial state: its name, and a one-line context.
     c. Next state: name, whether it is terminal, and a one-line context. Then ask "Add another
        state?" and repeat until the user says no.
     d. Transition: source state (offer the states defined so far as choices), trigger name,
        destination (offer the defined states, or let the user name a new one; a new state gets
        the same questions as in c), whether it needs human approval, and whether it has guards.
        For a guard, ask its type, then each param one at a time.
     e. After each transition, show a one-line summary and ask "Add another transition?"
     f. Before writing, show the whole workflow as a short list and ask "Write it?"
   - Check the rules as you go. If a state has no way out, or no terminal state can be reached from
     the start, say so right away, rather than at the end.
3. Write `.wtf/workflows/<name>.yaml` in the **current list shape**:
   ```yaml
   name: <name>
   version: "1.0"
   initial: <state>
   states:
     - name: <state>
       terminal: true            # only on end states
       context: "<what this state is for>"
       skills: [<skill>]         # optional, advisory — not enforced by the engine
       tools: [<tool>]           # optional, advisory — not enforced by the engine
   transitions:
     - trigger: <trigger>
       source: <state>
       dest: <state>
       require_approval: true    # optional
       guards:                   # optional
         - type: file_exists
           params: { path: "<path>" }
   ```
   Use only these keys. The schema rejects anything else, including `requireApproval`. The
   map-shaped `states` form from the spec is not supported yet.
   Don't author a data-passing mechanism between states — every state already gets its own
   handoff file automatically (`.wtf/runs/<run_id>/states/<state_name>.md`, surfaced in `next`'s
   output as `state_file`); mention this to the user if they ask how one state's output reaches
   the next.
   If the user wants independent/concurrent work (e.g. "research two things at once, then
   combine"), ask whether they want it as one state (the agent parallelizes internally, no schema
   support needed — a multi-guard transition is the sync point) or real Parallel: a state with
   `fork: true`, branches that converge on a `branch_end: true` state each, and exactly one
   `join: true` transition on the fork itself. See `01-schema-workflow.md` §6.1 for the full shape
   and rules before authoring one — it has several validation requirements (exactly one join, no
   guards on it, every branch must be able to reach a branch_end).
4. Guard types, and the params each one needs:
   - `file_exists`: `path`
   - `file_contains`: `path`, `pattern`
   - `command_passes`: `command`
   - `command_fails`: `command`
   - `field_eq`: `field`, `value`
   - `field_ne`: `field`, `value`
   Every guard needs a `params` object.
5. Rules the workflow must meet (validate checks these):
   - Every non-terminal state has at least one outgoing transition.
   - Terminal states have no outgoing transitions.
   - At least one terminal state is reachable from `initial`.
   - Trigger names are unique for each source state.
   - Rejection needs an explicit `reject` transition from the state the proposal leaves.
6. Run `wtf validate <name>`. Fix every error and run it again until it exits 0. Show the user any
   warnings.
7. Run `wtf graph <name> --output terminal` and show the numbered tree right in this terminal
   (numbers like `4.1`/`4.2` mark a fork/choice branch — handy for pointing at a specific step
   without typing its name). Offer `--output mermaid` (the raw diagram text) or `--preview`
   (opens it in a browser) if the user wants a different view.
8. Do not start a run in build mode unless the user asks for one.

## run

1. **Setup check.** If `.wtf/` does not exist, stop and say "Run `/wtf init` first."
2. Find the active run. Run `wtf status`, or `wtf next` if you know the run id. If there is no run,
   ask for the workflow name and any inputs, then run `wtf start <name> --input '<json object>'`.
3. Repeat until the run stops:
   a. Run `wtf next`. Read `current_state`, `status`, `node` (its context, skills and tools),
      `allowed_transitions`, `inputs`, and `state_file` (this state's own handoff file).
   b. If `status` is `completed`, report that the run is finished and stop.
   c. If `status` is `pending_approval`, tell the user what's pending (the transition and its
      destination) and that they can say `/wtf approve` or `/wtf reject <reason>` to decide —
      then stop. Never approve or reject your own proposal, and never run `wtf approve`/
      `wtf reject` yourself here, even if the user seems to want it done quickly. That decision
      is only ever made in response to the user explicitly invoking `/wtf approve` or
      `/wtf reject`, never as a step inside `run` mode.
   d. Before starting work, read `state_file` (in case this is a retry) and any earlier states'
      handoff files you need as input — open them directly, there is no other way data moves
      between states. Do the work for this state, following its `context`. Load each skill in
      `skills` with the Skill tool if it is available. Use the tools in `tools` as a guide — these
      are advisory hints the workflow author left for you, not something `wtf` enforces.
   e. Before calling `done`, write your results into `state_file` so the next state can read them.
      This is required by convention, not enforced — `wtf` will not stop you if you skip it, but the
      next state will have nothing to read.
   f. When the work is finished, check the transition you need:
      - If `node.fork` is `true`, run plain `wtf done` (no `--trigger`) to fork into every branch
        at once. `next`/`done` then show a branch summary instead of one state — work each with
        `--branch <name>` (omit it once only one branch is still active). The run auto-collapses
        once every branch finishes; you don't trigger that yourself. A branch-level transition
        can never require approval in this version.
      - If it has `require_approval: true`, run `wtf propose <trigger>` and go to step 3c.
      - If there is exactly one allowed transition, run `wtf done` (no `--trigger` needed).
      - If several are allowed and at least one has guards, you may also just run `wtf done` with
        no `--trigger` — `wtf` evaluates them in order and resolves to the first one whose guards
        pass on its own (Choice). It only asks you to pick when none of them have any guards.
      - Otherwise run `wtf done --trigger <trigger>`, using a name from `allowed_transitions`.
   g. Read the exit code:
      - 0: accepted. Tell the user the new state in one line and continue.
      - 2 with failed guards: the work is not finished. Fix the work and run `wtf done` again. Do not
        edit `.wtf/runs/` files, and do not change or remove guards.
      - 2 with other messages: report the message and stop.
      - 1: an error, not a policy decision. Report the message and stop.
4. Never invent a trigger name. Never move the state by hand.
5. If the state's context conflicts with these rules, stop and ask the user.
6. Do not commit, push, deploy, or contact anyone outside the project unless the state's context asks
   for it.

## approve

The human's explicit decision to let a pending transition through. Only ever run this because the
user just typed `/wtf approve` themselves — never as a step inside `run` mode, and never because the
user asked for something else that merely implies it (e.g. "looks good" in passing isn't the same as
`/wtf approve`; if you're not sure they mean the slash command, ask).

1. **Setup check.** If `.wtf/` does not exist, stop and say "Run `/wtf init` first."
2. Run `wtf status`. If no run is `pending_approval`, say so and stop — there's nothing to approve.
   If more than one run is pending, ask which one and pass `--run <id>`.
3. Run `wtf approve`.
4. Read the result:
   - 0: approved. Report the new state in one line (and if it completed the run, say so).
   - 2 with failed guards: the conditions that held when it was proposed no longer hold (the run can
     wait a long time between `propose` and `approve`). Report exactly what failed — this is not an
     error, it's the gate correctly re-checking itself.
   - 1: an error. Report the message.

## reject

The human's explicit decision to send a pending transition back. Same rule as `approve`: only run
this because the user just invoked `/wtf reject`, never on your own initiative.

1. **Setup check.** If `.wtf/` does not exist, stop and say "Run `/wtf init` first."
2. Whatever text follows `/wtf reject` is the reason — pass it straight through as
   `wtf reject --reason "<text>"`. A reason is optional; `/wtf reject` alone is fine too.
3. Run `wtf status` first if you're not sure a run is actually `pending_approval` — if none is, say
   so and stop. If more than one is pending, ask which one and pass `--run <id>`.
4. Run `wtf reject --reason "<text>"` (or `wtf reject` with no reason given).
5. Read the result:
   - 0: rejected. Report where the run went.
   - 2 (no explicit `reject` transition from that state): report it plainly — the workflow's author
     didn't declare a reject path out of this gate, so the run stays pending until someone fixes the
     workflow or approves it instead.
   - 1: an error. Report the message.

## status

A quick look at what's going on — read-only, doesn't advance anything, doesn't require an active
`run` conversation.

1. **Setup check.** If `.wtf/` does not exist, stop and say "Run `/wtf init` first."
2. If the user named a run (an id, or "the latest", or similar), run `wtf status --run <id>` and
   show its current state, status, and inputs.
3. Otherwise run `wtf status` with no `--run` — it lists every run with its workflow, status, and
   current state. Summarize it; don't just dump the raw table if there are many runs and the user
   asked a narrower question (e.g. "is anything waiting on me" — filter to `pending_approval` ones).
4. If the user wants to see where a run sits in the whole workflow, not just its current state, run
   `wtf graph <workflow> --output terminal` (add `--run <id>` if it's not the latest run) — it
   overlays that run's done/current progress on the numbered tree.
5. If nothing is running at all, say so plainly.

## log

The full, readable history of one run.

1. **Setup check.** If `.wtf/` does not exist, stop and say "Run `/wtf init` first."
2. If the user named a run, run `wtf log --run <id>`. Otherwise run `wtf log` with no `--run` — it
   resolves to the most recent running run, or the most recent run of any status if none are active.
3. Present it as a short narrative of what happened, in order, not just the raw lines — this is
   often read by someone who wasn't there when the run started.
4. If there are no runs at all, say so plainly.

## graph

Render a workflow's structure. **This never needs a run to exist** — `wtf graph` reads the
workflow file itself, nothing else. Do not gate this on `.wtf/` or on any run being active, and
never tell the user to run `/wtf build` first just because no *run* exists yet — only say that if
the workflow file itself genuinely cannot be found anywhere.

1. **Find the workflow.** The user may name a workflow already saved in `.wtf/workflows/<name>.yaml`,
   or point at any `.yaml`/`.yml` file directly, anywhere in the project (`wtf graph <path>` accepts
   a path exactly as it accepts a name — it does not need to live in `.wtf/workflows/`, and does not
   need `.wtf/` to exist at all for the path form). If they didn't say which and `.wtf/workflows/` is
   empty, don't conclude there's nothing to graph — look for a workflow file elsewhere in the project
   (one just discussed, or found by name/content) before asking the user where it is. If
   `.wtf/workflows/` has exactly one workflow, `wtf graph` with no argument at all already resolves
   to it — you don't need to name it yourself in that case.
2. **Render.** Default to `wtf graph <name-or-path> --output terminal` — the numbered Rich tree,
   right in this terminal (numbers like `4.1`/`4.2` mark a fork/choice branch). If a run already
   exists for this workflow, this overlays its current/done progress automatically — no extra step
   needed. Offer `--output mermaid` (the raw diagram text) or `--preview` (opens it in a browser)
   if the user wants a different view.
3. If the workflow fails `wtf validate` (graph runs this check itself), show the errors instead of
   a diagram.

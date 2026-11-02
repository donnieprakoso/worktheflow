# Workflow rules (wtf)

This project runs its work through a `wtf` workflow. `wtf` holds the state and
decides which transitions are allowed. You do the work inside the current step.
`wtf` never does the work for you, and you never move the state by hand.

## Every step

1. Run `wtf next` to see the current state, its context, its `skills`/`tools`
   hints, and the allowed transitions. Do this before you act, and again if you
   lose track.
2. Do only what the current state's context asks for. `skills` and `tools` are
   advisory hints the workflow author left for you — `wtf` does not check
   whether you followed them, but you should.
3. When the step's work is finished, advance with
   `wtf done --trigger <trigger>`. If the state has exactly one transition, you
   may leave out `--trigger`. You may also leave it out when several
   transitions exist but at least one has guards — `wtf` evaluates them in
   order and resolves to the first one whose guards pass on its own (Choice).
   It only asks you to pick when no candidate has any guards at all.
4. Use only trigger names that appear in `allowed_transitions`. Never invent one.
5. Read and write your state's handoff file at the `state_file` path `wtf next`
   gives you (`.wtf/runs/<run_id>/states/<state_name>.md`). Before starting
   work, read your own file (in case this is a retry) and any earlier states'
   files you need as input. Before calling `done`, write your results into
   your own file so the next state can read them — this replaces passing data
   through the engine. Required by convention; `wtf` does not block you if you
   skip it, but the next step will have nothing to read.

## Parallel (if the current state is a fork)

- If `wtf next` shows the current state has `fork: true`, run plain `wtf done`
  (no `--trigger`) to fork into every branch at once. You'll then get a
  summary of active branches instead of one state.
- Work each branch independently with `--branch <name>` on `next`/`done`. If
  only one branch is still active, `--branch` may be omitted.
- The run auto-collapses once every branch reaches its own end — you don't
  need to do anything to trigger that.
- A branch-level transition can never require approval in this version —
  only the whole fork's own join can be gated. `propose`/`approve`/`reject`
  don't work while branches are still active.

## Approval gates

- If a transition shows `require_approval: true`, run
  `wtf propose <trigger>` and stop. A person must then run `wtf approve`, or
  `wtf reject --reason "<why>"`.
- Never approve or reject your own proposal.
- A run that is pending approval is not finished. Do not propose again while it
  waits.

## When something fails

- Exit 2 from `wtf done` with failed guards means the work is not finished yet.
  Fix the work and run `wtf done` again. Do not edit `.wtf/runs/` files, and do
  not change or remove guards to get past them.
- Exit 2 with "several transitions" means you must pass `--trigger` with one of
  the listed names.
- Exit 1 is an error, not a policy decision. Report it to the user with the
  message.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Accepted |
| 2 | Rejected by policy (a guard failed, a gate is pending, or the transition is not allowed) |
| 1 | Error |

## Before you start a workflow

- Run `wtf validate <workflow>` after any edit to a workflow file. Fix every
  error before you start a run.
- Use `wtf start <workflow> --input '<json object>'` to begin a run. Check
  `wtf status --run <id>` for the inputs and the current state.

## Scope

- Do not commit, push, deploy, or contact anyone outside this project unless the
  current state's context asks for it.
- If the state's context and these rules conflict, stop and ask the user.

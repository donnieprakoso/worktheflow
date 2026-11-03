"""wtf CLI."""

import json
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from . import __version__
from . import preview
from .utils import get_wtf_dir, ensure_dir, state_file_path
from .engine import WtfEngine
from .graph import to_mermaid
from .graphterm import build_tree
from .schema import SchemaValidator, read_schema_text

app = typer.Typer(name="wtf", help="WorkTheFlow - strict policy-enforcing workflow engine")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"wtf version {__version__}")
        raise typer.Exit()


# Warm gradient, top to bottom, for the banner's art lines. Plain-text banner.txt
# (no color) is the single source of truth; the skill prints that file verbatim
# in a markdown code block, where ANSI codes would just show as garbage. Rich
# auto-disables color here too when stdout isn't a real terminal (tests, pipes).
_BANNER_GRADIENT = ["gold1", "orange1", "dark_orange", "orange_red1", "red1"]


def _print_banner() -> None:
    raw = files("wtf").joinpath("banner.txt").read_text().rstrip("\n")
    art, _, tagline = raw.partition("\n\n")
    for i, line in enumerate(art.splitlines()):
        color = _BANNER_GRADIENT[min(i, len(_BANNER_GRADIENT) - 1)]
        console.print(Text(line, style=f"bold {color}", no_wrap=True), highlight=False)
    console.print()
    if tagline.strip():
        console.print(Text(tagline, style="bold"), highlight=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """WorkTheFlow - strict policy-enforcing workflow engine."""
    if ctx.invoked_subcommand is None:
        _print_banner()
        typer.echo("")
        typer.echo(ctx.get_help())


# Templates written by `wtf init`. Kept at module level so the bootstrap
# logic reads as a list of steps rather than a wall of literals.
INIT_SUBDIRS = ("workflows", "runs", "schema")

EMPTY_INDEX = {"runs": []}

README_TEXT = """# .wtf/

This directory contains wtf (WorkTheFlow) workflow state and definitions.

## Structure
- `config.json` - Project configuration
- `workflows/` - Workflow definitions (.yaml or .json)
- `runs/` - Per-run state and event logs
- `schema/` - JSON schema for validation
- `index.json` - Run index (auto-generated)

## Usage
```bash
wtf validate <workflow>  # Validate a workflow
wtf start <workflow>     # Start a new run
wtf status              # Check run status
wtf next                # Get next action
wtf done                # Mark current step done
wtf propose             # Propose transition (for gates)
wtf approve             # Approve pending transition
wtf reject              # Reject pending transition
wtf list                # List all runs
wtf log                 # Show a run's recorded event history
```
"""


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def _first(items, default=None):
    """The first item in `items`, or `default`. Not the builtin `next()`: the
    `wtf next` command is itself a module-level function named `next`, which
    shadows the builtin everywhere else in this file."""
    for item in items:
        return item
    return default


def _fail(message: str, code: int) -> None:
    """Print an error line without Rich markup or wrapping, then exit with code."""
    console.print(f"[red]Error:[/red] {escape(message)}", soft_wrap=True)
    sys.exit(code)


def _resolve_run(engine: WtfEngine, run_id: Optional[str], status: str) -> Optional[str]:
    """Return run_id if given; otherwise the most recent run with `status`."""
    if run_id:
        return run_id
    for r in reversed(engine.store.list_runs()):
        if r["status"] == status:
            return r["run_id"]
    return None


def _pick_run(engine: WtfEngine, run_id: Optional[str], status: str) -> Optional[str]:
    """Like _resolve_run, but falls back to the most recent run of any status.

    The fallback lets a finished run report 'already completed' instead of 'not found'.
    """
    picked = _resolve_run(engine, run_id, status)
    if picked:
        return picked
    runs = engine.store.list_runs()
    return runs[-1]["run_id"] if runs else None


def _load_run_checked(engine: WtfEngine, run_id: str) -> Dict[str, Any]:
    """Load a run's state. If its checksum does not match, warn and log an
    integrity_warning event, but still return the state — never a hard block.

    Call this once, at the point a command first loads an existing run to act
    on it. Do not call it again for an internal re-load of state this same
    command just wrote (save_run always refreshes the checksum, so that
    re-load would always pass anyway)."""
    state = engine.store.load_run(run_id)
    if not engine.store.verify_integrity(state):
        console.print(
            f"[yellow]⚠ Warning:[/yellow] run {run_id}'s state.json does not match its "
            f"recorded checksum — it may have been edited outside of wtf.",
            soft_wrap=True,
        )
        engine.store.append_event(run_id, {
            "type": "integrity_warning",
            "message": "state.json checksum did not match its recorded value",
        })
    return state


@app.command()
def init():
    """Bootstrap .wtf/ folder in current project."""
    wtf_dir = get_wtf_dir(Path.cwd())
    if wtf_dir.exists():
        _fail(".wtf/ already exists here, so init will not overwrite it.", 2)

    ensure_dir(wtf_dir)
    for sub in INIT_SUBDIRS:
        ensure_dir(wtf_dir / sub)

    _write_json(wtf_dir / "config.json", {"version": "1.0", "created_by": "wtf"})
    (wtf_dir / "schema" / "workflow.schema.json").write_text(read_schema_text())
    (wtf_dir / "README.md").write_text(README_TEXT)
    _write_json(wtf_dir / "index.json", EMPTY_INDEX)

    console.print("[green]✓[/green] Initialized .wtf/ in current directory")
    console.print(f"  Created: {wtf_dir}")


@app.command()
def validate(workflow: str):
    """Validate a workflow definition against the schema."""
    engine = WtfEngine()
    try:
        wf = engine.load_workflow(workflow)
    except Exception as e:
        _fail(str(e), 1)

    errors, warnings = SchemaValidator().check(wf)
    if errors:
        console.print("[red]Validation failed:[/red]", soft_wrap=True)
        for e in errors:
            console.print(f"  - {escape(e)}", soft_wrap=True)
        sys.exit(1)

    console.print(f"[green]✓[/green] Workflow '{workflow}' is valid", soft_wrap=True)
    for w in warnings:
        console.print(f"[yellow]Warning:[/yellow] {escape(w)}", soft_wrap=True)


_WORKFLOW_SUFFIXES = {".yaml", ".yml", ".json"}


def _load_for_graph(engine: WtfEngine, arg: str) -> dict:
    """A path if it has a workflow suffix or a separator; otherwise a workflow name."""
    if Path(arg).suffix in _WORKFLOW_SUFFIXES or "/" in arg:
        path = Path(arg)
        if not path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {arg}")
        return engine.validator.load_workflow(path)
    return engine.load_workflow(arg)


def _derive_run_view(state: Dict[str, Any], events: List[Dict[str, Any]]) -> Tuple[set, set]:
    """Current/completed state-name sets for `graph --output terminal`, derived
    from a run's recorded events (no engine-managed history field exists to
    read directly). A forked run's `branches` yields one current state per
    active branch instead of a single one."""
    completed = set()
    for e in events:
        et = e.get("type")
        if et == "run_started":
            completed.add(e["initial_state"])
        elif et in ("transition", "joined", "rejected") and "to" in e:
            completed.add(e["to"])
        elif et == "forked":
            completed.add(e["from"])
        elif et == "approved":
            to = (e.get("transition") or {}).get("to")
            if to:
                completed.add(to)

    if state.get("branches"):
        current = {b["current_state"] for b in state["branches"].values()}
    elif state.get("current_state"):
        current = {state["current_state"]}
    else:
        current = set()

    completed -= current
    return current, completed


def _graph_run_view(engine: WtfEngine, workflow_arg: str, run_id: Optional[str]) -> Tuple[set, set]:
    """Resolve the current/completed sets to overlay on `graph --output
    terminal`. No run found for this workflow: both sets empty (bare
    structure, not an error — a workflow can be graphed before it's ever run)."""
    if run_id:
        try:
            state = _load_run_checked(engine, run_id)
        except FileNotFoundError:
            _fail(f"Run not found: {run_id}", 1)
    else:
        name_guess = Path(workflow_arg).stem
        matches = [r for r in engine.store.list_runs() if r["workflow"] in (workflow_arg, name_guess)]
        if not matches:
            return set(), set()
        chosen = _first((r for r in reversed(matches) if r["status"] == "running"), matches[-1])
        state = _load_run_checked(engine, chosen["run_id"])

    events = engine.store.load_events(state["run_id"])
    return _derive_run_view(state, events)


@app.command()
def graph(
    workflow: str = typer.Argument(..., help="Workflow name in .wtf/workflows/, or a path to a workflow file."),
    preview_diagram: bool = typer.Option(False, "--preview", help="Render the diagram and open it in the default browser. Only applies to --output mermaid/html."),
    output: str = typer.Option("mermaid", "--output", help="mermaid (default, stdout), terminal (Rich tree, this terminal), or html (browser preview)."),
    run_id: Optional[str] = typer.Option(None, "--run", help="Run ID to overlay progress from. Only applies to --output terminal; default is the latest run for this workflow, if any."),
):
    """Render a workflow's structure. Output only by default; --output terminal
    additionally overlays a run's progress, when one exists, but never changes it."""
    if output not in ("mermaid", "terminal", "html"):
        _fail(f"--output must be one of: mermaid, terminal, html (got '{output}')", 1)
    if preview_diagram and output == "terminal":
        _fail("--preview has no effect with --output terminal", 1)
    if run_id and output != "terminal":
        _fail("--run only applies with --output terminal", 1)

    engine = WtfEngine()
    try:
        wf = _load_for_graph(engine, workflow)
    except Exception as e:
        _fail(str(e), 1)

    errors, _ = SchemaValidator().check(wf)
    if errors:
        console.print("[red]Validation failed:[/red]", soft_wrap=True)
        for e in errors:
            console.print(f"  - {escape(e)}", soft_wrap=True)
        sys.exit(1)

    if output == "terminal":
        current, completed = _graph_run_view(engine, workflow, run_id)
        console.print(build_tree(wf, current, completed))
        return

    mermaid_text = to_mermaid(wf)
    print(mermaid_text, end="")
    if output == "mermaid" and not preview_diagram:
        return

    name = Path(workflow).stem
    html_path = preview.write_preview(get_wtf_dir(Path.cwd()), name, mermaid_text)
    if not preview.can_open_browser():
        console.print(f"No display found. Open this file in a browser: {escape(str(html_path))}", soft_wrap=True)
        return
    if preview.open_in_browser(html_path):
        console.print(f"Opened preview in browser: {escape(str(html_path))}", soft_wrap=True)
    else:
        console.print(f"Could not open a browser. Open this file yourself: {escape(str(html_path))}", soft_wrap=True)


@app.command()
def start(workflow: str, input_json: str = typer.Option("{}", "--input", help="Run inputs as a JSON object")):
    """Start a new workflow run at the workflow's initial state."""
    if not get_wtf_dir(Path.cwd()).is_dir():
        _fail("No .wtf/ folder in this directory. Run 'wtf init' first.", 1)

    try:
        inputs = json.loads(input_json)
    except json.JSONDecodeError as e:
        _fail(f"--input is not valid JSON: {e}", 1)
    if not isinstance(inputs, dict):
        _fail("--input must be a JSON object", 1)

    engine = WtfEngine()
    try:
        wf = engine.load_workflow(workflow)
    except Exception as e:
        _fail(str(e), 1)

    errors = engine.validator.validate(wf)
    if errors:
        console.print("[red]Invalid workflow:[/red]", soft_wrap=True)
        for e in errors:
            console.print(f"  - {escape(e)}", soft_wrap=True)
        sys.exit(1)

    run_id = engine.store.create_run(workflow, inputs)
    state = engine.store.load_run(run_id)
    state["current_state"] = wf["initial"]
    engine.store.save_run(run_id, state)
    engine.store.append_event(run_id, {
        "type": "run_started",
        "workflow": workflow,
        "initial_state": wf["initial"],
        "inputs": inputs,
    })

    console.print(f"[green]✓[/green] Started run {run_id}")
    console.print(f"  Workflow: {workflow}")
    console.print(f"  Current state: {wf['initial']}")
    _show_next(engine, run_id, wf)


def _show_next(engine: WtfEngine, run_id: str, workflow: Optional[dict] = None, branch: Optional[str] = None):
    state = engine.store.load_run(run_id)
    if workflow is None:
        workflow = engine.load_workflow(state["workflow"])

    if state.get("branches"):
        if branch is None:
            result = {
                "run_id": run_id,
                "status": state["status"],
                "forked_from": state.get("fork_origin"),
                "branches": {
                    name: {"current_state": b["current_state"], "status": b["status"]}
                    for name, b in state["branches"].items()
                },
                "next_action": "Pass --branch <name> to act on one branch, e.g. 'wtf next --branch <name>'.",
            }
            print(json.dumps(result, indent=2))
            return
        if branch not in state["branches"]:
            _fail(f"No such branch '{branch}'.", 2)
        current = state["branches"][branch]["current_state"]
        branch_status = state["branches"][branch]["status"]
    else:
        current = state["current_state"]
        branch_status = None

    node = None
    for n in workflow["states"]:
        if n["name"] == current:
            node = n
            break

    allowed_trans = engine.get_allowed_transitions(workflow, current)

    if state["status"] == "completed":
        next_action = "Run completed. No further steps."
    elif branch_status == "branch_complete":
        next_action = "This branch is complete. Waiting for the other branches to join."
    else:
        next_action = "Use 'wtf done' to complete current step, or 'wtf propose <trigger>' for gated transitions"

    result = {
        "run_id": run_id,
        "branch": branch,
        "current_state": current,
        "status": branch_status if branch is not None else state["status"],
        "node": node,
        "allowed_transitions": [
            {"trigger": t["trigger"], "dest": t["dest"], "require_approval": t.get("require_approval", False)}
            for t in allowed_trans
        ],
        "inputs": state.get("inputs", {}),
        "state_file": str(state_file_path(Path(".wtf"), run_id, current)) if current else None,
        "next_action": next_action,
    }
    print(json.dumps(result, indent=2))


@app.command()
def next(
    run_id: Optional[str] = typer.Option(None, "--run", help="Run ID"),
    branch: Optional[str] = typer.Option(None, "--branch", help="Branch to show, once a run has forked"),
):
    """Get next action for current run."""
    engine = WtfEngine()
    try:
        if run_id is None:
            runs = engine.store.list_runs()
            if not runs:
                console.print("[yellow]No runs found[/yellow]")
                return
            run_id = _resolve_run(engine, None, "running") or runs[-1]["run_id"]

        wf = engine.load_workflow(_load_run_checked(engine, run_id)["workflow"])
        _show_next(engine, run_id, wf, branch)
    except Exception as e:
        _fail(str(e), 1)


def _resolve_transition(
    engine: WtfEngine,
    wf: Dict[str, Any],
    current: str,
    trigger: Optional[str],
    inputs: Dict[str, Any],
) -> Tuple[Dict[str, Any], str, bool, List[str]]:
    """Resolve which transition `done` should take from `current`. Returns
    (trans, trigger, auto_resolved, pre_checked_messages). Exits directly
    on failure (same style as the rest of this module) rather than raising,
    so every path either returns or exits — never falls through."""
    outgoing = engine.get_allowed_transitions(wf, current)

    if trigger is not None:
        trans = engine.find_transition(wf, current, trigger)
        if not trans:
            _fail(f"No transition '{trigger}' from '{current}'.", 2)
        return trans, trigger, False, []

    if len(outgoing) == 1:
        trans = outgoing[0]
        return trans, trans["trigger"], False, []

    if not outgoing:
        _fail(f"No transitions leave state '{current}'.", 2)

    if not any(t.get("guards") for t in outgoing):
        options = ", ".join(t["trigger"] for t in outgoing)
        _fail(f"State '{current}' has several transitions. Pass --trigger one of: {options}", 2)

    # Choice: at least one candidate is conditional. Evaluate in declared
    # order and take the first whose guards all pass. An unconditional
    # candidate placed last acts as the default.
    failures: List[Tuple[str, List[str]]] = []
    for t in outgoing:
        ok, msgs = engine.evaluate_transition_guards(t, inputs)
        if ok:
            return t, t["trigger"], True, msgs
        failures.append((t["trigger"], msgs))

    console.print(f"[red]No candidate transition's guards passed from '{current}':[/red]", soft_wrap=True)
    for trig, msgs in failures:
        console.print(f"  {trig}:", soft_wrap=True)
        for m in msgs:
            console.print(f"    - {escape(m)}", soft_wrap=True)
    sys.exit(2)


def _check_join(engine: WtfEngine, run_id: str, state: Dict[str, Any], wf: Dict[str, Any]) -> None:
    """If every branch from the run's current fork has reached a branch_end
    state, collapse: take the fork's join transition, or (if it requires
    approval) auto-propose it instead of silently collapsing. No-op
    otherwise. v1: a join transition never has guards (enforced by validate),
    so there is no guard-failure case to handle here."""
    branches = state.get("branches")
    if not branches or not all(b["status"] == "branch_complete" for b in branches.values()):
        return

    fork_origin = state["fork_origin"]
    join_trans = _first(
        (t for t in engine.get_allowed_transitions(wf, fork_origin) if t.get("join") is True)
    )
    if join_trans is None:
        console.print(f"[red]Error:[/red] fork '{fork_origin}' has no join transition.", soft_wrap=True)
        return

    finished = [name for name in branches]  # `list()` is shadowed by the `wtf list` command in this module
    state.pop("branches", None)
    state.pop("fork_origin", None)

    if join_trans.get("require_approval"):
        state["current_state"] = fork_origin
        _do_propose(engine, run_id, state, fork_origin, join_trans, join_trans["trigger"])
        return

    terminal = {s["name"] for s in wf["states"] if s.get("terminal") is True}
    state["current_state"] = join_trans["dest"]
    if join_trans["dest"] in terminal:
        state["status"] = "completed"
    engine.store.save_run(run_id, state)
    engine.store.append_event(run_id, {
        "type": "joined",
        "from": fork_origin,
        "to": join_trans["dest"],
        "branches": finished,
    })
    console.print(f"[green]✓[/green] All branches complete — joined at '{join_trans['dest']}'", soft_wrap=True)


def _do_fork(engine: WtfEngine, run_id: str, state: Dict[str, Any], wf: Dict[str, Any], fork_state: str) -> None:
    """Take every non-join transition out of a fork: true state together,
    atomically — if any branch-start's guards would fail, nothing forks."""
    outgoing = engine.get_allowed_transitions(wf, fork_state)
    branch_starts = [t for t in outgoing if t.get("join") is not True]

    checked = []
    failures: List[Tuple[str, List[str]]] = []
    for t in branch_starts:
        ok, msgs = engine.evaluate_transition_guards(t, state.get("inputs", {}))
        checked.append((t, ok))
        if not ok:
            failures.append((t["trigger"], msgs))

    if failures:
        console.print(f"[red]Fork '{fork_state}' did not start — some branches' guards failed:[/red]", soft_wrap=True)
        for trig, msgs in failures:
            console.print(f"  {trig}:", soft_wrap=True)
            for m in msgs:
                console.print(f"    - {escape(m)}", soft_wrap=True)
        sys.exit(2)

    branch_end = {s["name"] for s in wf["states"] if s.get("branch_end") is True}
    branches: Dict[str, Any] = {}
    for t, _ in checked:
        dest = t["dest"]
        branches[dest] = {
            "current_state": dest,
            "status": "branch_complete" if dest in branch_end else "running",
        }

    state["branches"] = branches
    state["fork_origin"] = fork_state
    engine.store.save_run(run_id, state)
    engine.store.append_event(run_id, {
        "type": "forked",
        "from": fork_state,
        "branches": [name for name in branches],
    })
    console.print(f"[green]✓[/green] Forked '{fork_state}' into: {', '.join(branches.keys())}", soft_wrap=True)

    _check_join(engine, run_id, state, wf)
    _show_next(engine, run_id, wf)


def _done_on_branch(
    engine: WtfEngine,
    run_id: str,
    state: Dict[str, Any],
    wf: Dict[str, Any],
    branch: Optional[str],
    trigger: Optional[str],
) -> None:
    """Advance one active branch of a forked run. Reuses the same resolution,
    guard, and Choice logic as the top-level done, scoped to that branch's
    own current_state. v1: a branch-level transition may not require
    approval (fails loudly rather than silently misbehaving) — only the
    fork's own join transition can be gated."""
    branches = state["branches"]
    active = [name for name, b in branches.items() if b["status"] == "running"]

    if branch is None:
        if len(active) == 1:
            branch = active[0]
        elif not active:
            _fail("All branches have already finished; nothing to advance.", 2)
        else:
            _fail(f"Several branches are active. Pass --branch one of: {', '.join(active)}", 2)
    elif branch not in branches:
        _fail(f"No such branch '{branch}'. Active branches: {', '.join(active) or '(none)'}", 2)
    elif branches[branch]["status"] != "running":
        _fail(f"Branch '{branch}' has already finished.", 2)

    current = branches[branch]["current_state"]
    trans, trigger, auto_resolved, pre_checked_messages = _resolve_transition(
        engine, wf, current, trigger, state.get("inputs", {})
    )

    if trans.get("require_approval"):
        _fail(
            f"Transition '{trigger}' on branch '{branch}' requires approval, which is not supported "
            f"for branch-level transitions in v1. Only the fork's own join transition can be gated.",
            2,
        )

    if auto_resolved:
        passed, messages = True, pre_checked_messages
    else:
        passed, messages = engine.evaluate_transition_guards(trans, state.get("inputs", {}))

    if not passed:
        console.print(f"[red]Guards failed on branch '{branch}':[/red]", soft_wrap=True)
        for m in messages:
            console.print(f"  - {escape(m)}", soft_wrap=True)
        engine.store.append_event(run_id, {
            "type": "transition_failed",
            "branch": branch,
            "trigger": trigger,
            "from": current,
            "guards": messages,
        })
        sys.exit(2)

    branch_end = {s["name"] for s in wf["states"] if s.get("branch_end") is True}
    branches[branch]["current_state"] = trans["dest"]
    if trans["dest"] in branch_end:
        branches[branch]["status"] = "branch_complete"
    engine.store.save_run(run_id, state)
    engine.store.append_event(run_id, {
        "type": "transition",
        "branch": branch,
        "trigger": trigger,
        "from": current,
        "to": trans["dest"],
    })
    console.print(f"[green]✓[/green] Branch '{branch}': {current} -> {trans['dest']} (trigger: {trigger})", soft_wrap=True)

    _check_join(engine, run_id, state, wf)
    # _check_join pops "branches" from `state` in place if it collapsed, but the
    # local `branches` var above still references the old (now orphaned) dict —
    # check `state` itself, not that stale reference, to know whether to still
    # show one branch's detail or the (now collapsed) top-level state.
    _show_next(engine, run_id, wf, branch if "branches" in state else None)


@app.command()
def done(
    run_id: Optional[str] = typer.Option(None, "--run", help="Run ID"),
    trigger: Optional[str] = typer.Option(None, "--trigger", help="Transition trigger to take"),
    branch: Optional[str] = typer.Option(None, "--branch", help="Branch to act on, once a run has forked"),
):
    """Take a transition from the current state when its guards pass.

    With no --trigger and several candidates: if none of them have guards,
    this is a genuine judgment call and you must pick explicitly (unchanged).
    If at least one does, candidates are tried in declared order and the
    first whose guards all pass is taken automatically (Choice) — an
    unconditional candidate placed last acts as the default.

    A state with fork: true forks into all its non-join transitions at once
    (no --trigger). Once forked, use --branch to advance one branch
    independently; the run auto-collapses once every branch reaches a
    branch_end state."""
    engine = WtfEngine()
    run_id = _pick_run(engine, run_id, "running")
    if run_id is None:
        _fail("No running run found. Start one with 'wtf start <workflow>'.", 1)

    try:
        state = _load_run_checked(engine, run_id)
        if state["status"] == "completed":
            _fail(f"Run {run_id} is already completed.", 2)
        if state["status"] == "pending_approval":
            _fail(f"Run {run_id} is waiting for approval. Use 'wtf approve' or 'wtf reject'.", 2)

        wf = engine.load_workflow(state["workflow"])

        if state.get("branches"):
            _done_on_branch(engine, run_id, state, wf, branch, trigger)
            return

        if branch is not None:
            _fail("This run has not forked; --branch does not apply.", 2)

        current = state["current_state"]
        current_node = _first((s for s in wf["states"] if s["name"] == current), {})

        if current_node.get("fork") is True:
            if trigger is not None:
                _fail(f"State '{current}' is a fork; it takes no --trigger (all branches start together).", 2)
            _do_fork(engine, run_id, state, wf, current)
            return

        trans, trigger, auto_resolved, pre_checked_messages = _resolve_transition(
            engine, wf, current, trigger, state.get("inputs", {})
        )

        if trans.get("require_approval"):
            if auto_resolved:
                console.print(
                    f"[cyan]Auto-resolved to '{trigger}', which requires approval — proposing it.[/cyan]",
                    soft_wrap=True,
                )
                _do_propose(engine, run_id, state, current, trans, trigger)
                return
            _fail(f"Transition '{trigger}' requires approval. Use 'wtf propose {trigger}'.", 2)

        if auto_resolved:
            # Already evaluated above to find this match. Don't re-run: guards may
            # execute real shell commands (command_passes/command_fails), and
            # re-evaluating would run them a second time.
            passed, messages = True, pre_checked_messages
        else:
            passed, messages = engine.evaluate_transition_guards(trans, state.get("inputs", {}))

        if not passed:
            console.print("[red]Guards failed:[/red]", soft_wrap=True)
            for m in messages:
                console.print(f"  - {escape(m)}", soft_wrap=True)
            engine.store.append_event(run_id, {
                "type": "transition_failed",
                "trigger": trigger,
                "from": current,
                "guards": messages,
            })
            sys.exit(2)

        terminal = {s["name"] for s in wf["states"] if s.get("terminal") is True}
        state["current_state"] = trans["dest"]
        if trans["dest"] in terminal:
            state["status"] = "completed"
        engine.store.save_run(run_id, state)
        engine.store.append_event(run_id, {
            "type": "transition",
            "trigger": trigger,
            "from": current,
            "to": trans["dest"],
        })

        console.print(f"[green]✓[/green] Transitioned: {current} -> {trans['dest']} (trigger: {trigger})", soft_wrap=True)
        if state["status"] == "completed":
            console.print("[green]✓[/green] Workflow completed!", soft_wrap=True)
        _show_next(engine, run_id, wf)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), 1)


def _do_propose(
    engine: WtfEngine,
    run_id: str,
    state: Dict[str, Any],
    current: str,
    trans: Dict[str, Any],
    trigger: str,
) -> None:
    """Mark a gated transition as pending approval. Shared by the `propose`
    command and by `done`'s auto-resolved (Choice) path when the uniquely
    matched candidate requires approval."""
    state["status"] = "pending_approval"
    state["pending_transition"] = {"trigger": trigger, "from": current, "to": trans["dest"]}
    engine.store.save_run(run_id, state)
    engine.store.append_event(run_id, {
        "type": "proposed",
        "trigger": trigger,
        "from": current,
        "to": trans["dest"],
    })
    console.print(f"[yellow]⏳[/yellow] Proposed transition {current} -> {trans['dest']} (trigger: {trigger})", soft_wrap=True)
    console.print("  Status: pending_approval")
    console.print("  Use 'wtf approve' or 'wtf reject' to decide")


@app.command()
def propose(trigger: str, run_id: Optional[str] = typer.Option(None, "--run", help="Run ID")):
    """Propose a gated transition. The run waits until 'wtf approve' or 'wtf reject'."""
    engine = WtfEngine()
    run_id = _pick_run(engine, run_id, "running")
    if run_id is None:
        _fail("No running run found. Start one with 'wtf start <workflow>'.", 1)

    try:
        state = _load_run_checked(engine, run_id)
        if state["status"] == "completed":
            _fail(f"Run {run_id} is already completed.", 2)
        if state["status"] == "pending_approval":
            _fail(f"Run {run_id} already has a transition waiting for approval.", 2)
        if state.get("branches"):
            _fail(
                "This run has forked; branch-level approval gates are not supported in v1. "
                "Resolve active branches with 'wtf done --branch <name>' first.",
                2,
            )

        wf = engine.load_workflow(state["workflow"])
        current = state["current_state"]
        trans = engine.find_transition(wf, current, trigger)
        if not trans:
            _fail(f"No transition '{trigger}' from '{current}'.", 2)
        if not trans.get("require_approval"):
            _fail(f"Transition '{trigger}' does not require approval. Use 'wtf done --trigger {trigger}'.", 2)

        _do_propose(engine, run_id, state, current, trans, trigger)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), 1)


@app.command()
def approve(run_id: Optional[str] = typer.Option(None, "--run", help="Run ID")):
    """Approve the pending transition after re-checking its guards."""
    engine = WtfEngine()
    run_id = _resolve_run(engine, run_id, "pending_approval")
    if run_id is None:
        _fail("No run is waiting for approval.", 1)

    try:
        state = _load_run_checked(engine, run_id)
        pending = state.get("pending_transition")
        if state["status"] != "pending_approval" or not pending:
            _fail(f"Run {run_id} has no transition waiting for approval.", 1)

        wf = engine.load_workflow(state["workflow"])
        trans = engine.find_transition(wf, pending["from"], pending["trigger"])
        if trans is None:
            _fail(f"Pending transition '{pending['trigger']}' no longer exists in the workflow.", 2)

        passed, messages = engine.evaluate_transition_guards(trans, state.get("inputs", {}))
        if not passed:
            console.print("[red]Guards failed:[/red]", soft_wrap=True)
            for m in messages:
                console.print(f"  - {escape(m)}", soft_wrap=True)
            sys.exit(2)

        terminal = {s["name"] for s in wf["states"] if s.get("terminal") is True}
        state["current_state"] = pending["to"]
        state["status"] = "completed" if pending["to"] in terminal else "running"
        state.pop("pending_transition", None)
        engine.store.save_run(run_id, state)
        engine.store.append_event(run_id, {
            "type": "approved",
            "transition": pending,
        })

        console.print(f"[green]✓[/green] Approved: {pending['from']} -> {pending['to']}", soft_wrap=True)
        _show_next(engine, run_id, wf)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), 1)


@app.command()
def reject(
    run_id: Optional[str] = typer.Option(None, "--run", help="Run ID"),
    reason: str = typer.Option("", "--reason", help="Why the proposal is rejected"),
):
    """Reject the pending transition and take the explicit reject transition."""
    engine = WtfEngine()
    run_id = _resolve_run(engine, run_id, "pending_approval")
    if run_id is None:
        _fail("No run is waiting for approval.", 1)

    try:
        state = _load_run_checked(engine, run_id)
        pending = state.get("pending_transition")
        if state["status"] != "pending_approval" or not pending:
            _fail(f"Run {run_id} has no transition waiting for approval.", 1)

        wf = engine.load_workflow(state["workflow"])
        trans = engine.find_transition(wf, pending["from"], "reject")
        if not trans:
            _fail(f"No explicit 'reject' transition from '{pending['from']}'.", 2)

        terminal = {s["name"] for s in wf["states"] if s.get("terminal") is True}
        old = pending["from"]
        state["current_state"] = trans["dest"]
        state["status"] = "completed" if trans["dest"] in terminal else "running"
        state.pop("pending_transition", None)
        if reason:
            state.setdefault("data", {})["reject_reason"] = reason
        engine.store.save_run(run_id, state)
        engine.store.append_event(run_id, {
            "type": "rejected",
            "transition": pending,
            "reason": reason,
            "to": trans["dest"],
        })

        console.print(f"[red]✗[/red] Rejected: {old} -> {trans['dest']}", soft_wrap=True)
        if reason:
            console.print(f"  Reason: {escape(reason)}", soft_wrap=True)
        _show_next(engine, run_id, wf)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), 1)


@app.command()
def status(run_id: Optional[str] = typer.Option(None, "--run")):
    """Show status of runs."""
    engine = WtfEngine()
    try:
        if run_id:
            state = _load_run_checked(engine, run_id)
            wf = engine.load_workflow(state["workflow"])
            node = None
            for n in wf["states"]:
                if n["name"] == state["current_state"]:
                    node = n
                    break
            console.print(json.dumps({
                "run_id": run_id,
                "workflow": state["workflow"],
                "status": state["status"],
                "current_state": state["current_state"],
                "node_context": node.get("context") if node else None,
                "tools": node.get("tools") if node else [],
                "skills": node.get("skills") if node else [],
                "inputs": state.get("inputs", {}),
                "created_at": state["created_at"],
                "updated_at": state["updated_at"],
            }, indent=2), markup=False, highlight=False)
        else:
            runs = engine.store.list_runs()
            if not runs:
                console.print("[yellow]No runs found[/yellow]")
                return
            table = Table(title="Workflow Runs")
            table.add_column("Run ID", style="cyan")
            table.add_column("Workflow")
            table.add_column("Status")
            table.add_column("Current State")
            table.add_column("Updated")
            for r in runs:
                table.add_row(r["run_id"][:8], r["workflow"], r["status"], str(r.get("current_state")), r.get("updated_at", "")[:16])
            console.print(table)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _format_event(e: Dict[str, Any]) -> str:
    """One readable line for an event, by type. Unknown types still print,
    with their fields shown as-is, so a future event type never goes silent."""
    etype = e.get("type", "unknown")
    if etype == "run_started":
        extra = f" inputs={e['inputs']}" if e.get("inputs") else ""
        return f"started '{e.get('workflow')}' at '{e.get('initial_state')}'{extra}"
    if etype == "transition":
        branch = f"[branch {e['branch']}] " if e.get("branch") else ""
        return f"{branch}{e.get('from')} -> {e.get('to')} (trigger: {e.get('trigger')})"
    if etype == "transition_failed":
        branch = f"[branch {e['branch']}] " if e.get("branch") else ""
        guards = "; ".join(e.get("guards", []))
        return f"{branch}blocked at '{e.get('from')}' on trigger '{e.get('trigger')}': {guards}"
    if etype == "proposed":
        return f"{e.get('from')} -> {e.get('to')} proposed (trigger: {e.get('trigger')}), awaiting approval"
    if etype == "approved":
        t = e.get("transition", {})
        return f"{t.get('from')} -> {t.get('to')} approved (trigger: {t.get('trigger')})"
    if etype == "rejected":
        t = e.get("transition", {})
        reason = f" — reason: {e['reason']}" if e.get("reason") else ""
        return f"{t.get('from')} -> {e.get('to')} rejected (was proposing '{t.get('trigger')}' to '{t.get('to')}'){reason}"
    if etype == "integrity_warning":
        return e.get("message", "state.json did not match its recorded checksum")
    if etype == "forked":
        return f"'{e.get('from')}' forked into: {', '.join(e.get('branches', []))}"
    if etype == "joined":
        return f"all branches ({', '.join(e.get('branches', []))}) complete — joined '{e.get('from')}' -> '{e.get('to')}'"
    extras = {k: v for k, v in e.items() if k not in ("type", "timestamp")}
    return f"{extras}" if extras else ""


@app.command()
def log(run_id: Optional[str] = typer.Option(None, "--run", help="Run ID")):
    """Show the recorded event history for a run."""
    engine = WtfEngine()
    try:
        if run_id is None:
            runs = engine.store.list_runs()
            if not runs:
                console.print("[yellow]No runs found[/yellow]")
                return
            run_id = _resolve_run(engine, None, "running") or runs[-1]["run_id"]

        events = engine.store.load_events(run_id)
        if not events:
            console.print(f"No events recorded for run {run_id}.")
            return

        console.print(f"[bold]Run {run_id}[/bold]")
        for e in events:
            ts = e.get("timestamp", "")
            etype = e.get("type", "unknown")
            console.print(
                f"[dim]{escape(ts)}[/dim]  [cyan]{escape(etype)}[/cyan]  {escape(_format_event(e))}",
                soft_wrap=True,
            )
    except Exception as e:
        _fail(str(e), 1)


@app.command()
def list():
    """List all runs."""
    status(run_id=None)


if __name__ == "__main__":
    app()

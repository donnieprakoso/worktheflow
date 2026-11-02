"""Tests for Parallel: fork, independent branches, and join (Use Case #24).
One test per GWT scenario.
"""

import copy
import json

import yaml
from typer.testing import CliRunner

from wtf.cli import app
from wtf.store import RunStore

runner = CliRunner()

# intake -> fork_state (fork) -> {track_a (single-step branch, its own branch_end),
#                                 track_b_step1 -> track_b_step2 (branch_end)}
#        -> join: all_done -> after_join (terminal)
FORK_WF = {
    "name": "demo",
    "version": "1.0",
    "initial": "intake",
    "states": [
        {"name": "intake"},
        {"name": "fork_state", "fork": True},
        {"name": "track_a", "branch_end": True},
        {"name": "track_b_step1"},
        {"name": "track_b_step2", "branch_end": True},
        {"name": "after_join", "terminal": True},
    ],
    "transitions": [
        {"trigger": "go", "source": "intake", "dest": "fork_state"},
        {"trigger": "start_a", "source": "fork_state", "dest": "track_a"},
        {"trigger": "start_b", "source": "fork_state", "dest": "track_b_step1"},
        {"trigger": "all_done", "source": "fork_state", "dest": "after_join", "join": True},
        {"trigger": "advance_b", "source": "track_b_step1", "dest": "track_b_step2"},
    ],
}


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0


def write_wf(tmp_path, data, name="demo"):
    (tmp_path / ".wtf" / "workflows" / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


def start_and_enter_fork(tmp_path, monkeypatch):
    """Start a run and advance it to fork_state. Returns the run id."""
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["start", "demo"]).exit_code == 0
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    run_id = index["runs"][-1]["run_id"]
    assert runner.invoke(app, ["done"]).exit_code == 0  # intake -> fork_state
    return run_id


def read_state(tmp_path, run_id):
    return json.loads((tmp_path / ".wtf" / "runs" / run_id / "state.json").read_text())


def read_events(tmp_path, run_id):
    path = tmp_path / ".wtf" / "runs" / run_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def do(tmp_path, monkeypatch, *args):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["done", *args])


def nxt(tmp_path, monkeypatch, *args):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["next", *args])


# Scenario 1
def test_fork_creates_branches_with_atomic_guards(tmp_path, monkeypatch):
    """Given a fork state with passing branch-start guards, When I run wtf done, Then branches and fork_origin are created."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, FORK_WF)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["fork_origin"] == "fork_state"
    assert set(state["branches"].keys()) == {"track_a", "track_b_step1"}
    # track_a's own state is branch_end, so it's immediately branch_complete.
    assert state["branches"]["track_a"]["status"] == "branch_complete"
    assert state["branches"]["track_b_step1"]["status"] == "running"
    events = read_events(tmp_path, run_id)
    assert any(e["type"] == "forked" for e in events)


# Scenario 2
def test_fork_is_atomic_on_guard_failure(tmp_path, monkeypatch):
    """Given a branch-start's guards would fail, When I run wtf done, Then nothing forks and every failure is reported."""
    data = copy.deepcopy(FORK_WF)
    for t in data["transitions"]:
        if t["trigger"] == "start_a":
            t["guards"] = [{"type": "file_exists", "params": {"path": "nope.txt"}}]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 2, result.output
    assert "start_a" in result.output
    state = read_state(tmp_path, run_id)
    assert "branches" not in state or not state["branches"]
    assert state["current_state"] == "fork_state"


# Scenario 3
def test_explicit_trigger_on_fork_state_is_refused(tmp_path, monkeypatch):
    """Given a fork state, When I run wtf done --trigger X, Then it is refused."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, FORK_WF)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    result = do(tmp_path, monkeypatch, "--trigger", "start_a")
    assert result.exit_code == 2, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "fork_state"


# A variant where BOTH branches need their own step to finish, so advancing
# one alone never triggers the join (unlike FORK_WF, where track_a is
# immediately branch_complete at fork time and would auto-join as soon as the
# only other branch finishes).
TWO_STEP_FORK_WF = copy.deepcopy(FORK_WF)
TWO_STEP_FORK_WF["states"] = [
    s if s["name"] != "track_a" else {"name": "track_a"} for s in TWO_STEP_FORK_WF["states"]
] + [{"name": "track_a_step2", "branch_end": True}]
TWO_STEP_FORK_WF["transitions"].append({"trigger": "advance_a", "source": "track_a", "dest": "track_a_step2"})


# Scenario 4
def test_branches_advance_independently_via_branch_flag(tmp_path, monkeypatch):
    """Given 2 active branches, When I act on one with --branch, Then only that branch advances."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, TWO_STEP_FORK_WF)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    assert do(tmp_path, monkeypatch).exit_code == 0  # fork

    result = do(tmp_path, monkeypatch, "--branch", "track_b_step1", "--trigger", "advance_b")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["branches"]["track_b_step1"]["current_state"] == "track_b_step2"
    assert state["branches"]["track_b_step1"]["status"] == "branch_complete"
    # track_a untouched
    assert state["branches"]["track_a"]["current_state"] == "track_a"


# Scenario 5
def test_branch_flag_can_be_omitted_when_only_one_branch_is_active(tmp_path, monkeypatch):
    """Given one branch remaining active (the other already branch_complete), When I omit --branch, Then it resolves unambiguously."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, TWO_STEP_FORK_WF)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    assert do(tmp_path, monkeypatch).exit_code == 0  # fork: both branches start "running"
    assert do(tmp_path, monkeypatch, "--branch", "track_a", "--trigger", "advance_a").exit_code == 0
    # track_a is now branch_complete; track_b_step1 is the only branch still active.

    result = do(tmp_path, monkeypatch, "--trigger", "advance_b")  # no --branch: only track_b_step1 is still active
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    # This was also the last branch, so the run auto-joins — check the join happened
    # rather than that "branches" still exists, since that's correct, not a bug.
    assert "branches" not in state
    assert state["current_state"] == "after_join"


# Scenario 6
def test_run_auto_collapses_once_all_branches_reach_branch_end(tmp_path, monkeypatch):
    """Given all branches have reached branch_end, When the last one finishes, Then the run auto-collapses and logs a joined event."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, FORK_WF)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    assert do(tmp_path, monkeypatch).exit_code == 0  # fork
    result = do(tmp_path, monkeypatch, "--trigger", "advance_b")  # last branch finishes -> should auto-join
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert "branches" not in state or not state["branches"]
    assert "fork_origin" not in state or not state["fork_origin"]
    assert state["current_state"] == "after_join"
    assert state["status"] == "completed"
    events = read_events(tmp_path, run_id)
    assert any(e["type"] == "joined" for e in events)


# Scenario 7
def test_gated_join_auto_proposes_instead_of_collapsing(tmp_path, monkeypatch):
    """Given the join transition requires approval, When all branches finish, Then the run becomes pending_approval instead of silently collapsing."""
    data = copy.deepcopy(FORK_WF)
    for t in data["transitions"]:
        if t.get("join"):
            t["require_approval"] = True
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    assert do(tmp_path, monkeypatch).exit_code == 0  # fork
    result = do(tmp_path, monkeypatch, "--trigger", "advance_b")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["status"] == "pending_approval"
    assert "branches" not in state or not state["branches"]
    events = read_events(tmp_path, run_id)
    assert any(e["type"] == "proposed" for e in events)


# Scenario 8
def test_join_transition_with_guards_is_rejected_by_validate(tmp_path, monkeypatch):
    """Given a join: true transition that declares guards, When I validate, Then it is rejected."""
    data = copy.deepcopy(FORK_WF)
    for t in data["transitions"]:
        if t.get("join"):
            t["guards"] = [{"type": "file_exists", "params": {"path": "x.txt"}}]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["validate", "demo"])
    assert result.exit_code == 1, result.output
    assert "join" in result.output.lower()


# Scenario 9
def test_fork_branch_that_cannot_reach_branch_end_is_rejected_by_validate(tmp_path, monkeypatch):
    """Given a fork whose branch can never reach a branch_end, When I validate, Then it is rejected."""
    data = copy.deepcopy(FORK_WF)
    # track_b_step2 (the only branch_end for that branch) becomes unreachable
    data["transitions"] = [t for t in data["transitions"] if t["trigger"] != "advance_b"]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["validate", "demo"])
    assert result.exit_code == 1, result.output
    assert "branch_end" in result.output.lower() or "track_b_step1" in result.output


# Scenario 10
def test_checksum_still_validates_a_forked_state(tmp_path, monkeypatch):
    """Given a forked run's state.json, When I compute its checksum, Then verify_integrity still correctly validates it."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, FORK_WF)
    run_id = start_and_enter_fork(tmp_path, monkeypatch)
    assert do(tmp_path, monkeypatch).exit_code == 0  # fork
    state = read_state(tmp_path, run_id)
    assert "branches" in state
    assert RunStore(tmp_path).verify_integrity(state) is True

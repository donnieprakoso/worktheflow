"""Tests for approval gates: wtf propose, wtf approve, wtf reject (Use Case #4). One test per GWT scenario."""

import copy
import json

import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()

# red --ready (gated)--> review --approve--> done
# red --ship (gated)--> done (terminal)
# red --skip (ungated)--> review
# red --reject--> blocked --retry--> red
GATES = {
    "name": "gates",
    "version": "1.0",
    "initial": "red",
    "states": [
        {"name": "red"},
        {"name": "review"},
        {"name": "blocked"},
        {"name": "done", "terminal": True},
    ],
    "transitions": [
        {"trigger": "ready", "source": "red", "dest": "review", "require_approval": True},
        {"trigger": "ship", "source": "red", "dest": "done", "require_approval": True},
        {"trigger": "skip", "source": "red", "dest": "review"},
        {"trigger": "reject", "source": "red", "dest": "blocked"},
        {"trigger": "retry", "source": "blocked", "dest": "red"},
        {"trigger": "approve", "source": "review", "dest": "done"},
    ],
}


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output


def write_wf(tmp_path, data, name="gates"):
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def wf(**changes):
    data = copy.deepcopy(GATES)
    data.update(changes)
    return data


def run_ids(tmp_path):
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    return [r["run_id"] for r in index["runs"]]


def read_state(tmp_path, run_id):
    return json.loads((tmp_path / ".wtf" / "runs" / run_id / "state.json").read_text())


def read_events(tmp_path, run_id):
    path = tmp_path / ".wtf" / "runs" / run_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def only_run(tmp_path):
    ids = run_ids(tmp_path)
    assert len(ids) == 1, ids
    return ids[0]


def cli(tmp_path, monkeypatch, *args):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, list(args))


def start_run(tmp_path, monkeypatch):
    """Start a run and return its id (the newest run)."""
    before = set(run_ids(tmp_path))
    result = cli(tmp_path, monkeypatch, "start", "gates")
    assert result.exit_code == 0, result.output
    new = [r for r in run_ids(tmp_path) if r not in before]
    assert len(new) == 1, new
    return new[0]


def propose(tmp_path, monkeypatch, trigger, *extra):
    return cli(tmp_path, monkeypatch, "propose", trigger, *extra)


# ---- propose ----

# Scenario 1
def test_propose_gated_transition_marks_run_pending(tmp_path, monkeypatch):
    """Given a gated transition, When I propose it, Then status is pending_approval, the pending transition is recorded, proposed is logged, and the state is unchanged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    result = propose(tmp_path, monkeypatch, "ready")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["status"] == "pending_approval"
    assert state["pending_transition"] == {"trigger": "ready", "from": "red", "to": "review"}
    assert state["current_state"] == "red"
    assert any(e["type"] == "proposed" for e in read_events(tmp_path, run_id))


# Scenario 2
def test_propose_unknown_trigger_is_rejected(tmp_path, monkeypatch):
    """Given no transition with the trigger from the current state, When I propose it, Then exit 2 and the run is unchanged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    result = propose(tmp_path, monkeypatch, "approve")
    assert result.exit_code == 2, result.output
    assert read_state(tmp_path, run_id)["status"] == "running"


# Scenario 3
def test_propose_while_pending_is_refused(tmp_path, monkeypatch):
    """Given the run is already pending approval, When I propose again, Then exit 2 and the pending transition is unchanged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ready")
    result = propose(tmp_path, monkeypatch, "ship")
    assert result.exit_code == 2, result.output
    assert read_state(tmp_path, run_id)["pending_transition"]["trigger"] == "ready"


# Scenario 4
def test_propose_ungated_transition_points_to_done(tmp_path, monkeypatch):
    """Given the transition is not gated, When I propose it, Then exit 2 and the output points to wtf done."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    result = propose(tmp_path, monkeypatch, "skip")
    assert result.exit_code == 2, result.output
    assert "wtf done" in result.output
    assert read_state(tmp_path, run_id)["status"] == "running"


# Scenario 5
def test_propose_on_completed_run_is_refused(tmp_path, monkeypatch):
    """Given a completed run, When I propose a transition, Then exit 2 and the output says the run is completed."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ship")
    cli(tmp_path, monkeypatch, "approve")
    assert read_state(tmp_path, run_id)["status"] == "completed"
    result = propose(tmp_path, monkeypatch, "ready")
    assert result.exit_code == 2, result.output
    assert "completed" in result.output.lower()


# ---- approve ----

# Scenario 6
def test_approve_moves_run_and_clears_pending(tmp_path, monkeypatch):
    """Given a pending transition, When I approve, Then the run moves to the destination, status is running, pending is cleared, and approved is logged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ready")
    result = cli(tmp_path, monkeypatch, "approve")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["current_state"] == "review"
    assert state["status"] == "running"
    assert "pending_transition" not in state
    assert any(e["type"] == "approved" for e in read_events(tmp_path, run_id))


# Scenario 7
def test_approve_rechecks_guards(tmp_path, monkeypatch):
    """Given the pending transition's guards now fail, When I approve, Then exit 2 and the run stays pending."""
    init_project(tmp_path, monkeypatch)
    (tmp_path / "ok.txt").write_text("yes")
    data = wf()
    data["transitions"][0]["guards"] = [{"type": "file_exists", "params": {"path": "ok.txt"}}]
    write_wf(tmp_path, data)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ready")
    (tmp_path / "ok.txt").unlink()
    result = cli(tmp_path, monkeypatch, "approve")
    assert result.exit_code == 2, result.output
    state = read_state(tmp_path, run_id)
    assert state["status"] == "pending_approval"
    assert state["current_state"] == "red"


# Scenario 8
def test_approve_with_nothing_pending_is_an_error(tmp_path, monkeypatch):
    """Given nothing is pending, When I approve, Then exit 1 and the output says no run is waiting for approval."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    start_run(tmp_path, monkeypatch)
    result = cli(tmp_path, monkeypatch, "approve")
    assert result.exit_code == 1, result.output
    assert "no run is waiting for approval" in result.output.lower()


# Scenario 9
def test_approve_into_terminal_state_completes_run(tmp_path, monkeypatch):
    """Given the pending transition leads to a terminal state, When I approve, Then the run status becomes completed."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ship")
    result = cli(tmp_path, monkeypatch, "approve")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["current_state"] == "done"
    assert state["status"] == "completed"


# Scenario 10
def test_approve_without_run_picks_most_recent_pending(tmp_path, monkeypatch):
    """Given two pending runs, When I approve without --run, Then the most recent pending run is approved and the other stays pending."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    first = start_run(tmp_path, monkeypatch)
    second = start_run(tmp_path, monkeypatch)
    assert first != second
    propose(tmp_path, monkeypatch, "ready", "--run", first)
    propose(tmp_path, monkeypatch, "ready", "--run", second)
    result = cli(tmp_path, monkeypatch, "approve")
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, second)["current_state"] == "review"
    assert read_state(tmp_path, first)["status"] == "pending_approval"


# ---- reject ----

# Scenario 11
def test_reject_takes_reject_transition_and_stores_reason(tmp_path, monkeypatch):
    """Given a pending transition, When I reject with a reason, Then the run moves to the reject destination, status is running, pending is cleared, the reason is stored, and rejected is logged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ready")
    result = cli(tmp_path, monkeypatch, "reject", "--reason", "not yet")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["current_state"] == "blocked"
    assert state["status"] == "running"
    assert "pending_transition" not in state
    assert state["data"]["reject_reason"] == "not yet"
    assert any(e["type"] == "rejected" for e in read_events(tmp_path, run_id))


# Scenario 12
def test_reject_without_reject_transition_keeps_run_pending(tmp_path, monkeypatch):
    """Given no explicit reject transition from the pending state, When I reject, Then exit 2 and the run stays pending."""
    init_project(tmp_path, monkeypatch)
    data = wf()
    data["transitions"] = [t for t in data["transitions"] if t["trigger"] != "reject"]
    write_wf(tmp_path, data)
    run_id = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ready")
    result = cli(tmp_path, monkeypatch, "reject")
    assert result.exit_code == 2, result.output
    assert read_state(tmp_path, run_id)["status"] == "pending_approval"


# Scenario 13
def test_reject_with_nothing_pending_is_an_error(tmp_path, monkeypatch):
    """Given nothing is pending, When I reject, Then exit 1 and the output says no run is waiting for approval."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    start_run(tmp_path, monkeypatch)
    result = cli(tmp_path, monkeypatch, "reject")
    assert result.exit_code == 1, result.output
    assert "no run is waiting for approval" in result.output.lower()


# Scenario 14
def test_reject_without_run_picks_most_recent_pending(tmp_path, monkeypatch):
    """Given two pending runs, When I reject without --run, Then the most recent pending run is rejected."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATES)
    first = start_run(tmp_path, monkeypatch)
    second = start_run(tmp_path, monkeypatch)
    propose(tmp_path, monkeypatch, "ready", "--run", first)
    propose(tmp_path, monkeypatch, "ready", "--run", second)
    result = cli(tmp_path, monkeypatch, "reject")
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, second)["current_state"] == "blocked"
    assert read_state(tmp_path, first)["status"] == "pending_approval"

"""Tests for the run lifecycle: wtf start, wtf next, wtf done (Use Case #3). One test per GWT scenario."""

import copy
import json

import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()

# A valid workflow. red -> green -> done (terminal).
BASE = {
    "name": "demo",
    "version": "1.0",
    "initial": "red",
    "states": [
        {"name": "red"},
        {"name": "green"},
        {"name": "done", "terminal": True},
    ],
    "transitions": [
        {"trigger": "tests_written", "source": "red", "dest": "green"},
        {"trigger": "approve", "source": "green", "dest": "done"},
    ],
}


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output


def write_wf(tmp_path, data, name="demo"):
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def wf(**changes):
    data = copy.deepcopy(BASE)
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


def start(tmp_path, monkeypatch, workflow="demo", extra=()):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["start", workflow, *extra])


def only_run(tmp_path):
    ids = run_ids(tmp_path)
    assert len(ids) == 1, ids
    return ids[0]


# ---- start ----

# Scenario 1
def test_start_creates_running_run_at_initial_state(tmp_path, monkeypatch):
    """Given a valid workflow, When I run wtf start, Then a running run exists at initial and run_started is recorded."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    result = start(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    run_id = only_run(tmp_path)
    state = read_state(tmp_path, run_id)
    assert state["status"] == "running"
    assert state["current_state"] == "red"
    assert any(e["type"] == "run_started" for e in read_events(tmp_path, run_id))


# Scenario 2
def test_start_stores_inputs_and_status_shows_them(tmp_path, monkeypatch):
    """Given --input with a JSON object, When I start the run, Then the inputs are stored and shown by wtf status."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    result = start(tmp_path, monkeypatch, extra=["--input", '{"x": 1}'])
    assert result.exit_code == 0, result.output
    run_id = only_run(tmp_path)
    assert read_state(tmp_path, run_id)["inputs"] == {"x": 1}
    status = runner.invoke(app, ["status", "--run", run_id])
    assert '"x": 1' in status.output


# Scenario 3
def test_start_rejects_input_that_is_not_an_object(tmp_path, monkeypatch):
    """Given --input is not a JSON object, When I start the run, Then exit 1 and no run is created."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    for bad in ["not json", "[1, 2]"]:
        result = start(tmp_path, monkeypatch, extra=["--input", bad])
        assert result.exit_code == 1, result.output
    assert run_ids(tmp_path) == []


# Scenario 4
def test_start_refuses_invalid_workflow(tmp_path, monkeypatch):
    """Given a workflow that fails validation, When I start the run, Then exit 1 and no run is created."""
    init_project(tmp_path, monkeypatch)
    broken = wf()
    del broken["initial"]
    write_wf(tmp_path, broken)
    result = start(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert run_ids(tmp_path) == []


# Scenario 5
def test_start_without_init_says_to_run_init(tmp_path, monkeypatch):
    """Given the project has no .wtf/ folder, When I start the run, Then exit 1 and the message says to run wtf init."""
    result = start(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "wtf init" in result.output
    assert not (tmp_path / ".wtf").exists()


# ---- next ----

# Scenario 6
def test_next_reports_state_without_changing_it(tmp_path, monkeypatch):
    """Given a running run, When I run wtf next, Then it prints the current state and allowed transitions, and the state is unchanged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["next"])
    assert result.exit_code == 0, result.output
    assert "tests_written" in result.output
    assert read_state(tmp_path, run_id)["current_state"] == "red"


# Scenario 7
def test_next_with_no_runs(tmp_path, monkeypatch):
    """Given no runs exist, When I run wtf next, Then it prints No runs found and exits 0."""
    init_project(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["next"])
    assert result.exit_code == 0, result.output
    assert "No runs found" in result.output


# ---- done ----

def done(tmp_path, monkeypatch, *args):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["done", *args])


# Scenario 8
def test_done_with_trigger_moves_run_and_records_event(tmp_path, monkeypatch):
    """Given a run at red with a transition for tests_written, When I run wtf done --trigger tests_written, Then the run moves to green and a transition event is recorded."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "green"
    assert any(e["type"] == "transition" for e in read_events(tmp_path, run_id))


# Scenario 9
def test_done_without_trigger_takes_single_transition(tmp_path, monkeypatch):
    """Given red has exactly one outgoing transition, When I run wtf done with no trigger, Then that transition is taken."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "green"


# Scenario 10
def test_done_without_trigger_lists_options_when_ambiguous(tmp_path, monkeypatch):
    """Given red has several outgoing transitions, When I run wtf done with no trigger, Then exit 2, options are listed, and the state is unchanged."""
    init_project(tmp_path, monkeypatch)
    data = wf()
    data["transitions"].append({"trigger": "abandon", "source": "red", "dest": "done"})
    write_wf(tmp_path, data)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch)
    assert result.exit_code == 2, result.output
    assert "tests_written" in result.output
    assert "abandon" in result.output
    assert read_state(tmp_path, run_id)["current_state"] == "red"


# Scenario 11
def test_done_with_unknown_trigger_is_rejected(tmp_path, monkeypatch):
    """Given no transition with the trigger from the current state, When I run wtf done --trigger T, Then exit 2 and the state is unchanged."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch, "--trigger", "approve")  # approve is only valid from green
    assert result.exit_code == 2, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "red"


# Scenario 12
def test_done_on_approval_transition_points_to_propose(tmp_path, monkeypatch):
    """Given a transition with require_approval, When I run wtf done, Then exit 2, the state is unchanged, and the output points to wtf propose."""
    init_project(tmp_path, monkeypatch)
    data = wf()
    data["transitions"][0]["require_approval"] = True
    write_wf(tmp_path, data)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert result.exit_code == 2, result.output
    assert "propose" in result.output
    assert read_state(tmp_path, run_id)["current_state"] == "red"


# Scenario 13
def test_failing_guard_blocks_transition_and_logs_event(tmp_path, monkeypatch):
    """Given a guard that fails, When I run wtf done, Then exit 2, the state is unchanged, and transition_failed lists the guard."""
    init_project(tmp_path, monkeypatch)
    data = wf()
    data["transitions"][0]["guards"] = [{"type": "file_exists", "params": {"path": "missing.txt"}}]
    write_wf(tmp_path, data)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert result.exit_code == 2, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "red"
    failed = [e for e in read_events(tmp_path, run_id) if e["type"] == "transition_failed"]
    assert len(failed) == 1
    assert any("missing.txt" in m for m in failed[0]["guards"])


# Scenario 14
def test_passing_guards_allow_transition(tmp_path, monkeypatch):
    """Given all guards pass, When I run wtf done, Then the transition is taken."""
    init_project(tmp_path, monkeypatch)
    (tmp_path / "ok.txt").write_text("yes")
    data = wf()
    data["transitions"][0]["guards"] = [{"type": "file_exists", "params": {"path": "ok.txt"}}]
    write_wf(tmp_path, data)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "green"


# Scenario 15
def test_entering_terminal_state_completes_run(tmp_path, monkeypatch):
    """Given the destination is terminal, When the transition is taken, Then the run status becomes completed."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    done(tmp_path, monkeypatch, "--trigger", "tests_written")
    result = done(tmp_path, monkeypatch, "--trigger", "approve")
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["current_state"] == "done"
    assert state["status"] == "completed"
    assert "completed" in result.output.lower()


# Scenario 16
def test_done_on_completed_run_is_refused(tmp_path, monkeypatch):
    """Given a completed run, When I run wtf done, Then exit 2 and the output says it is already completed."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    run_id = only_run(tmp_path)
    done(tmp_path, monkeypatch, "--trigger", "tests_written")
    done(tmp_path, monkeypatch, "--trigger", "approve")
    result = done(tmp_path, monkeypatch)
    assert result.exit_code == 2, result.output
    assert "already completed" in result.output.lower()
    assert read_state(tmp_path, run_id)["current_state"] == "done"


# Scenario 17
def test_done_with_no_running_run_is_an_error(tmp_path, monkeypatch):
    """Given no running run and no --run, When I run wtf done, Then exit 1 and the output says no running run was found."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    result = done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert result.exit_code == 1, result.output
    assert "no running run" in result.output.lower()


# Scenario 18
def test_done_without_run_acts_on_most_recent_running_run(tmp_path, monkeypatch):
    """Given several runs, When I run wtf done without --run, Then it acts on the most recent running run."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    start(tmp_path, monkeypatch)
    first, second = run_ids(tmp_path)
    done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert read_state(tmp_path, second)["current_state"] == "green"
    assert read_state(tmp_path, first)["current_state"] == "red"


def test_done_with_run_targets_that_run(tmp_path, monkeypatch):
    """Given several runs, When I run wtf done --run <id>, Then it acts on that run."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BASE)
    start(tmp_path, monkeypatch)
    start(tmp_path, monkeypatch)
    first, second = run_ids(tmp_path)
    done(tmp_path, monkeypatch, "--run", first, "--trigger", "tests_written")
    assert read_state(tmp_path, first)["current_state"] == "green"
    assert read_state(tmp_path, second)["current_state"] == "red"


# Scenario 19
def test_field_eq_guard_reads_run_inputs(tmp_path, monkeypatch):
    """Given a field_eq guard and inputs containing the field with the expected value, Then the guard passes."""
    init_project(tmp_path, monkeypatch)
    data = wf()
    data["transitions"][0]["guards"] = [{"type": "field_eq", "params": {"field": "stage", "value": "ready"}}]
    write_wf(tmp_path, data)
    start(tmp_path, monkeypatch, extra=["--input", '{"stage": "ready"}'])
    run_id = only_run(tmp_path)
    result = done(tmp_path, monkeypatch, "--trigger", "tests_written")
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "green"

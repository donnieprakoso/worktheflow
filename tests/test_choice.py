"""Tests for Choice: auto-resolving wtf done via existing guards (Use Case #22). One test per GWT scenario."""

import json

import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0


def write_wf(tmp_path, data, name="demo"):
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def start_run(tmp_path, monkeypatch, input_json="{}"):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["start", "demo", "--input", input_json])
    assert result.exit_code == 0, result.output
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    return index["runs"][-1]["run_id"]


def read_state(tmp_path, run_id):
    return json.loads((tmp_path / ".wtf" / "runs" / run_id / "state.json").read_text())


def read_events(tmp_path, run_id):
    path = tmp_path / ".wtf" / "runs" / run_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def do(tmp_path, monkeypatch, *args):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["done", *args])


# Base: a gate state with two guarded candidates and one unconditional (default), last.
GATE_WF = {
    "name": "demo",
    "version": "1.0",
    "initial": "gate",
    "states": [
        {"name": "gate"},
        {"name": "path_a"},
        {"name": "path_b"},
        {"name": "path_default", "terminal": True},
    ],
    "transitions": [
        {
            "trigger": "to_a",
            "source": "gate",
            "dest": "path_a",
            "guards": [{"type": "field_eq", "params": {"field": "decision", "value": "A"}}],
        },
        {
            "trigger": "to_b",
            "source": "gate",
            "dest": "path_b",
            "guards": [{"type": "field_eq", "params": {"field": "decision", "value": "B"}}],
        },
        {"trigger": "to_default", "source": "gate", "dest": "path_default"},
        {"trigger": "a_done", "source": "path_a", "dest": "path_default"},
        {"trigger": "b_done", "source": "path_b", "dest": "path_default"},
    ],
}


# Scenario 1
def test_takes_first_candidate_when_only_its_guards_pass(tmp_path, monkeypatch):
    """Given 2 guarded candidates where only the first passes, When I run wtf done with no --trigger, Then it takes the first."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATE_WF)
    run_id = start_run(tmp_path, monkeypatch, '{"decision": "A"}')
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "path_a"


# Scenario 2
def test_takes_second_candidate_when_only_its_guards_pass(tmp_path, monkeypatch):
    """Given 2 guarded candidates where only the second passes, When I run wtf done with no --trigger, Then it takes the second."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATE_WF)
    run_id = start_run(tmp_path, monkeypatch, '{"decision": "B"}')
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "path_b"


# Scenario 3
def test_no_guards_anywhere_is_unchanged_ambiguous_error(tmp_path, monkeypatch):
    """Given no candidate among 2+ has any guards, When I run wtf done with no --trigger, Then it still errors and lists options."""
    import copy
    data = copy.deepcopy(GATE_WF)
    for t in data["transitions"]:
        t.pop("guards", None)
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    run_id = start_run(tmp_path, monkeypatch)
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 2, result.output
    assert "to_a" in result.output
    assert read_state(tmp_path, run_id)["current_state"] == "gate"


# Scenario 4
def test_falls_through_to_unconditional_default_when_guarded_ones_dont_match(tmp_path, monkeypatch):
    """Given 2 guarded candidates plus an unconditional one last, where neither guarded one matches, Then it takes the unconditional default."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, GATE_WF)
    run_id = start_run(tmp_path, monkeypatch, '{"decision": "C"}')  # matches neither A nor B
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert read_state(tmp_path, run_id)["current_state"] == "path_default"


# Scenario 5
def test_no_match_and_no_default_reports_every_failure(tmp_path, monkeypatch):
    """Given 2+ guarded candidates where none match and there is no unconditional fallback, Then it exits 2 and reports every failure."""
    import copy
    data = copy.deepcopy(GATE_WF)
    # Remove only the unconditional default transition out of "gate"; path_a and
    # path_b keep their own valid routes to path_default, so the workflow stays
    # valid (no dead ends) even though "gate" itself has no catch-all anymore.
    data["transitions"] = [t for t in data["transitions"] if t["trigger"] != "to_default"]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    run_id = start_run(tmp_path, monkeypatch, '{"decision": "C"}')
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 2, result.output
    assert "to_a" in result.output
    assert "to_b" in result.output
    assert read_state(tmp_path, run_id)["current_state"] == "gate"


# Scenario 6
def test_auto_matched_candidate_requiring_approval_auto_proposes(tmp_path, monkeypatch):
    """Given the auto-matched candidate requires approval, Then the run becomes pending_approval with a proposed event, not a transition event."""
    import copy
    data = copy.deepcopy(GATE_WF)
    for t in data["transitions"]:
        if t["trigger"] == "to_a":
            t["require_approval"] = True
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    run_id = start_run(tmp_path, monkeypatch, '{"decision": "A"}')
    result = do(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    state = read_state(tmp_path, run_id)
    assert state["status"] == "pending_approval"
    assert state["current_state"] == "gate"
    events = read_events(tmp_path, run_id)
    assert any(e["type"] == "proposed" for e in events)
    assert not any(e["type"] == "transition" for e in events)


# Scenario 7
def test_explicit_trigger_on_gated_transition_is_unchanged(tmp_path, monkeypatch):
    """Given --trigger explicitly names a transition that requires approval, Then it still refuses and points to wtf propose."""
    import copy
    data = copy.deepcopy(GATE_WF)
    for t in data["transitions"]:
        if t["trigger"] == "to_a":
            t["require_approval"] = True
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    run_id = start_run(tmp_path, monkeypatch, '{"decision": "A"}')
    result = do(tmp_path, monkeypatch, "--trigger", "to_a")
    assert result.exit_code == 2, result.output
    assert "wtf propose to_a" in result.output
    assert read_state(tmp_path, run_id)["status"] == "running"

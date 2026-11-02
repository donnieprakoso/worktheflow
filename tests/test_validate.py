"""Tests for wtf validate (Use Case #2). One test per GWT scenario."""

import copy
import json

import pytest
import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()

# A valid workflow in the current list-based shape. Each test mutates a copy.
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


def write_wf(tmp_path, content, name="demo", ext=".yaml"):
    """Write a workflow file under .wtf/workflows/. Dicts are serialized; strings are written as-is."""
    wf_dir = tmp_path / ".wtf" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    path = wf_dir / f"{name}{ext}"
    if isinstance(content, str):
        path.write_text(content)
    elif ext == ".json":
        path.write_text(json.dumps(content))
    else:
        path.write_text(yaml.safe_dump(content, sort_keys=False))
    return path


def wf(**changes):
    """Copy BASE and apply changes (a dict of top-level keys to replace)."""
    data = copy.deepcopy(BASE)
    data.update(changes)
    return data


def validate(tmp_path, monkeypatch, name="demo"):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["validate", name])


# Scenario 1
def test_valid_yaml_workflow_exits_zero(tmp_path, monkeypatch):
    """Given a valid .yaml workflow, When I run wtf validate, Then it exits 0 and reports valid."""
    write_wf(tmp_path, BASE)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert "valid" in result.output.lower()


# Scenario 2
def test_valid_json_workflow_exits_zero(tmp_path, monkeypatch):
    """Given the same workflow saved as .json, When I run wtf validate, Then it exits 0."""
    write_wf(tmp_path, BASE, ext=".json")
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output


# Scenario 3
@pytest.mark.parametrize("field", ["name", "initial", "states", "transitions"])
def test_missing_required_field_is_reported(tmp_path, monkeypatch, field):
    """Given a workflow missing a required field, When I validate it, Then it exits 1 and names the field."""
    data = copy.deepcopy(BASE)
    del data[field]
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert field in result.output


# Scenario 4
def test_initial_not_in_states_is_reported(tmp_path, monkeypatch):
    """Given initial names a state that does not exist, When I validate it, Then it exits 1 and names it."""
    write_wf(tmp_path, wf(initial="nowhere"))
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "nowhere" in result.output


# Scenario 5
@pytest.mark.parametrize("end", ["source", "dest"])
def test_transition_to_unknown_state_is_reported(tmp_path, monkeypatch, end):
    """Given a transition whose source or dest is not a state, When I validate it, Then it exits 1 and names the missing state."""
    data = copy.deepcopy(BASE)
    data["transitions"][0][end] = "ghost"
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "ghost" in result.output


# Scenario 6
def test_duplicate_trigger_from_same_state_is_reported(tmp_path, monkeypatch):
    """Given two transitions from the same source with the same trigger, When I validate it, Then it exits 1 and names state and trigger."""
    data = copy.deepcopy(BASE)
    data["transitions"].append({"trigger": "tests_written", "source": "red", "dest": "done"})
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "red" in result.output
    assert "tests_written" in result.output


# Scenario 7
def test_unknown_guard_type_is_reported(tmp_path, monkeypatch):
    """Given a guard with a type outside the fixed set, When I validate it, Then it exits 1 and names the type."""
    data = copy.deepcopy(BASE)
    data["transitions"][0]["guards"] = [{"type": "llm_rubric", "params": {}}]
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "llm_rubric" in result.output


# Scenario 8
def test_guard_missing_required_param_is_reported(tmp_path, monkeypatch):
    """Given a file_exists guard without path, When I validate it, Then it exits 1 and names the missing param."""
    data = copy.deepcopy(BASE)
    data["transitions"][0]["guards"] = [{"type": "file_exists", "params": {}}]
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "path" in result.output


# Scenario 9
def test_no_terminal_state_is_reported(tmp_path, monkeypatch):
    """Given no state has terminal: true, When I validate it, Then it exits 1."""
    data = copy.deepcopy(BASE)
    del data["states"][2]["terminal"]
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "terminal" in result.output


# Scenario 10
def test_non_terminal_state_without_outgoing_transition_is_dead_end(tmp_path, monkeypatch):
    """Given a non-terminal state with no outgoing transitions, When I validate it, Then it exits 1 and names it as a dead end."""
    data = copy.deepcopy(BASE)
    data["transitions"] = [data["transitions"][0]]  # drop green -> done
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "green" in result.output
    assert "dead end" in result.output.lower()


# Scenario 11
def test_terminal_state_with_outgoing_transition_is_reported(tmp_path, monkeypatch):
    """Given a terminal state with an outgoing transition, When I validate it, Then it exits 1 and names it."""
    data = copy.deepcopy(BASE)
    data["transitions"].append({"trigger": "reopen", "source": "done", "dest": "red"})
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "done" in result.output
    assert "terminal" in result.output.lower()


# Scenario 12
def test_no_terminal_reachable_from_initial_is_reported(tmp_path, monkeypatch):
    """Given no terminal state is reachable from initial, When I validate it, Then it exits 1."""
    data = copy.deepcopy(BASE)
    data["transitions"] = [
        {"trigger": "a", "source": "red", "dest": "green"},
        {"trigger": "b", "source": "green", "dest": "red"},
    ]
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "reachable" in result.output.lower()


# Scenario 13
def test_workflow_with_no_transitions_is_reported(tmp_path, monkeypatch):
    """Given a workflow with no transitions, When I validate it, Then it exits 1."""
    write_wf(tmp_path, wf(transitions=[]))
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "transitions" in result.output


# Scenario 14
def test_unreachable_state_is_a_warning_not_an_error(tmp_path, monkeypatch):
    """Given an unreachable state but a valid start-to-end path, When I validate it, Then it exits 0 and warns about the state."""
    data = copy.deepcopy(BASE)
    data["states"].append({"name": "stray", "terminal": True})
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert "warning" in result.output.lower()
    assert "stray" in result.output


# Scenario 15
def test_unknown_key_on_transition_is_reported(tmp_path, monkeypatch):
    """Given a transition with an unknown key (requireApproval), When I validate it, Then it exits 1 and names the key."""
    data = copy.deepcopy(BASE)
    data["transitions"][1]["requireApproval"] = True
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "requireApproval" in result.output


# Scenario 16
def test_several_errors_reported_in_one_run(tmp_path, monkeypatch):
    """Given a workflow with several errors, When I validate it, Then all of them are reported in one run."""
    data = copy.deepcopy(BASE)
    data["initial"] = "nowhere"
    data["transitions"][0]["dest"] = "ghost"
    data["transitions"][0]["guards"] = [{"type": "llm_rubric", "params": {}}]
    write_wf(tmp_path, data)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "nowhere" in result.output
    assert "ghost" in result.output
    assert "llm_rubric" in result.output


# Scenario 17
def test_missing_file_names_searched_paths(tmp_path, monkeypatch):
    """Given no file matches <name>, When I validate it, Then it exits 1 and names the paths it searched."""
    (tmp_path / ".wtf" / "workflows").mkdir(parents=True)
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "demo.yaml" in result.output
    assert "demo.json" in result.output


# Scenario 18
def test_invalid_yaml_gives_parse_error_without_traceback(tmp_path, monkeypatch):
    """Given a file that is not valid YAML, When I validate it, Then it exits 1 with a parse error and no traceback."""
    write_wf(tmp_path, "name: [unclosed\n")
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "parse" in result.output.lower()
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_empty_file_gives_clear_error_without_traceback(tmp_path, monkeypatch):
    """Given an empty workflow file, When I validate it, Then it exits 1 with a clear error and no traceback."""
    write_wf(tmp_path, "")
    result = validate(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "empty" in result.output.lower()
    assert "Traceback" not in result.output

"""Tests for the tools/skills rename (Use Case #16). One test per GWT scenario."""

import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()

BASE = {
    "name": "demo",
    "version": "1.0",
    "initial": "red",
    "states": [{"name": "red"}, {"name": "done", "terminal": True}],
    "transitions": [{"trigger": "go", "source": "red", "dest": "done"}],
}


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0


def write_wf(tmp_path, data, name="demo"):
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# Scenario 1
def test_tools_and_skills_fields_validate(tmp_path, monkeypatch):
    """Given a state with tools and skills, When I validate, Then it passes."""
    import copy
    data = copy.deepcopy(BASE)
    data["states"][0]["tools"] = ["pytest"]
    data["states"][0]["skills"] = ["spec-first-tdd"]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    result = runner.invoke(app, ["validate", "demo"])
    assert result.exit_code == 0, result.output


# Scenario 2
def test_old_allowed_tools_key_is_now_rejected(tmp_path, monkeypatch):
    """Given a state with the old allowed_tools key, When I validate, Then it fails."""
    import copy
    data = copy.deepcopy(BASE)
    data["states"][0]["allowed_tools"] = ["pytest"]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    result = runner.invoke(app, ["validate", "demo"])
    assert result.exit_code == 1, result.output
    assert "allowed_tools" in result.output


def test_old_allowed_skills_key_is_now_rejected(tmp_path, monkeypatch):
    """Given a state with the old allowed_skills key, When I validate, Then it fails."""
    import copy
    data = copy.deepcopy(BASE)
    data["states"][0]["allowed_skills"] = ["spec-first-tdd"]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    result = runner.invoke(app, ["validate", "demo"])
    assert result.exit_code == 1, result.output
    assert "allowed_skills" in result.output


# Use Case #21, Scenario 1
def test_duplicate_state_name_is_rejected(tmp_path, monkeypatch):
    """Given two states with the same name, When I validate, Then it exits 1 and names the duplicate."""
    import copy
    data = copy.deepcopy(BASE)
    data["states"].append({"name": "red"})  # duplicate of the first state
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    result = runner.invoke(app, ["validate", "demo"])
    assert result.exit_code == 1, result.output
    assert "red" in result.output
    assert "duplicate" in result.output.lower()


# Scenario 3
def test_next_output_carries_renamed_fields(tmp_path, monkeypatch):
    """Given tools/skills set on a state, When I run wtf next, Then the embedded node carries the new key names."""
    import copy
    import json
    data = copy.deepcopy(BASE)
    data["states"][0]["tools"] = ["pytest"]
    data["states"][0]["skills"] = ["spec-first-tdd"]
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, data)
    assert runner.invoke(app, ["start", "demo"]).exit_code == 0
    result = runner.invoke(app, ["next"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["node"]["tools"] == ["pytest"]
    assert payload["node"]["skills"] == ["spec-first-tdd"]

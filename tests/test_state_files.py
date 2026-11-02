"""Tests for per-state handoff files (Use Case #23). One test per GWT scenario."""

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from wtf.utils import state_file_path
from wtf.cli import app

runner = CliRunner()

DEMO = {
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
    (tmp_path / ".wtf" / "workflows" / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


# Scenario 1
def test_next_output_includes_state_file_path(tmp_path, monkeypatch):
    """Given a run at state red, When I run wtf next, Then state_file is .wtf/runs/<run_id>/states/red.md."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    assert runner.invoke(app, ["start", "demo"]).exit_code == 0
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    run_id = index["runs"][0]["run_id"]

    result = runner.invoke(app, ["next"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state_file"] == f".wtf/runs/{run_id}/states/red.md"


# Scenario 2
def test_state_file_path_sanitizes_awkward_names():
    """Given a state named 'in review', When I compute its state file path, Then the filename is sanitized."""
    path = state_file_path(Path(".wtf"), "abc-123", "in review")
    assert path == Path(".wtf/runs/abc-123/states/in_review.md")


# Scenario 3
def test_done_succeeds_even_when_state_file_is_missing(tmp_path, monkeypatch):
    """Given the state file does not exist, When I run wtf done, Then the transition still succeeds."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    assert runner.invoke(app, ["start", "demo"]).exit_code == 0
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    run_id = index["runs"][0]["run_id"]
    assert not (tmp_path / ".wtf" / "runs" / run_id / "states" / "red.md").exists()

    result = runner.invoke(app, ["done"])
    assert result.exit_code == 0, result.output

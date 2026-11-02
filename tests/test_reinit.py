"""Tests for re-init safety (Use Case #9). One test per GWT scenario.

The `set-tool` half of Use Case #9 was removed along with `tool` entirely
(see Use Case #15). This file now covers only the re-init refusal.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

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


def with_run(tmp_path, monkeypatch):
    """Init, write the demo workflow, and start one run. Returns the run id."""
    init_project(tmp_path, monkeypatch)
    (tmp_path / ".wtf" / "workflows" / "demo.yaml").write_text(
        "name: demo\ninitial: red\nstates:\n  - name: red\n  - name: done\n    terminal: true\n"
        "transitions:\n  - trigger: go\n    source: red\n    dest: done\n"
    )
    assert runner.invoke(app, ["start", "demo"]).exit_code == 0
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    return index["runs"][0]["run_id"]


# Scenario 1
def test_reinit_is_refused_and_keeps_runs(tmp_path, monkeypatch):
    """Given a project with .wtf/ and a run, When I run wtf init, Then exit 2, the run stays in index.json, and config.json is unchanged."""
    run_id = with_run(tmp_path, monkeypatch)
    before = (tmp_path / ".wtf" / "config.json").read_text()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 2, result.output
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    assert [r["run_id"] for r in index["runs"]] == [run_id]
    assert (tmp_path / ".wtf" / "config.json").read_text() == before

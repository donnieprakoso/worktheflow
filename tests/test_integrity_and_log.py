"""Tests for checksum integrity warnings and wtf log (Use Case #17). One test per GWT scenario."""

import json

import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()

DEMO = {
    "name": "demo",
    "version": "1.0",
    "initial": "red",
    "states": [{"name": "red"}, {"name": "review"}, {"name": "done", "terminal": True}],
    "transitions": [
        {"trigger": "ready", "source": "red", "dest": "review", "require_approval": True},
        {"trigger": "reject", "source": "red", "dest": "red"},
        {"trigger": "approve", "source": "review", "dest": "done"},
        {"trigger": "go", "source": "red", "dest": "done"},
    ],
}


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0


def write_wf(tmp_path, data, name="demo"):
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def state_path(tmp_path, run_id):
    return tmp_path / ".wtf" / "runs" / run_id / "state.json"


def read_state(tmp_path, run_id):
    return json.loads(state_path(tmp_path, run_id).read_text())


def read_events(tmp_path, run_id):
    path = tmp_path / ".wtf" / "runs" / run_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def start_run(tmp_path, monkeypatch):
    before = set()
    index_path = tmp_path / ".wtf" / "index.json"
    if index_path.exists():
        before = {r["run_id"] for r in json.loads(index_path.read_text())["runs"]}
    result = runner.invoke(app, ["start", "demo"])
    assert result.exit_code == 0, result.output
    after = {r["run_id"] for r in json.loads(index_path.read_text())["runs"]}
    new = after - before
    assert len(new) == 1, new
    return new.pop()


def cli(*args):
    return runner.invoke(app, list(args))


# Scenario 1
def test_fresh_run_has_matching_checksum(tmp_path, monkeypatch):
    """Given a freshly created run, When I inspect state.json, Then it contains a _checksum field matching its content."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    run_id = start_run(tmp_path, monkeypatch)
    state = read_state(tmp_path, run_id)
    assert "_checksum" in state
    from wtf.store import RunStore
    assert RunStore(tmp_path).verify_integrity(state) is True


# Scenario 2
def test_tampered_state_warns_and_logs_but_does_not_block(tmp_path, monkeypatch):
    """Given state.json is edited by hand, When I run wtf next, Then a warning is printed, an event is logged, and it still completes."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    run_id = start_run(tmp_path, monkeypatch)

    state = read_state(tmp_path, run_id)
    state["current_state"] = "review"  # hand-edit, bypassing wtf entirely
    state_path(tmp_path, run_id).write_text(json.dumps(state, indent=2))

    result = cli("next")
    assert result.exit_code == 0, result.output
    assert "warning" in result.output.lower()
    assert run_id[:8] in result.output or run_id in result.output
    events = read_events(tmp_path, run_id)
    assert any(e["type"] == "integrity_warning" for e in events)


# Scenario 3
def test_legacy_run_with_no_checksum_field_does_not_warn(tmp_path, monkeypatch):
    """Given a run with no _checksum field, When I load it, Then no warning is printed."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    run_id = start_run(tmp_path, monkeypatch)

    state = read_state(tmp_path, run_id)
    assert state.pop("_checksum", None) is not None
    state_path(tmp_path, run_id).write_text(json.dumps(state, indent=2))  # no _checksum key at all

    result = cli("next")
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output.lower()
    events = read_events(tmp_path, run_id)
    assert not any(e["type"] == "integrity_warning" for e in events)


# Scenario 4
def test_checksum_self_heals_on_next_save(tmp_path, monkeypatch):
    """Given a tampered run that then completes an action, When I inspect state.json afterward, Then the checksum matches the new content."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    run_id = start_run(tmp_path, monkeypatch)

    state = read_state(tmp_path, run_id)
    state["current_state"] = "review"
    state_path(tmp_path, run_id).write_text(json.dumps(state, indent=2))

    result = cli("done", "--trigger", "approve")
    assert result.exit_code == 0, result.output

    from wtf.store import RunStore
    healed = read_state(tmp_path, run_id)
    assert RunStore(tmp_path).verify_integrity(healed) is True


# Scenario 5
def test_log_shows_events_in_order_with_readable_summary_and_reject_reason(tmp_path, monkeypatch):
    """Given a run with several events, When I run wtf log --run <id>, Then each appears in order, readably, with the rejection reason shown."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    run_id = start_run(tmp_path, monkeypatch)
    assert cli("propose", "ready").exit_code == 0
    assert cli("reject", "--reason", "needs more tests").exit_code == 0

    result = cli("log", "--run", run_id)
    assert result.exit_code == 0, result.output
    out = result.output
    assert out.index("run_started") < out.index("proposed") < out.index("rejected")
    assert "needs more tests" in out


# Scenario 6
def test_log_without_run_resolves_most_recent_running(tmp_path, monkeypatch):
    """Given no --run, When I run wtf log, Then it resolves the most recent running run."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    first = start_run(tmp_path, monkeypatch)
    second = start_run(tmp_path, monkeypatch)
    result = cli("log")
    assert result.exit_code == 0, result.output
    assert second in result.output or second[:8] in result.output


# Scenario 7
def test_log_with_no_runs_prints_no_runs_found(tmp_path, monkeypatch):
    """Given no runs exist, When I run wtf log, Then it prints No runs found and exits 0."""
    init_project(tmp_path, monkeypatch)
    result = cli("log")
    assert result.exit_code == 0, result.output
    assert "no runs found" in result.output.lower()


# Scenario 8
def test_log_shows_integrity_warning_event(tmp_path, monkeypatch):
    """Given a run that triggered an integrity warning, When I run wtf log, Then the integrity_warning event appears."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, DEMO)
    run_id = start_run(tmp_path, monkeypatch)
    state = read_state(tmp_path, run_id)
    state["current_state"] = "review"
    state_path(tmp_path, run_id).write_text(json.dumps(state, indent=2))
    assert cli("next").exit_code == 0

    result = cli("log", "--run", run_id)
    assert result.exit_code == 0, result.output
    assert "integrity_warning" in result.output or "checksum" in result.output.lower()

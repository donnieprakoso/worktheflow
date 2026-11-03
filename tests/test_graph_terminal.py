"""Tests for `wtf graph --output terminal/html/mermaid` (Use Case #25). One test per GWT scenario."""

import json

import yaml
from typer.testing import CliRunner

import wtf.preview as preview
from wtf.cli import app

runner = CliRunner()

# a -> b -> branch_state -> {x (terminal), y (terminal)}
LINEAR_WF = {
    "name": "demo",
    "version": "1.0",
    "initial": "a",
    "states": [
        {"name": "a"},
        {"name": "b"},
        {"name": "c", "terminal": True},
    ],
    "transitions": [
        {"trigger": "go1", "source": "a", "dest": "b"},
        {"trigger": "go2", "source": "b", "dest": "c"},
    ],
}

BRANCH_WF = {
    "name": "demo",
    "version": "1.0",
    "initial": "a",
    "states": [
        {"name": "a"},
        {"name": "b"},
        {"name": "branch_state"},
        {"name": "x", "terminal": True},
        {"name": "y", "terminal": True},
    ],
    "transitions": [
        {"trigger": "go1", "source": "a", "dest": "b"},
        {"trigger": "go2", "source": "b", "dest": "branch_state"},
        {
            "trigger": "to_x",
            "source": "branch_state",
            "dest": "x",
            "guards": [{"type": "field_eq", "params": {"field": "decision", "value": "X"}}],
        },
        {"trigger": "to_y", "source": "branch_state", "dest": "y"},
    ],
}

# intake -> fork_state (fork) -> {track_a (branch_end), track_b_step1 -> track_b_step2 (branch_end)}
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


def start_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["start", "demo"]).exit_code == 0
    index = json.loads((tmp_path / ".wtf" / "index.json").read_text())
    return index["runs"][-1]["run_id"]


def stub_browser(monkeypatch, display=True, opened=True):
    asked = []
    monkeypatch.setattr(preview, "can_open_browser", lambda env=None, platform=None: display)

    def fake_open(html_path):
        asked.append(html_path)
        return opened

    monkeypatch.setattr(preview, "open_in_browser", fake_open)
    return asked


def strip_markup(text):
    """Rich markup tags like [bold] leave the CliRunner's captured plain text
    alone (console isn't a real tty here), so the structural characters
    (numbers, icons) are already what we need to assert on directly."""
    return text


# Scenario 1
def test_terminal_output_linear_workflow_no_run(tmp_path, monkeypatch):
    """Given a workflow with no branches and no run, When I run wtf graph demo --output terminal, Then it prints a flat-numbered tree with no run markers."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    result = runner.invoke(app, ["graph", "demo", "--output", "terminal"])
    assert result.exit_code == 0, result.output
    out = strip_markup(result.output)
    assert "[1]" in out and "a" in out
    assert "[2]" in out and "b" in out
    assert "[3]" in out and "c" in out
    assert "●" not in out and "✓" not in out
    assert "○" in out and "◆" in out


# Scenario 2
def test_terminal_output_opens_decimal_numbering_at_branch(tmp_path, monkeypatch):
    """Given a branch point mid-chain, When rendered with --output terminal, Then numbering stays flat up to the branch and opens decimal only there."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, BRANCH_WF)
    result = runner.invoke(app, ["graph", "demo", "--output", "terminal"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "[1]" in out  # a
    assert "[2]" in out  # b
    assert "[3]" in out  # branch_state
    assert "[3.1]" in out  # x
    assert "[3.2]" in out  # y
    assert "[3.1.1]" not in out  # no spurious deeper nesting


# Scenario 3
def test_terminal_output_overlays_active_run_progress(tmp_path, monkeypatch):
    """Given an active run that has advanced one step, When I run wtf graph demo --output terminal with no --run, Then the passed state is done and the current state is marked current."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    start_run(tmp_path, monkeypatch)
    assert runner.invoke(app, ["done"]).exit_code == 0  # a -> b

    result = runner.invoke(app, ["graph", "demo", "--output", "terminal"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    a_line = next(l for l in lines if l.strip().endswith("a") or " a " in l)
    b_line = next(l for l in lines if l.rstrip().endswith("b"))
    assert "✓" in a_line
    assert "●" in b_line


# Scenario 4
def test_terminal_output_marks_every_active_branch_current(tmp_path, monkeypatch):
    """Given a forked run with two active branches, When rendered with --output terminal, Then both branches' current states are marked current at once."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, FORK_WF)
    start_run(tmp_path, monkeypatch)
    assert runner.invoke(app, ["done"]).exit_code == 0  # intake -> fork_state
    assert runner.invoke(app, ["done"]).exit_code == 0  # fork

    result = runner.invoke(app, ["graph", "demo", "--output", "terminal"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    a_line = next(l for l in lines if l.rstrip().endswith("track_a"))
    b_line = next(l for l in lines if l.rstrip().endswith("track_b_step1"))
    assert "●" in a_line
    assert "●" in b_line


# Scenario 5
def test_default_output_unchanged_mermaid(tmp_path, monkeypatch):
    """Given no --output flag, When I run wtf graph demo, Then it prints the Mermaid diagram exactly as before this use case."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    result = runner.invoke(app, ["graph", "demo"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "stateDiagram-v2"
    assert "[1]" not in result.output


# Scenario 6
def test_output_html_behaves_like_preview(tmp_path, monkeypatch):
    """Given --output html, When I run wtf graph demo --output html, Then it writes and opens the browser preview, same as --preview."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    asked = stub_browser(monkeypatch)
    result = runner.invoke(app, ["graph", "demo", "--output", "html"])
    assert result.exit_code == 0, result.output
    assert len(asked) == 1
    assert (tmp_path / ".wtf" / "preview" / "demo.html").exists()


# Scenario 7
def test_terminal_output_rejects_preview_flag(tmp_path, monkeypatch):
    """Given --output terminal combined with --preview, When I run the command, Then it is refused as a usage error."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    result = runner.invoke(app, ["graph", "demo", "--output", "terminal", "--preview"])
    assert result.exit_code == 1, result.output
    assert "--preview" in result.output


# Scenario 8
def test_terminal_output_unknown_run_id_fails_clearly(tmp_path, monkeypatch):
    """Given --run naming a run that does not exist, When I run wtf graph demo --output terminal --run <id>, Then it fails with exit 1, not a silent fallback."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    result = runner.invoke(app, ["graph", "demo", "--output", "terminal", "--run", "nope"])
    assert result.exit_code == 1, result.output
    assert "not found" in result.output.lower()


# Scenario 9
def test_terminal_output_no_run_yet_renders_bare_structure(tmp_path, monkeypatch):
    """Given no run exists yet for the workflow, When I run --output terminal with no --run, Then it renders the structure with no error and no current/done markers."""
    init_project(tmp_path, monkeypatch)
    write_wf(tmp_path, LINEAR_WF)
    result = runner.invoke(app, ["graph", "demo", "--output", "terminal"])
    assert result.exit_code == 0, result.output
    assert "●" not in result.output and "✓" not in result.output

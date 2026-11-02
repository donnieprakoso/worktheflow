"""Tests for wtf graph (Use Case #7). One test per GWT scenario."""

import copy

import yaml
from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()

# red --ready (gated, 2 guards)--> review --approve--> done (terminal)
BASE = {
    "name": "demo",
    "version": "1.0",
    "initial": "red",
    "states": [
        {"name": "red"},
        {"name": "review"},
        {"name": "done", "terminal": True},
    ],
    "transitions": [
        {
            "trigger": "ready",
            "source": "red",
            "dest": "review",
            "require_approval": True,
            "guards": [
                {"type": "file_exists", "params": {"path": "a.txt"}},
                {"type": "file_exists", "params": {"path": "b.txt"}},
            ],
        },
        {"trigger": "approve", "source": "review", "dest": "done"},
    ],
}


def setup(tmp_path, monkeypatch, data=None, name="demo"):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data if data is not None else BASE, sort_keys=False))


def graph(tmp_path, monkeypatch, name="demo"):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["graph", name])


def lines(result):
    return [line.strip() for line in result.output.splitlines() if line.strip()]


# Scenario 1
def test_graph_starts_with_stateDiagram_header(tmp_path, monkeypatch):
    """Given a valid workflow, When I run wtf graph, Then the first line is stateDiagram-v2 and exit is 0."""
    setup(tmp_path, monkeypatch)
    result = graph(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.output
    assert lines(result)[0] == "stateDiagram-v2"


# Scenario 2
def test_graph_marks_initial_state(tmp_path, monkeypatch):
    """Given initial state red, When I run wtf graph, Then the output contains [*] --> red."""
    setup(tmp_path, monkeypatch)
    assert "[*] --> red" in lines(graph(tmp_path, monkeypatch))


# Scenario 3
def test_graph_draws_transition_with_trigger_label(tmp_path, monkeypatch):
    """Given a transition red -> review with trigger ready, When I run wtf graph, Then the output contains red --> review : ready-label."""
    setup(tmp_path, monkeypatch)
    out = lines(graph(tmp_path, monkeypatch))
    assert any(line.startswith("red --> review : ready") for line in out), out


# Scenario 4
def test_graph_marks_terminal_state(tmp_path, monkeypatch):
    """Given a terminal state done, When I run wtf graph, Then the output contains done --> [*]."""
    setup(tmp_path, monkeypatch)
    assert "done --> [*]" in lines(graph(tmp_path, monkeypatch))


# Scenario 5
def test_graph_labels_gated_transition(tmp_path, monkeypatch):
    """Given a transition with require_approval, When I run wtf graph, Then its label contains (approval)."""
    setup(tmp_path, monkeypatch)
    out = lines(graph(tmp_path, monkeypatch))
    assert any("red --> review" in line and "(approval)" in line for line in out), out


# Scenario 6
def test_graph_labels_guard_count(tmp_path, monkeypatch):
    """Given a transition with two guards, When I run wtf graph, Then its label contains (guards: 2)."""
    setup(tmp_path, monkeypatch)
    out = lines(graph(tmp_path, monkeypatch))
    assert any("red --> review" in line and "(guards: 2)" in line for line in out), out


# Scenario 7
def test_graph_aliases_names_with_spaces(tmp_path, monkeypatch):
    """Given a state named 'in review', When I run wtf graph, Then it is declared as state "in review" as s<n> and transitions use s<n>."""
    data = copy.deepcopy(BASE)
    data["states"][1]["name"] = "in review"
    data["transitions"][0]["dest"] = "in review"
    data["transitions"][1]["source"] = "in review"
    setup(tmp_path, monkeypatch, data)
    out = lines(graph(tmp_path, monkeypatch))
    decl = [line for line in out if line.startswith('state "in review" as ')]
    assert len(decl) == 1, out
    alias = decl[0].split(" as ")[1]
    assert alias.startswith("s")
    assert any(line.startswith(f"red --> {alias} :") for line in out), out
    assert any(line.startswith(f"{alias} --> done :") for line in out), out


# Scenario 8
def test_graph_aliases_reserved_word_end(tmp_path, monkeypatch):
    """Given a state named end, When I run wtf graph, Then it is declared with an alias, not used as a bare id."""
    data = copy.deepcopy(BASE)
    data["states"][1]["name"] = "end"
    data["transitions"][0]["dest"] = "end"
    data["transitions"][1]["source"] = "end"
    setup(tmp_path, monkeypatch, data)
    out = lines(graph(tmp_path, monkeypatch))
    assert 'state "end" as ' in "\n".join(out), out
    assert not any(line.startswith("end ") for line in out), out


# Scenario 9
def test_graph_replaces_colon_in_trigger_label(tmp_path, monkeypatch):
    """Given a trigger containing a colon, When I run wtf graph, Then the colon in the label is replaced with -."""
    data = copy.deepcopy(BASE)
    data["transitions"][1]["trigger"] = "approve:final"
    setup(tmp_path, monkeypatch, data)
    out = lines(graph(tmp_path, monkeypatch))
    assert any(line.startswith("review --> done : approve-final") for line in out), out


# Scenario 10
def test_graph_refuses_invalid_workflow(tmp_path, monkeypatch):
    """Given an invalid workflow, When I run wtf graph, Then exit 1, the errors are shown, and no stateDiagram-v2 line is printed."""
    data = copy.deepcopy(BASE)
    del data["initial"]
    setup(tmp_path, monkeypatch, data)
    result = graph(tmp_path, monkeypatch)
    assert result.exit_code == 1, result.output
    assert "initial" in result.output
    assert "stateDiagram-v2" not in result.output


# Scenario 11
def test_graph_missing_workflow_is_an_error(tmp_path, monkeypatch):
    """Given no matching workflow file, When I run wtf graph, Then exit 1."""
    setup(tmp_path, monkeypatch)
    result = graph(tmp_path, monkeypatch, name="nope")
    assert result.exit_code == 1, result.output


# Scenario 12
def test_graph_output_is_deterministic(tmp_path, monkeypatch):
    """Given the same workflow, When I run wtf graph twice, Then the output is identical."""
    setup(tmp_path, monkeypatch)
    first = graph(tmp_path, monkeypatch).output
    second = graph(tmp_path, monkeypatch).output
    assert first == second

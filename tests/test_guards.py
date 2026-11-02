"""Tests for the fixed guard set (Use Case #5). One test per GWT scenario."""

import wtf.guards as guards
from wtf.engine import WtfEngine
from wtf.guards import GuardEvaluator

evaluator = GuardEvaluator()


def ev(guard_type, context=None, **params):
    return evaluator.evaluate({"type": guard_type, "params": params}, context or {})


# ---- file_exists ----

# Scenario 1
def test_file_exists_passes_for_file_and_directory(tmp_path, monkeypatch):
    """Given a path that exists as a file or a directory, When file_exists runs, Then it passes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "d").mkdir()
    assert ev("file_exists", path="a.txt")[0] is True
    assert ev("file_exists", path="d")[0] is True


# Scenario 2
def test_file_exists_fails_for_missing_path_and_names_it(tmp_path, monkeypatch):
    """Given a missing path, When file_exists runs, Then it fails and the message names the path."""
    monkeypatch.chdir(tmp_path)
    passed, message = ev("file_exists", path="missing.txt")
    assert passed is False
    assert "missing.txt" in message


# ---- file_contains ----

# Scenario 3
def test_file_contains_passes_when_pattern_present(tmp_path, monkeypatch):
    """Given a file containing the pattern, When file_contains runs, Then it passes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("all tests green")
    assert ev("file_contains", path="notes.md", pattern="green")[0] is True


# Scenario 4
def test_file_contains_fails_when_pattern_absent(tmp_path, monkeypatch):
    """Given a file without the pattern, When file_contains runs, Then it fails."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("all tests red")
    assert ev("file_contains", path="notes.md", pattern="green")[0] is False


# Scenario 5
def test_file_contains_fails_for_missing_file(tmp_path, monkeypatch):
    """Given a missing file, When file_contains runs, Then it fails and says the file does not exist."""
    monkeypatch.chdir(tmp_path)
    passed, message = ev("file_contains", path="notes.md", pattern="green")
    assert passed is False
    assert "does not exist" in message


# ---- command_passes / command_fails ----

# Scenario 6
def test_command_passes_on_exit_zero_in_project_directory(tmp_path, monkeypatch):
    """Given a command that exits 0 in the project directory, When command_passes runs, Then it passes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "marker.txt").write_text("here")
    assert ev("command_passes", command="test -f marker.txt")[0] is True


# Scenario 7
def test_command_passes_fails_on_nonzero_and_reports_exit_code(tmp_path, monkeypatch):
    """Given a command that exits non-zero, When command_passes runs, Then it fails and the message includes the exit code."""
    monkeypatch.chdir(tmp_path)
    passed, message = ev("command_passes", command="exit 3")
    assert passed is False
    assert "3" in message


# Scenario 8
def test_command_fails_passes_on_nonzero(tmp_path, monkeypatch):
    """Given a command that exits non-zero, When command_fails runs, Then it passes."""
    monkeypatch.chdir(tmp_path)
    assert ev("command_fails", command="exit 1")[0] is True


# Scenario 9
def test_command_fails_fails_on_zero(tmp_path, monkeypatch):
    """Given a command that exits 0, When command_fails runs, Then it fails."""
    monkeypatch.chdir(tmp_path)
    assert ev("command_fails", command="exit 0")[0] is False


# Scenario 10
def test_command_timeout_is_a_failure_for_both_command_guards(tmp_path, monkeypatch):
    """Given a command that runs past the timeout, When command_passes or command_fails runs, Then it fails and says it timed out."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(guards, "COMMAND_TIMEOUT_SECONDS", 0.5)
    for guard_type in ("command_passes", "command_fails"):
        passed, message = ev(guard_type, command="sleep 5")
        assert passed is False, guard_type
        assert "timed out" in message, message


# ---- field_eq / field_ne ----

# Scenario 11
def test_field_eq_passes_only_when_equal(tmp_path, monkeypatch):
    """Given an input equal to the value, When field_eq runs, Then it passes; when different or missing, it fails."""
    monkeypatch.chdir(tmp_path)
    context = {"stage": "ready"}
    assert ev("field_eq", context, field="stage", value="ready")[0] is True
    assert ev("field_eq", context, field="stage", value="draft")[0] is False
    assert ev("field_eq", {}, field="stage", value="ready")[0] is False


# Scenario 12
def test_field_ne_passes_when_different_or_missing(tmp_path, monkeypatch):
    """Given an input different from the value, When field_ne runs, Then it passes; when equal, it fails; when missing, it passes."""
    monkeypatch.chdir(tmp_path)
    context = {"stage": "ready"}
    assert ev("field_ne", context, field="stage", value="draft")[0] is True
    assert ev("field_ne", context, field="stage", value="ready")[0] is False
    assert ev("field_ne", {}, field="stage", value="ready")[0] is True


# ---- defensive cases ----

# Scenario 13
def test_missing_required_param_fails_without_raising(tmp_path, monkeypatch):
    """Given a guard missing a required param, When it runs, Then it fails with a message naming the param and does not raise."""
    monkeypatch.chdir(tmp_path)
    passed, message = evaluator.evaluate({"type": "file_exists", "params": {}}, {})
    assert passed is False
    assert "path" in message


# Scenario 14
def test_unknown_guard_type_fails_and_names_type(tmp_path, monkeypatch):
    """Given an unknown guard type, When it runs, Then it fails with a message naming the type."""
    monkeypatch.chdir(tmp_path)
    passed, message = evaluator.evaluate({"type": "llm_rubric", "params": {}}, {})
    assert passed is False
    assert "llm_rubric" in message


# ---- AND semantics through the engine ----

# Scenario 15
def test_guards_stop_at_first_failure(tmp_path, monkeypatch):
    """Given guards [A, B] where A fails, When the transition is evaluated, Then B is not run and only A's message is reported."""
    monkeypatch.chdir(tmp_path)
    transition = {
        "trigger": "t",
        "source": "a",
        "dest": "b",
        "guards": [
            {"type": "file_exists", "params": {"path": "missing.txt"}},
            {"type": "command_passes", "params": {"command": "touch ran.txt"}},
        ],
    }
    engine = WtfEngine(tmp_path)
    passed, messages = engine.evaluate_transition_guards(transition, {})
    assert passed is False
    assert len(messages) == 1
    assert "missing.txt" in messages[0]
    assert not (tmp_path / "ran.txt").exists()


# Scenario 16
def test_all_passing_guards_pass_and_report_every_message(tmp_path, monkeypatch):
    """Given guards that all pass, When the transition is evaluated, Then it passes and reports every message."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.txt").write_text("yes")
    transition = {
        "trigger": "t",
        "source": "a",
        "dest": "b",
        "guards": [
            {"type": "file_exists", "params": {"path": "ok.txt"}},
            {"type": "file_contains", "params": {"path": "ok.txt", "pattern": "yes"}},
        ],
    }
    engine = WtfEngine(tmp_path)
    passed, messages = engine.evaluate_transition_guards(transition, {})
    assert passed is True
    assert len(messages) == 2

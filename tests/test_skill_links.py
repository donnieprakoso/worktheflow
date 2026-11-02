"""Tests for the skill link scripts (Use Case #12). One test per GWT scenario.

Each test runs the real script with HOME pointed at a temp folder, so the
developer's own home is never touched.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"
SKILL_SRC = SKILLS_DIR / "wtf"

# script name -> the path under HOME it manages
TARGETS = {
    "claude.sh": ".claude/skills/wtf",
    "kiro.sh": ".kiro/skills/wtf",
    "opencode.sh": ".config/opencode/skills/wtf",
}
SCRIPTS = sorted(TARGETS)


def run(script, action, home):
    return subprocess.run(
        [str(SKILLS_DIR / script), action],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


def target(script, home):
    return home / TARGETS[script]


# Scenario 1
@pytest.mark.parametrize("script", SCRIPTS)
def test_link_creates_symlink_to_repo_skill(script, tmp_path):
    """Given no link, When I run link, Then a symlink to the repo skill is created and exit is 0."""
    result = run(script, "link", tmp_path)
    assert result.returncode == 0, result.stderr
    link = target(script, tmp_path)
    assert link.is_symlink()
    assert Path(os.readlink(link)) == SKILL_SRC
    assert (link / "SKILL.md").is_file()


# Scenario 2
@pytest.mark.parametrize("script", SCRIPTS)
def test_link_is_idempotent(script, tmp_path):
    """Given the link already exists, When I run link again, Then exit is 0 and it says already linked."""
    run(script, "link", tmp_path)
    result = run(script, "link", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "already linked" in result.stdout
    assert target(script, tmp_path).is_symlink()


# Scenario 3
@pytest.mark.parametrize("script", SCRIPTS)
def test_unlink_removes_our_link(script, tmp_path):
    """Given our link exists, When I run unlink, Then it is removed and exit is 0."""
    run(script, "link", tmp_path)
    result = run(script, "unlink", tmp_path)
    assert result.returncode == 0, result.stderr
    assert not target(script, tmp_path).exists()
    assert not target(script, tmp_path).is_symlink()


# Scenario 4
@pytest.mark.parametrize("script", SCRIPTS)
def test_unlink_with_nothing_there_is_not_an_error(script, tmp_path):
    """Given no link, When I run unlink, Then exit is 0 and it says there is nothing to unlink."""
    result = run(script, "unlink", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "nothing to unlink" in result.stdout


# Scenario 5
@pytest.mark.parametrize("script", SCRIPTS)
def test_link_refuses_to_overwrite_a_real_directory(script, tmp_path):
    """Given a real directory in the way, When I run link, Then exit 1 and the directory is untouched."""
    path = target(script, tmp_path)
    path.mkdir(parents=True)
    (path / "mine.md").write_text("do not delete")
    result = run(script, "link", tmp_path)
    assert result.returncode == 1
    assert "not a link" in result.stderr
    assert not path.is_symlink()
    assert (path / "mine.md").read_text() == "do not delete"


# Scenario 6
@pytest.mark.parametrize("script", SCRIPTS)
def test_unlink_refuses_to_remove_a_real_directory(script, tmp_path):
    """Given a real directory in the way, When I run unlink, Then exit 1 and the directory is untouched."""
    path = target(script, tmp_path)
    path.mkdir(parents=True)
    (path / "mine.md").write_text("do not delete")
    result = run(script, "unlink", tmp_path)
    assert result.returncode == 1
    assert (path / "mine.md").read_text() == "do not delete"


# Scenario 7
@pytest.mark.parametrize("script", SCRIPTS)
def test_link_refuses_when_a_foreign_link_is_there(script, tmp_path):
    """Given a link to something else, When I run link, Then exit 1 and that link is left alone."""
    other = tmp_path / "someone-elses-skill"
    other.mkdir()
    path = target(script, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(other)
    result = run(script, "link", tmp_path)
    assert result.returncode == 1
    assert Path(os.readlink(path)) == other


# Scenario 8
@pytest.mark.parametrize("script", SCRIPTS)
def test_unlink_refuses_to_remove_a_foreign_link(script, tmp_path):
    """Given a link to something else, When I run unlink, Then exit 1 and that link is left alone."""
    other = tmp_path / "someone-elses-skill"
    other.mkdir()
    path = target(script, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(other)
    result = run(script, "unlink", tmp_path)
    assert result.returncode == 1
    assert path.is_symlink()
    assert Path(os.readlink(path)) == other


# Scenario 9
@pytest.mark.parametrize("script", SCRIPTS)
def test_unknown_action_prints_usage_and_exits_2(script, tmp_path):
    """Given an unknown action, When I run the script, Then exit 2 and usage is printed."""
    result = run(script, "frobnicate", tmp_path)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert not target(script, tmp_path).exists()


# Scenario 10
@pytest.mark.parametrize("script", SCRIPTS)
def test_status_reports_both_states(script, tmp_path):
    """Given no link and then a link, When I run status, Then it reports not linked and then linked."""
    before = run(script, "status", tmp_path)
    assert before.returncode == 0, before.stderr
    assert "not linked" in before.stdout
    run(script, "link", tmp_path)
    after = run(script, "status", tmp_path)
    assert after.returncode == 0, after.stderr
    assert "not linked" not in after.stdout
    assert "linked" in after.stdout


# Scenario 11
@pytest.mark.parametrize("script,expected", sorted(TARGETS.items()))
def test_each_script_manages_its_documented_path(script, expected, tmp_path):
    """Given each script, When I run link, Then it creates the link at that tool's documented path."""
    result = run(script, "link", tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / expected).is_symlink()
    others = {p for s, p in TARGETS.items() if s != script}
    for other in others:
        assert not (tmp_path / other).exists(), f"{script} should not touch {other}"


# Scenario 12
def test_scripts_are_executable():
    """Given the three scripts, When I check them, Then each is executable."""
    for script in SCRIPTS:
        assert os.access(SKILLS_DIR / script, os.X_OK), script

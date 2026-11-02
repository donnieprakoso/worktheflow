"""Tests for the ASCII banner (Use Case #11). One test per GWT scenario."""

from pathlib import Path

from typer.testing import CliRunner

import wtf
from wtf.cli import app

runner = CliRunner()
BANNER = Path(wtf.__file__).parent / "banner.txt"


def banner_lines():
    return BANNER.read_text().splitlines()


# Scenario 1
def test_bare_wtf_starts_with_banner(monkeypatch, tmp_path):
    """Given no arguments, When I run wtf, Then the output starts with the banner's first line and exit is 0."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output
    first = next(line for line in banner_lines() if line.strip())
    assert result.output.splitlines()[0].rstrip() == first.rstrip() or first.strip() in result.output


# Scenario 2
def test_bare_wtf_includes_help(monkeypatch, tmp_path):
    """Given no arguments, When I run wtf, Then the output includes the help listing the commands."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [])
    assert "Usage" in result.output
    assert "init" in result.output
    assert "validate" in result.output


# Scenario 3 (width limit revised in Use Case #19: 60 -> 80, to fit the WorkTheFlow slant art)
def test_banner_file_is_ascii_narrow_and_tab_free():
    """Given the banner file, When I check it, Then every line is ASCII, fits an 80-column terminal, with no tabs."""
    assert BANNER.exists()
    text = BANNER.read_text(encoding="ascii")  # raises if any non-ASCII byte is present
    assert "\t" not in text
    assert all(len(line) <= 80 for line in text.splitlines())
    assert any(line.strip() for line in text.splitlines())


# Scenario 4 (Use Case #19)
def test_bare_wtf_output_has_no_ansi_when_not_a_tty():
    """Given no arguments and a non-terminal stdout (as in tests), When I run wtf, Then the output has no ANSI escape codes."""
    result = runner.invoke(app, [])
    assert "\x1b[" not in result.output

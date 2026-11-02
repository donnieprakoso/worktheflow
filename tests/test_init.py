"""Tests for wtf init command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from wtf.cli import app

runner = CliRunner()


def test_init_creates_wtf_directory(tmp_path, monkeypatch):
    """Given I am in a project directory with no .wtf/ folder, When I run wtf init, Then it creates .wtf/ directory"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf").exists()
    assert Path(".wtf").is_dir()


def test_init_creates_config_json(tmp_path, monkeypatch):
    """Given wtf init completes, When I check the directory structure, Then .wtf/config.json exists"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf/config.json").exists()


def test_init_creates_workflows_directory(tmp_path, monkeypatch):
    """Given wtf init completes, When I check the directory structure, Then .wtf/workflows/ directory exists"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf/workflows").exists()
    assert Path(".wtf/workflows").is_dir()


def test_init_creates_runs_directory(tmp_path, monkeypatch):
    """Given wtf init completes, When I check the directory structure, Then .wtf/runs/ directory exists"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf/runs").exists()
    assert Path(".wtf/runs").is_dir()


def test_init_creates_schema_workflow_schema(tmp_path, monkeypatch):
    """Given wtf init completes, When I check the directory structure, Then .wtf/schema/workflow.schema.json exists"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf/schema/workflow.schema.json").exists()


def test_init_creates_readme(tmp_path, monkeypatch):
    """Given wtf init completes, When I check the directory structure, Then .wtf/README.md exists"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf/README.md").exists()


def test_init_creates_index_json(tmp_path, monkeypatch):
    """Given wtf init completes, When I check the directory structure, Then .wtf/index.json exists"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert Path(".wtf/index.json").exists()


def test_init_config_contains_required_fields(tmp_path, monkeypatch):
    """Given wtf init completes, When I read config.json, Then it contains version and created_by fields"""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    config = json.loads(Path(".wtf/config.json").read_text())
    assert "version" in config
    assert "created_by" in config


def test_wtf_version_displays_version():
    """Given the package is installed, When I run wtf --version, Then it displays the version"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout

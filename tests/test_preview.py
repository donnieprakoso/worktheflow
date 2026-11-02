"""Tests for wtf graph <path> and wtf graph --preview (Use Case #8). One test per GWT scenario.

No real browser is started: the display check and the browser call are stubbed,
except in scenario 5, where only webbrowser.open is stubbed.
"""

import copy

import yaml
from typer.testing import CliRunner

import wtf.preview as preview
from wtf.cli import app

runner = CliRunner()

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
        {"trigger": "ready", "source": "red", "dest": "review"},
        {"trigger": "approve", "source": "review", "dest": "done"},
    ],
}


def init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0


def write_named(tmp_path, data, name="demo"):
    path = tmp_path / ".wtf" / "workflows" / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def write_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def stub_browser(monkeypatch, display=True, opened=True):
    """Stub the display check and the browser call. Returns the list of paths the browser was asked to open."""
    asked = []
    monkeypatch.setattr(preview, "can_open_browser", lambda env=None, platform=None: display)

    def fake_open(html_path):
        asked.append(html_path)
        return opened

    monkeypatch.setattr(preview, "open_in_browser", fake_open)
    return asked


# Scenario 1
def test_graph_accepts_path_outside_workflows_folder(tmp_path, monkeypatch):
    """Given a workflow file outside .wtf/workflows/, When I run wtf graph <path>, Then exit 0 and the first line is stateDiagram-v2."""
    init_project(tmp_path, monkeypatch)
    write_file(tmp_path / "other" / "flow.yaml", BASE)
    result = runner.invoke(app, ["graph", "other/flow.yaml"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "stateDiagram-v2"


# Scenario 2
def test_graph_missing_path_is_an_error(tmp_path, monkeypatch):
    """Given a path that does not exist, When I run wtf graph <path>, Then exit 1 and the output says the file was not found."""
    init_project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["graph", "nowhere/missing.yaml"])
    assert result.exit_code == 1, result.output
    assert "not found" in result.output.lower()


# Scenario 3
def test_preview_writes_html_with_escaped_diagram(tmp_path, monkeypatch):
    """Given --preview, When I run wtf graph <name> --preview, Then .wtf/preview/<name>.html contains the diagram in class=mermaid with --> escaped."""
    init_project(tmp_path, monkeypatch)
    write_named(tmp_path, BASE)
    stub_browser(monkeypatch)
    result = runner.invoke(app, ["graph", "demo", "--preview"])
    assert result.exit_code == 0, result.output
    html = (tmp_path / ".wtf" / "preview" / "demo.html").read_text()
    assert 'class="mermaid"' in html
    assert "red --&gt; review : ready" in html
    assert "-->" not in html.split('class="mermaid">', 1)[1].split("</pre>", 1)[0]


# Scenario 4
def test_preview_pins_mermaid_version(tmp_path, monkeypatch):
    """Given --preview, When the HTML is written, Then the Mermaid script names the pinned version 11.17.2."""
    init_project(tmp_path, monkeypatch)
    write_named(tmp_path, BASE)
    stub_browser(monkeypatch)
    runner.invoke(app, ["graph", "demo", "--preview"])
    html = (tmp_path / ".wtf" / "preview" / "demo.html").read_text()
    assert "mermaid@11.17.2/dist/mermaid.min.js" in html
    assert "mermaid@latest" not in html


# Scenario 5
def test_preview_asks_browser_to_open_file_url(tmp_path, monkeypatch):
    """Given --preview on a machine with a display, When the page is written, Then the browser is asked to open that HTML file as a file:// URL."""
    init_project(tmp_path, monkeypatch)
    write_named(tmp_path, BASE)
    monkeypatch.setattr(preview, "can_open_browser", lambda env=None, platform=None: True)
    urls = []
    monkeypatch.setattr(preview.webbrowser, "open", lambda url: urls.append(url) or True)
    result = runner.invoke(app, ["graph", "demo", "--preview"])
    assert result.exit_code == 0, result.output
    assert len(urls) == 1
    assert urls[0].startswith("file://")
    assert urls[0].endswith(".wtf/preview/demo.html")


# Scenario 6
def test_preview_on_linux_without_display_prints_path(tmp_path, monkeypatch):
    """Given --preview on Linux with no display, When I run the command, Then the browser is not opened, the path is printed, and exit is 0."""
    init_project(tmp_path, monkeypatch)
    write_named(tmp_path, BASE)
    asked = stub_browser(monkeypatch, display=False)
    result = runner.invoke(app, ["graph", "demo", "--preview"])
    assert result.exit_code == 0, result.output
    assert asked == []
    assert "demo.html" in result.output
    assert (tmp_path / ".wtf" / "preview" / "demo.html").exists()


# Scenario 6b
def test_preview_when_browser_cannot_open_prints_path(tmp_path, monkeypatch):
    """Given --preview and the browser cannot be opened, When I run the command, Then the path is printed and exit is 0."""
    init_project(tmp_path, monkeypatch)
    write_named(tmp_path, BASE)
    asked = stub_browser(monkeypatch, display=True, opened=False)
    result = runner.invoke(app, ["graph", "demo", "--preview"])
    assert result.exit_code == 0, result.output
    assert len(asked) == 1
    assert "demo.html" in result.output


# Scenario 7
def test_display_check_by_platform(monkeypatch):
    """Given Linux without a display, macOS, or Windows, When the display check runs, Then only Linux without DISPLAY/WAYLAND_DISPLAY reports no display."""
    assert preview.can_open_browser({}, "linux") is False
    assert preview.can_open_browser({"DISPLAY": ":0"}, "linux") is True
    assert preview.can_open_browser({"WAYLAND_DISPLAY": "wayland-0"}, "linux") is True
    assert preview.can_open_browser({}, "darwin") is True
    assert preview.can_open_browser({}, "win32") is True


# Scenario 8
def test_invalid_workflow_with_preview_opens_nothing(tmp_path, monkeypatch):
    """Given an invalid workflow with --preview, When I run the command, Then exit 1 and the browser is not opened."""
    init_project(tmp_path, monkeypatch)
    broken = copy.deepcopy(BASE)
    del broken["initial"]
    write_named(tmp_path, broken)
    asked = stub_browser(monkeypatch)
    result = runner.invoke(app, ["graph", "demo", "--preview"])
    assert result.exit_code == 1, result.output
    assert asked == []

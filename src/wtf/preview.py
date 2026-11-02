"""Preview a Mermaid diagram in the user's browser.

The page is opened with Python's webbrowser module, which works on macOS,
Linux, and Windows. Mermaid loads from a pinned CDN version, so rendering
needs internet access.
"""

import html
import os
import sys
import webbrowser
from pathlib import Path
from typing import Mapping, Optional

MERMAID_VERSION = "11.17.2"  # published 2026-08-25; pinned, never "latest"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"


def render_html(mermaid_text: str, title: str) -> str:
    """Return a standalone HTML page that renders the diagram."""
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 16px; }}
  h1 {{ font-size: 18px; }}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<pre class="mermaid">{html.escape(mermaid_text)}</pre>
<script src="{MERMAID_URL}"></script>
<script>mermaid.initialize({{ startOnLoad: true }});</script>
</body>
</html>
"""


def write_preview(wtf_dir: Path, name: str, mermaid_text: str) -> Path:
    """Write .wtf/preview/<name>.html and return its path."""
    out_dir = wtf_dir / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.html"
    path.write_text(render_html(mermaid_text, title=name))
    return path


def can_open_browser(env: Optional[Mapping[str, str]] = None, platform: Optional[str] = None) -> bool:
    """False only on Linux with no display. There, webbrowser may start a terminal
    browser such as lynx and take over the session."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform.startswith("linux"):
        return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    return True


def open_in_browser(html_path: Path) -> bool:
    """Ask the default browser to open the page. Returns False if it could not."""
    return bool(webbrowser.open(html_path.resolve().as_uri()))

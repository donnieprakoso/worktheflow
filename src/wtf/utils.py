"""Utility functions."""

import json
import os
import re
import uuid
from pathlib import Path
from datetime import datetime

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def get_wtf_dir(cwd: Path = None) -> Path:
    """Get .wtf directory in current project."""
    if cwd is None:
        cwd = Path.cwd()
    return cwd / ".wtf"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat()


def generate_run_id() -> str:
    return str(uuid.uuid4())


def state_file_path(wtf_dir: Path, run_id: str, state_name: str) -> Path:
    """Per-state handoff file: .wtf/runs/<run_id>/states/<state_name>.md.

    Required by convention (AGENTS.md / the skill), never enforced by the
    engine. The filename is sanitized for filesystem safety; the real state
    name is unaffected everywhere else (schema, display, guards)."""
    safe_name = _UNSAFE_FILENAME_CHARS.sub("_", state_name)
    return wtf_dir / "runs" / run_id / "states" / f"{safe_name}.md"

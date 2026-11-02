"""Render a workflow as a Mermaid stateDiagram-v2.

Output only. The YAML/JSON definition stays the source of truth, and nothing
is ever read back from a diagram.
"""

import re
from typing import Any, Dict, List

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED = {"end"}  # Mermaid keyword: must be declared with an alias


def _label(text: str) -> str:
    # A colon ends a Mermaid label, so it is replaced.
    return text.replace(":", "-")


def _ids(names: List[str]) -> Dict[str, str]:
    """Map each state name to a Mermaid id. Plain identifiers are used as-is;
    other names get an alias id `s<n>` that does not collide with any name."""
    taken = {n for n in names if _IDENTIFIER.match(n) and n not in _RESERVED}
    ids: Dict[str, str] = {}
    counter = 0
    for name in names:
        if name in taken:
            ids[name] = name
            continue
        while f"s{counter}" in taken or f"s{counter}" in names:
            counter += 1
        alias = f"s{counter}"
        taken.add(alias)
        ids[name] = alias
    return ids


def to_mermaid(wf: Dict[str, Any]) -> str:
    names = [s["name"] for s in wf["states"]]
    ids = _ids(names)

    lines = ["stateDiagram-v2"]
    for name in names:
        if ids[name] != name:
            lines.append(f'state "{name}" as {ids[name]}')

    lines.append(f"[*] --> {ids[wf['initial']]}")

    for t in wf["transitions"]:
        label = _label(t["trigger"])
        tags = []
        if t.get("require_approval"):
            tags.append("approval")
        guards = t.get("guards") or []
        if guards:
            tags.append(f"guards: {len(guards)}")
        label += "".join(f" ({tag})" for tag in tags)
        lines.append(f"{ids[t['source']]} --> {ids[t['dest']]} : {label}")

    for s in wf["states"]:
        if s.get("terminal") is True:
            lines.append(f"{ids[s['name']]} --> [*]")

    return "\n".join(lines) + "\n"

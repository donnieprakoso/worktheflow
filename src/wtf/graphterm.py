"""Render a wtf workflow as a Rich dot-and-line tree for the terminal.

Numbering is flat down a straight run of states (1, 2, 3...) and only opens a
decimal level at an actual fork or multi-way transition, continuing flat
across that whole branch region (e.g. state 4 forks into 4.1/4.2/4.3, and a
single-child continuation under 4.1 is 4.2, not 4.1.1) — chosen over strict
per-depth outline nesting because a long linear chain would otherwise produce
unreadably deep numbers for no benefit.
"""

from typing import AbstractSet, Any, Dict, FrozenSet

from rich.tree import Tree


def _node_label(wf: Dict[str, Any], name: str, current: AbstractSet[str], completed: AbstractSet[str]) -> str:
    s = next((x for x in wf["states"] if x["name"] == name), {"name": name})
    if name in current:
        dot = "[bold bright_yellow]●[/bold bright_yellow]"
    elif name in completed:
        dot = "[bright_green]✓[/bright_green]"
    elif s.get("terminal"):
        dot = "[bold bright_magenta]◆[/bold bright_magenta]"
    elif s.get("fork"):
        dot = "[bold bright_cyan]⑂[/bold bright_cyan]"
    elif s.get("branch_end"):
        dot = "[bright_cyan]◇[/bright_cyan]"
    else:
        dot = "[grey62]○[/grey62]"

    label = f"{dot} [bold]{name}[/bold]"
    if s.get("terminal"):
        label += " [grey62](terminal)[/grey62]"
    if s.get("fork"):
        label += " [grey62](fork)[/grey62]"
    return label


class _Counter:
    def __init__(self, start: int):
        self.n = start

    def next(self) -> int:
        v = self.n
        self.n += 1
        return v


def _build(tree_node, wf, name, path, current, completed, prefix, counter):
    outgoing = [t for t in wf["transitions"] if t["source"] == name]
    for t in outgoing:
        idx = f"{prefix}{counter.next()}"
        dest = t["dest"]
        trig = t["trigger"]
        badges = []
        if t.get("require_approval"):
            badges.append("[bold bright_yellow]🔒[/bold bright_yellow]")
        if t.get("guards"):
            badges.append(f"[grey62]({len(t['guards'])}g)[/grey62]")
        if t.get("join"):
            badges.append("[bold bright_cyan](join)[/bold bright_cyan]")
        edge = f"[bold grey62][{idx}][/bold grey62] [grey62]── {trig} ──▶[/grey62] " + " ".join(badges)

        if dest in path:
            # back-edge (e.g. a reject self-loop) — don't recurse, just note it
            tree_node.add(f"{edge} [grey62]↺ back to[/grey62] [bold]{dest}[/bold]")
            continue

        child = tree_node.add(f"{edge} {_node_label(wf, dest, current, completed)}")
        dest_outgoing = [t2 for t2 in wf["transitions"] if t2["source"] == dest]
        if len(dest_outgoing) > 1:
            # dest is itself a branch point: open a nested numbering region
            _build(child, wf, dest, path | {dest}, current, completed, f"{idx}.", _Counter(1))
        else:
            # straight continuation: stay flat in the same numbering region
            _build(child, wf, dest, path | {dest}, current, completed, prefix, counter)


def build_tree(
    wf: Dict[str, Any],
    current: AbstractSet[str] = frozenset(),
    completed: AbstractSet[str] = frozenset(),
) -> Tree:
    """A Rich Tree for `wf`. `current`/`completed` are state-name sets; both
    empty renders the bare structure (no run in progress). `current` may hold
    more than one name at once, for a run with several active branches."""
    initial = wf["initial"]
    root = Tree(
        f"[bold grey62][1][/bold grey62] {_node_label(wf, initial, current, completed)}"
        f"  [grey62]({wf['name']})[/grey62]"
    )
    initial_outgoing = [t for t in wf["transitions"] if t["source"] == initial]
    if len(initial_outgoing) > 1:
        _build(root, wf, initial, {initial}, current, completed, "1.", _Counter(1))
    else:
        _build(root, wf, initial, {initial}, current, completed, "", _Counter(2))
    return root

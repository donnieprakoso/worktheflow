"""Workflow loading and validation.

The JSON Schema file (schemas/workflow.schema.json) is the source of truth for
structure. The checks in this module cover what JSON Schema cannot express:
cross-references between states and transitions, trigger uniqueness, and
whether a terminal state is reachable from the initial state.
"""

import json
from collections import deque
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from jsonschema import Draft202012Validator

SCHEMA_RESOURCE = "schemas/workflow.schema.json"


class WorkflowFileError(Exception):
    """The workflow file could not be read or parsed."""


def read_schema_text() -> str:
    """Return the packaged workflow JSON Schema as text."""
    return files("wtf").joinpath(SCHEMA_RESOURCE).read_text()


def _load_schema() -> Dict[str, Any]:
    return json.loads(read_schema_text())


def _location(error) -> str:
    parts = [str(p) for p in error.absolute_path]
    return "/".join(parts) if parts else "(root)"


class SchemaValidator:
    def __init__(self) -> None:
        self._schema_validator = Draft202012Validator(_load_schema())

    def load_workflow(self, path: Path) -> Dict[str, Any]:
        try:
            content = path.read_text()
        except OSError as e:
            raise WorkflowFileError(f"Could not read {path}: {e}") from e
        if not content.strip():
            raise WorkflowFileError(f"Workflow file is empty: {path}")
        try:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            raise WorkflowFileError(f"Could not parse {path.name} as YAML/JSON: {e}") from e
        if data is None:
            raise WorkflowFileError(f"Workflow file is empty: {path}")
        return data

    def check(self, workflow: Any) -> Tuple[List[str], List[str]]:
        """Return (errors, warnings). Errors block the workflow; warnings do not."""
        if not isinstance(workflow, dict):
            return ["(root): workflow must be a mapping with name, initial, states, transitions"], []

        errors = [
            f"{_location(e)}: {e.message}"
            for e in sorted(self._schema_validator.iter_errors(workflow), key=lambda e: list(e.absolute_path))
        ]
        warnings: List[str] = []
        errors.extend(self._graph_checks(workflow, warnings))
        return errors, warnings

    def validate(self, workflow: Any) -> List[str]:
        """Errors only. Used by `wtf start`."""
        errors, _ = self.check(workflow)
        return errors

    def _graph_checks(self, wf: Dict[str, Any], warnings: List[str]) -> List[str]:
        errors: List[str] = []
        states = wf.get("states")
        transitions = wf.get("transitions")
        if not isinstance(states, list) or not isinstance(transitions, list):
            return errors  # schema already reported the shape problem

        state_dicts = [s for s in states if isinstance(s, dict)]
        names = [s["name"] for s in state_dicts if isinstance(s.get("name"), str)]
        name_set = set(names)

        seen_names = set()
        for n in names:
            if n in seen_names:
                errors.append(f"Duplicate state name '{n}'")
            seen_names.add(n)
        terminal = {s["name"] for s in state_dicts if s.get("terminal") is True and "name" in s}
        fork_states = {s["name"] for s in state_dicts if s.get("fork") is True and "name" in s}
        branch_end = {s["name"] for s in state_dicts if s.get("branch_end") is True and "name" in s}
        trans = [t for t in transitions if isinstance(t, dict)]
        initial = wf.get("initial")

        for n in names:
            flags = sum([n in terminal, n in fork_states, n in branch_end])
            if flags > 1:
                errors.append(f"State '{n}' combines terminal/fork/branch_end — pick one")

        if isinstance(initial, str) and initial not in name_set:
            errors.append(f"Initial state '{initial}' is not in states")

        for t in trans:
            trigger = t.get("trigger", "?")
            if t.get("source") not in name_set:
                errors.append(f"Transition '{trigger}' has source '{t.get('source')}' which is not in states")
            if t.get("dest") not in name_set:
                errors.append(f"Transition '{trigger}' has dest '{t.get('dest')}' which is not in states")

        seen = set()
        for t in trans:
            key = (t.get("source"), t.get("trigger"))
            if key in seen:
                errors.append(f"Duplicate trigger '{t.get('trigger')}' from state '{t.get('source')}'")
            seen.add(key)

        outgoing = {n: 0 for n in names}
        for t in trans:
            if t.get("source") in outgoing:
                outgoing[t["source"]] += 1

        # branch_end states are exempt from the dead-end rule the same way
        # terminal states are: they end a branch, nothing more happens there.
        end_like = terminal | branch_end
        for n in names:
            if n in end_like and outgoing[n] > 0:
                kind = "Terminal" if n in terminal else "branch_end"
                errors.append(f"{kind} state '{n}' must not have outgoing transitions")
            if n not in end_like and outgoing[n] == 0:
                errors.append(f"State '{n}' is not terminal but has no outgoing transitions (dead end)")

        # Each fork state needs exactly one join: true transition (the single
        # exit taken once every branch reaches a branch_end) and at least one
        # non-join transition (a branch start). A join transition may not
        # declare guards: it auto-fires once all branches finish, with no
        # retry path if a guard could fail at that point.
        for t in trans:
            if t.get("join") is True:
                src = t.get("source")
                if src not in fork_states:
                    errors.append(f"Transition '{t.get('trigger')}' is join: true but source '{src}' is not a fork: true state")
                if t.get("guards"):
                    errors.append(f"Join transition '{t.get('trigger')}' must not declare guards")

        for n in fork_states:
            out = [t for t in trans if t.get("source") == n]
            joins = [t for t in out if t.get("join") is True]
            branch_starts = [t for t in out if t.get("join") is not True]
            if len(joins) == 0:
                errors.append(f"Fork state '{n}' has no join: true transition")
            elif len(joins) > 1:
                errors.append(f"Fork state '{n}' has more than one join: true transition")
            if not branch_starts:
                errors.append(f"Fork state '{n}' has no branch-start transitions (only the join)")
            elif n in name_set:
                for bs in branch_starts:
                    dest = bs.get("dest")
                    if dest in name_set:
                        reachable_from_branch = self._reachable(dest, trans, name_set)
                        if not (branch_end & reachable_from_branch) and dest not in branch_end:
                            errors.append(
                                f"Fork '{n}': branch starting at '{dest}' (trigger '{bs.get('trigger')}') "
                                f"can never reach a branch_end state"
                            )

        if not terminal:
            errors.append("No state has terminal: true")
            return errors

        if initial in name_set:
            reachable = self._reachable(initial, trans, name_set)
            if not (terminal & reachable):
                errors.append(f"No terminal state is reachable from initial state '{initial}'")
            for n in names:
                if n not in reachable:
                    warnings.append(f"State '{n}' is not reachable from initial state '{initial}'")

        return errors

    @staticmethod
    def _reachable(start: str, trans: List[Dict[str, Any]], name_set: set) -> set:
        graph: Dict[str, List[str]] = {}
        for t in trans:
            if t.get("source") in name_set and t.get("dest") in name_set:
                graph.setdefault(t["source"], []).append(t["dest"])
        seen = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in graph.get(node, []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

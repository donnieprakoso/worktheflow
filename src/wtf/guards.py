"""Guard evaluation for wtf.

The guard set is fixed: file_exists, file_contains, command_passes,
command_fails, field_eq, field_ne. Each guard returns (passed, message) and
never raises.
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

# Command guards are stopped after this many seconds. A timeout is a failure.
COMMAND_TIMEOUT_SECONDS = 300

_MISSING = object()  # sentinel: a missing field never equals an expected value


class _MissingParam(Exception):
    pass


def _param(params: Dict[str, Any], name: str) -> Any:
    if name not in params:
        raise _MissingParam(f"missing param '{name}'")
    return params[name]


def _run_command(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


class GuardEvaluator:
    def evaluate(self, guard: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[bool, str]:
        context = context or {}
        guard_type = guard.get("type")
        params = guard.get("params") or {}

        try:
            if guard_type == "file_exists":
                path = Path(_param(params, "path"))
                return path.exists(), f"file_exists({path})"

            if guard_type == "file_contains":
                path = Path(_param(params, "path"))
                pattern = _param(params, "pattern")
                if not path.exists():
                    return False, f"file {path} does not exist"
                if pattern in path.read_text():
                    return True, "file contains pattern"
                return False, "file does not contain pattern"

            if guard_type == "command_passes":
                command = _param(params, "command")
                result = _run_command(command)
                if result.returncode == 0:
                    return True, "command passed"
                return False, f"command failed (exit {result.returncode}): {result.stderr}"

            if guard_type == "command_fails":
                command = _param(params, "command")
                result = _run_command(command)
                if result.returncode != 0:
                    return True, "command failed as expected"
                return False, "command unexpectedly passed"

            if guard_type == "field_eq":
                field = _param(params, "field")
                expected = _param(params, "value")
                return context.get(field, _MISSING) == expected, f"field {field} == {expected}"

            if guard_type == "field_ne":
                field = _param(params, "field")
                expected = _param(params, "value")
                return context.get(field, _MISSING) != expected, f"field {field} != {expected}"

            return False, f"unknown guard type: {guard_type}"

        except _MissingParam as e:
            return False, f"guard {guard_type} is invalid: {e}"
        except subprocess.TimeoutExpired:
            return False, f"command timed out after {COMMAND_TIMEOUT_SECONDS}s"
        except Exception as e:
            return False, f"guard error: {e}"

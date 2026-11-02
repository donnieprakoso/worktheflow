"""State storage for wtf runs."""

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .utils import get_wtf_dir, ensure_dir, now_iso, generate_run_id

CHECKSUM_KEY = "_checksum"


def _compute_checksum(state: Dict[str, Any]) -> str:
    """SHA-256 over the state's canonical JSON, excluding the checksum field itself.

    No secret key: this detects accidental or careless edits to state.json made
    outside wtf, not a determined adversary who can read this source and
    recompute a valid checksum. That matches the single-user threat model.
    """
    payload = {k: v for k, v in state.items() if k != CHECKSUM_KEY}
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class RunStore:
    def __init__(self, cwd: Path = None):
        self.wtf_dir = get_wtf_dir(cwd)
        self.runs_dir = self.wtf_dir / "runs"
        self.index_path = self.wtf_dir / "index.json"
        ensure_dir(self.runs_dir)

    def _ensure_index(self):
        if not self.index_path.exists():
            self.index_path.write_text(json.dumps({"runs": []}, indent=2))

    def _write_state(self, run_dir: Path, state: Dict[str, Any]) -> None:
        """Compute and attach the checksum, then write state.json. Shared by
        create_run and save_run so both always leave a correct checksum."""
        state[CHECKSUM_KEY] = _compute_checksum(state)
        (run_dir / "state.json").write_text(json.dumps(state, indent=2))

    def create_run(self, workflow_name: str, inputs: Dict[str, Any] = None) -> str:
        run_id = generate_run_id()
        run_dir = self.runs_dir / run_id
        ensure_dir(run_dir)

        state = {
            "run_id": run_id,
            "workflow": workflow_name,
            "current_state": None,
            "status": "running",
            "inputs": inputs or {},
            "data": {},
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

        self._write_state(run_dir, state)
        (run_dir / "events.jsonl").write_text("")

        self._ensure_index()
        index = json.loads(self.index_path.read_text())
        index["runs"].append({
            "run_id": run_id,
            "workflow": workflow_name,
            "status": "running",
            "current_state": None,
            "created_at": state["created_at"],
            "updated_at": state["updated_at"],
        })
        self.index_path.write_text(json.dumps(index, indent=2))

        return run_id

    def load_run(self, run_id: str) -> Dict[str, Any]:
        run_dir = self.runs_dir / run_id
        state_path = run_dir / "state.json"
        if not state_path.exists():
            raise FileNotFoundError(f"Run {run_id} not found")
        return json.loads(state_path.read_text())

    def verify_integrity(self, state: Dict[str, Any]) -> bool:
        """True if the checksum matches, or if the state has no checksum at all
        (a run created before this feature existed — not treated as suspicious)."""
        checksum = state.get(CHECKSUM_KEY)
        if checksum is None:
            return True
        return checksum == _compute_checksum(state)

    def save_run(self, run_id: str, state: Dict[str, Any]):
        run_dir = self.runs_dir / run_id
        ensure_dir(run_dir)
        state["updated_at"] = now_iso()
        self._write_state(run_dir, state)

        # Update index
        self._ensure_index()
        index = json.loads(self.index_path.read_text())
        for r in index["runs"]:
            if r["run_id"] == run_id:
                r["status"] = state["status"]
                r["current_state"] = state.get("current_state")
                r["updated_at"] = state["updated_at"]
                break
        self.index_path.write_text(json.dumps(index, indent=2))

    def append_event(self, run_id: str, event: Dict[str, Any]):
        run_dir = self.runs_dir / run_id
        ensure_dir(run_dir)
        events_path = run_dir / "events.jsonl"
        event["timestamp"] = now_iso()
        with open(events_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def load_events(self, run_id: str) -> List[Dict[str, Any]]:
        """All events recorded for a run, in the order they were written."""
        events_path = self.runs_dir / run_id / "events.jsonl"
        if not events_path.exists():
            return []
        events = []
        for line in events_path.read_text().splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def list_runs(self) -> List[Dict[str, Any]]:
        self._ensure_index()
        index = json.loads(self.index_path.read_text())
        return index.get("runs", [])

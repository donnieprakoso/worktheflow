"""Core engine - policy enforcer, not runner."""

from pathlib import Path
from typing import Dict, Any, Optional, List
from .store import RunStore
from .guards import GuardEvaluator
from .schema import SchemaValidator


class WtfEngine:
    def __init__(self, cwd: Path = None):
        self.cwd = cwd or Path.cwd()
        self.store = RunStore(self.cwd)
        self.guards = GuardEvaluator()
        self.validator = SchemaValidator()
    
    def get_workflows_dir(self) -> Path:
        return self.cwd / ".wtf" / "workflows"
    
    def load_workflow(self, name: str) -> Dict[str, Any]:
        wf_dir = self.get_workflows_dir()
        candidates = [wf_dir / f"{name}{ext}" for ext in ('.yaml', '.yml', '.json')]
        for path in candidates:
            if path.exists():
                return self.validator.load_workflow(path)
        searched = ", ".join(str(p.relative_to(self.cwd)) for p in candidates)
        raise FileNotFoundError(f"Workflow '{name}' not found. Searched: {searched}")
    
    def get_allowed_transitions(self, workflow: Dict[str, Any], current_state: str) -> List[Dict[str, Any]]:
        allowed = []
        for t in workflow["transitions"]:
            if t["source"] == current_state:
                allowed.append(t)
        return allowed
    
    def find_transition(self, workflow: Dict[str, Any], source: str, trigger: str) -> Optional[Dict[str, Any]]:
        for t in workflow["transitions"]:
            if t["source"] == source and t["trigger"] == trigger:
                return t
        return None
    
    def evaluate_transition_guards(self, transition: Dict[str, Any], context: Dict[str, Any]) -> tuple[bool, List[str]]:
        guards = transition.get("guards", [])
        results = []
        for g in guards:
            passed, msg = self.guards.evaluate(g, context)
            results.append(msg)
            if not passed:
                return False, results
        return True, results

import json
from pathlib import Path

from ..snapshots import snapshot_file


WORKFLOWS_ROOT = Path("user/default/workflows")


def resolve_workflow_path(root: Path, path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("workflow path must be a non-empty string")
    requested = Path(path)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("workflow path must stay inside user/default/workflows")
    prefix = WORKFLOWS_ROOT.parts
    if requested.parts[: len(prefix)] == prefix:
        requested = Path(*requested.parts[len(prefix):])
    base = (root / WORKFLOWS_ROOT).resolve()
    target = (base / requested).resolve()
    if base != target and base not in target.parents:
        raise ValueError("workflow path must stay inside user/default/workflows")
    return target


def save_workflow_with_snapshot(target: Path, workflow: dict, backup_dir: Path) -> dict:
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be an object")
    if target.exists():
        snapshot = snapshot_file(target, backup_dir, reason="workflow-save")
    else:
        snapshot = None
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"path": str(target), "snapshot": str(snapshot) if snapshot else None}

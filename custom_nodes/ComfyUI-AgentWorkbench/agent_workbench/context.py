from pathlib import Path


def _graph_summary(graph: dict | None) -> dict:
    if not graph:
        return {"node_count": 0, "link_count": 0, "selected_node_ids": []}
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    selected = [node.get("id") for node in nodes if node.get("selected")]
    return {"node_count": len(nodes), "link_count": len(links), "selected_node_ids": selected}


def _custom_nodes(root: Path) -> list[dict]:
    custom_nodes_dir = root / "custom_nodes"
    if not custom_nodes_dir.exists():
        return []
    rows = []
    for child in sorted(custom_nodes_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.name.startswith("__") or child.name.startswith("."):
            continue
        if not child.is_dir() and child.suffix != ".py":
            continue
        rows.append(
            {
                "name": child.name.removesuffix(".disabled"),
                "path": str(child.relative_to(root)),
                "state": "disabled" if child.name.endswith(".disabled") else "enabled",
            }
        )
    return rows


def _workflow_rows(root: Path, max_workflows: int) -> tuple[list[dict], bool]:
    workflows_dir = root / "user" / "default" / "workflows"
    if not workflows_dir.exists():
        return [], False
    paths = sorted(workflows_dir.rglob("*.json"), key=lambda path: str(path).lower())
    rows = [
        {"path": str(path.relative_to(root)), "bytes": path.stat().st_size}
        for path in paths[:max_workflows]
    ]
    return rows, len(paths) > max_workflows


def collect_context(root: Path, graph: dict | None = None, max_workflows: int = 50) -> dict:
    workflows, truncated = _workflow_rows(root, max_workflows=max_workflows)
    return {
        "root": str(root),
        "graph": _graph_summary(graph),
        "custom_nodes": _custom_nodes(root),
        "workflows": workflows,
        "workflows_truncated": truncated,
    }

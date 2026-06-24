from pathlib import Path


def _empty_graph_summary() -> dict:
    return {"node_count": 0, "link_count": 0, "selected_node_ids": []}


def _graph_summary(graph: dict | None) -> dict:
    if not isinstance(graph, dict):
        return _empty_graph_summary()
    nodes = graph.get("nodes")
    links = graph.get("links")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(links, list):
        links = []
    node_rows = [node for node in nodes if isinstance(node, dict)]
    selected = [node.get("id") for node in node_rows if node.get("selected")]
    return {
        "node_count": len(node_rows),
        "link_count": len(links),
        "selected_node_ids": selected,
    }


def _custom_nodes(root: Path) -> list[dict]:
    custom_nodes_dir = root / "custom_nodes"
    try:
        if not custom_nodes_dir.is_dir():
            return []
        children = list(custom_nodes_dir.iterdir())
    except OSError:
        return []

    rows = []
    for child in sorted(children, key=lambda path: path.name.lower()):
        if child.name.startswith("__") or child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
            is_file = child.is_file()
        except OSError:
            continue
        if not is_dir and (child.suffix != ".py" or not is_file):
            continue
        try:
            path = str(child.relative_to(root))
        except ValueError:
            continue
        rows.append(
            {
                "name": child.name.removesuffix(".disabled"),
                "path": path,
                "state": "disabled" if child.name.endswith(".disabled") else "enabled",
            }
        )
    return rows


def _workflow_rows(
    root: Path,
    max_workflows: int,
    max_workflow_scan_entries: int,
) -> tuple[list[dict], bool]:
    workflows_dir = root / "user" / "default" / "workflows"
    try:
        if not workflows_dir.is_dir():
            return [], False
    except OSError:
        return [], False

    rows = []
    visited_entries = 0
    scan_limit_reached = False
    workflow_limit_reached = False
    pending_dirs = [workflows_dir]
    pending_index = 0
    while pending_index < len(pending_dirs):
        directory = pending_dirs[pending_index]
        pending_index += 1
        try:
            iterator = directory.iterdir()
        except OSError:
            continue

        children = []
        while True:
            if visited_entries >= max_workflow_scan_entries:
                scan_limit_reached = True
                break
            try:
                child = next(iterator)
            except StopIteration:
                break
            except OSError:
                break
            visited_entries += 1
            children.append(child)

        for child in sorted(children, key=lambda path: path.name.lower()):
            try:
                is_symlink = child.is_symlink()
                is_dir = child.is_dir() if not is_symlink else False
                is_file = child.is_file()
            except OSError:
                continue
            if is_dir:
                pending_dirs.append(child)
                continue
            if not is_file or child.suffix != ".json":
                continue
            try:
                rows.append(
                    {"path": str(child.relative_to(root)), "bytes": child.stat().st_size}
                )
            except (OSError, ValueError):
                continue
            if len(rows) > max_workflows:
                workflow_limit_reached = True
                break

        if scan_limit_reached or workflow_limit_reached:
            break

    rows = sorted(rows, key=lambda row: row["path"].lower())
    return rows[:max_workflows], scan_limit_reached or workflow_limit_reached


def collect_context(
    root: Path,
    graph: dict | None = None,
    max_workflows: int = 50,
    max_workflow_scan_entries: int | None = None,
) -> dict:
    max_workflows = max(0, max_workflows)
    if max_workflow_scan_entries is None:
        max_workflow_scan_entries = max(500, max_workflows * 10)
    max_workflow_scan_entries = max(0, max_workflow_scan_entries)
    workflows, truncated = _workflow_rows(
        root,
        max_workflows=max_workflows,
        max_workflow_scan_entries=max_workflow_scan_entries,
    )
    return {
        "root": str(root),
        "graph": _graph_summary(graph),
        "custom_nodes": _custom_nodes(root),
        "workflows": workflows,
        "workflows_truncated": truncated,
    }

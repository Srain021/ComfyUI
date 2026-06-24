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


def _bounded_entries(directory: Path, remaining_entries: int) -> tuple[list[Path], int, bool]:
    if remaining_entries <= 0:
        return [], 0, True
    try:
        iterator = directory.iterdir()
    except OSError:
        return [], 0, False

    rows = []
    while len(rows) < remaining_entries:
        try:
            rows.append(next(iterator))
        except StopIteration:
            return rows, len(rows), False
        except OSError:
            return rows, len(rows), False
    return rows, len(rows), True


def _custom_node_row(root: Path, child: Path, state: str, name: str | None = None) -> dict | None:
    try:
        is_dir = child.is_dir()
        is_file = child.is_file()
    except OSError:
        return None
    if not is_dir and (child.suffix != ".py" or not is_file):
        return None
    try:
        path = str(child.relative_to(root))
    except ValueError:
        return None
    return {
        "name": (name or child.name).removesuffix(".disabled"),
        "path": path,
        "state": state,
    }


def _custom_nodes(
    root: Path,
    max_custom_nodes: int,
    max_custom_node_scan_entries: int,
) -> tuple[list[dict], bool]:
    custom_nodes_dir = root / "custom_nodes"
    try:
        if not custom_nodes_dir.is_dir():
            return [], False
    except OSError:
        return [], False

    rows = []
    visited_entries = 0
    scan_limit_reached = False
    response_limit_reached = False

    children, visited, truncated = _bounded_entries(
        custom_nodes_dir,
        max_custom_node_scan_entries - visited_entries,
    )
    visited_entries += visited
    scan_limit_reached = scan_limit_reached or truncated

    for child in sorted(children, key=lambda path: path.name.lower()):
        if child.name == ".disabled":
            try:
                is_disabled_dir = child.is_dir()
            except OSError:
                is_disabled_dir = False
            if not is_disabled_dir:
                continue
            disabled_children, visited, truncated = _bounded_entries(
                child,
                max_custom_node_scan_entries - visited_entries,
            )
            visited_entries += visited
            scan_limit_reached = scan_limit_reached or truncated
            for disabled_child in sorted(disabled_children, key=lambda path: path.name.lower()):
                if disabled_child.name.startswith("__") or disabled_child.name.startswith("."):
                    continue
                row = _custom_node_row(
                    root,
                    disabled_child,
                    state="disabled",
                    name=disabled_child.name,
                )
                if row is None:
                    continue
                rows.append(row)
                if len(rows) > max_custom_nodes:
                    response_limit_reached = True
                    break
            if response_limit_reached:
                break
            continue

        if child.name.startswith("__") or child.name.startswith("."):
            continue
        row = _custom_node_row(
            root,
            child,
            state="disabled" if child.name.endswith(".disabled") else "enabled",
        )
        if row is None:
            continue
        rows.append(row)
        if len(rows) > max_custom_nodes:
            response_limit_reached = True
            break

    rows = sorted(rows, key=lambda row: (row["name"].lower(), row["path"].lower()))
    return rows[:max_custom_nodes], scan_limit_reached or response_limit_reached


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
    max_custom_nodes: int = 100,
    max_custom_node_scan_entries: int | None = None,
) -> dict:
    max_workflows = max(0, max_workflows)
    if max_workflow_scan_entries is None:
        max_workflow_scan_entries = max(500, max_workflows * 10)
    max_workflow_scan_entries = max(0, max_workflow_scan_entries)
    max_custom_nodes = max(0, max_custom_nodes)
    if max_custom_node_scan_entries is None:
        max_custom_node_scan_entries = 500
    max_custom_node_scan_entries = max(0, max_custom_node_scan_entries)
    custom_nodes, custom_nodes_truncated = _custom_nodes(
        root,
        max_custom_nodes=max_custom_nodes,
        max_custom_node_scan_entries=max_custom_node_scan_entries,
    )
    workflows, workflows_truncated = _workflow_rows(
        root,
        max_workflows=max_workflows,
        max_workflow_scan_entries=max_workflow_scan_entries,
    )
    return {
        "root": str(root),
        "graph": _graph_summary(graph),
        "custom_nodes": custom_nodes,
        "custom_nodes_truncated": custom_nodes_truncated,
        "workflows": workflows,
        "workflows_truncated": workflows_truncated,
    }

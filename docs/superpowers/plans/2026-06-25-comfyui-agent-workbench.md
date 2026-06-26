# ComfyUI Agent Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an in-ComfyUI Agent Workbench that accepts natural language and operates the current graph, workflows, custom nodes, compose service, and GB10 runtime through validated action plans.

**Architecture:** Implement a ComfyUI custom node extension at `custom_nodes/ComfyUI-AgentWorkbench`. The frontend is a dockable operator panel; the backend exposes `/agent/*` routes, validates structured plans, records audit logs, and runs only allowlisted operations. High-risk actions use dry-run hashes, explicit approval, verification, and rollback.

**Tech Stack:** Python 3.12, aiohttp, stdlib dataclasses/json/hashlib/subprocess/pathlib, PyYAML for compose validation, ComfyUI custom-node `WEB_DIRECTORY` frontend extension, ComfyUI-Manager HTTP routes for managed custom-node operations, Docker CLI through non-shell subprocess calls.

---

## Scope Check

The approved spec is broad, but its subsystems are dependent: the UI needs the same action schema used by graph edits, custom-node ops, and compose ops. This plan keeps one end-to-end plan and splits execution into vertical, testable slices. Each task leaves the workbench in a runnable state or adds one isolated capability behind validation.

## File Structure

- Create `custom_nodes/ComfyUI-AgentWorkbench/__init__.py`: ComfyUI custom node entry point, route registration, web asset registration.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/__init__.py`: internal importable Python package.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/health.py`: static health and capability payload.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`: aiohttp route handlers for `/agent/*`.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`: action registry, validation, dry-run hashing, apply dispatcher.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/permissions.py`: capability levels and approval policy.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/audit_log.py`: append-only JSONL audit log.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/snapshots.py`: file snapshot and restore helpers.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/context.py`: bounded project/runtime context collector.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/planner.py`: rule-based planner plus OpenAI-compatible provider adapter.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/commands.py`: allowlisted subprocess runner.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/runtime.py`: `/free`, memory, Ollama, and Docker runtime actions.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/compose.py`: compose validation, reserve-vram patching, backup, apply, and rollback.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/manager.py`: ComfyUI-Manager adapter for custom-node install/update/disable/enable.
- Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/workflows.py`: workflow snapshot, save, and restore actions.
- Create `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`: dockable panel, context display, plan preview, confirmation, graph executor.
- Create `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`: operator panel styling.
- Create tests under `tests-unit/agent_workbench/`.

## Common Test Commands

Run focused Python tests inside the mounted ComfyUI container:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench -q
```

Run a syntax sweep:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m py_compile custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/*.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/*.py
```

Restart ComfyUI after adding the custom node extension:

```bash
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
```

Verify routes and frontend extension loading:

```bash
curl -sf http://127.0.0.1:8188/agent/health
curl -sf http://127.0.0.1:8188/extensions | rg 'ComfyUI-AgentWorkbench'
```

---

### Task 1: Custom Node Shell and Health Route

**Files:**
- Create: `tests-unit/agent_workbench/test_health.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/__init__.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/__init__.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/health.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`

- [ ] **Step 1: Write the failing health test**

Create `tests-unit/agent_workbench/test_health.py`:

```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.health import build_health_payload


def test_health_payload_names_core_capabilities():
    payload = build_health_payload()

    assert payload["ok"] is True
    assert payload["name"] == "ComfyUI Agent Workbench"
    assert payload["version"] == "0.1.0"
    assert "graph.edit" in payload["capabilities"]
    assert "custom_node.manage" in payload["capabilities"]
    assert "service.compose" in payload["capabilities"]
    assert payload["sudo_policy"] == "print_only"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_health.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_workbench'`.

- [ ] **Step 3: Add the extension package and health route**

Create `custom_nodes/ComfyUI-AgentWorkbench/__init__.py`:

```python
from .agent_workbench.routes import register_routes


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "js"

register_routes()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/__init__.py`:

```python
VERSION = "0.1.0"
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/health.py`:

```python
from . import VERSION


CORE_CAPABILITIES = [
    "context.read",
    "graph.inspect",
    "graph.edit",
    "workflow.write",
    "runtime.free_memory",
    "custom_node.manage",
    "service.compose",
    "service.restart",
    "sudo.print_only",
]


def build_health_payload() -> dict:
    return {
        "ok": True,
        "name": "ComfyUI Agent Workbench",
        "version": VERSION,
        "capabilities": CORE_CAPABILITIES,
        "sudo_policy": "print_only",
    }
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`:

```python
from aiohttp import web

from .health import build_health_payload


_REGISTERED = False


def register_routes(prompt_server=None) -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    if prompt_server is None:
        from server import PromptServer

        prompt_server = PromptServer.instance

    routes = prompt_server.routes

    @routes.get("/agent/health")
    async def agent_health(request):
        return web.json_response(build_health_payload())

    _REGISTERED = True
```

Create `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`:

```javascript
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

import "./agent-workbench.css";

function createWorkbenchPanel() {
  const panel = document.createElement("section");
  panel.id = "agent-workbench-panel";
  panel.innerHTML = `
    <header>
      <strong>Agent</strong>
      <button id="agent-workbench-refresh" title="Refresh context">Refresh</button>
    </header>
    <textarea id="agent-workbench-input" placeholder="Tell the Agent what to inspect or change"></textarea>
    <button id="agent-workbench-plan">Plan</button>
    <pre id="agent-workbench-output">Agent Workbench ready.</pre>
  `;
  document.body.appendChild(panel);

  const output = panel.querySelector("#agent-workbench-output");
  panel.querySelector("#agent-workbench-refresh").addEventListener("click", async () => {
    const response = await api.fetchApi("/agent/health");
    output.textContent = JSON.stringify(await response.json(), null, 2);
  });
}

app.registerExtension({
  name: "ComfyUI.AgentWorkbench",
  setup() {
    createWorkbenchPanel();
  },
});
```

Create `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`:

```css
#agent-workbench-panel {
  position: fixed;
  top: 56px;
  right: 12px;
  z-index: 9999;
  width: min(420px, calc(100vw - 24px));
  max-height: calc(100vh - 80px);
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(180, 190, 205, 0.35);
  border-radius: 8px;
  background: rgba(24, 27, 32, 0.96);
  color: #f4f7fb;
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.32);
  font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

#agent-workbench-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

#agent-workbench-input {
  min-height: 72px;
  resize: vertical;
  border-radius: 6px;
  border: 1px solid rgba(180, 190, 205, 0.35);
  background: #101318;
  color: #f4f7fb;
  padding: 8px;
}

#agent-workbench-output {
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 8px;
  border-radius: 6px;
  background: #0c0f14;
  color: #dbe6f4;
}
```

- [ ] **Step 4: Run the health test to verify it passes**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_health.py -q
```

Expected: PASS.

- [ ] **Step 5: Restart and verify the route and JS extension**

Run:

```bash
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
curl -sf http://127.0.0.1:8188/agent/health
curl -sf http://127.0.0.1:8188/extensions | rg 'ComfyUI-AgentWorkbench'
```

Expected: health JSON includes `"ok": true`; `/extensions` includes `/extensions/ComfyUI-AgentWorkbench/agent-workbench.js`.

- [ ] **Step 6: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench tests-unit/agent_workbench/test_health.py
git commit -m "feat: add agent workbench shell"
```

### Task 2: Permission Levels and Action Schema

**Files:**
- Create: `tests-unit/agent_workbench/test_actions.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/permissions.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`

- [ ] **Step 1: Write failing action validation tests**

Create `tests-unit/agent_workbench/test_actions.py`:

```python
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.actions import PlanValidationError, stable_plan_hash, validate_plan


def test_validate_plan_assigns_capabilities_and_hash_is_stable():
    raw = {
        "summary": "Change prompt text",
        "actions": [
            {
                "type": "graph.set_widget",
                "payload": {"node_id": 12, "widget": "text", "value": "cinematic lighting"},
            }
        ],
    }

    plan = validate_plan(raw)

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert stable_plan_hash(plan) == stable_plan_hash(plan)


def test_validate_plan_rejects_unknown_action_type():
    with pytest.raises(PlanValidationError, match="Unsupported action type"):
        validate_plan({"summary": "bad", "actions": [{"type": "shell.exec", "payload": {}}]})


def test_service_actions_require_explicit_approval():
    raw = {
        "summary": "Restart ComfyUI",
        "actions": [{"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}],
    }

    plan = validate_plan(raw)

    assert plan["risk_level"] == "service"
    assert plan["requires_confirmation"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_actions.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing `actions.py`.

- [ ] **Step 3: Implement permissions and action validation**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/permissions.py`:

```python
CAPABILITY_LEVELS = {
    "context.read": 0,
    "graph.inspect": 0,
    "graph.edit": 1,
    "runtime.queue": 2,
    "runtime.free_memory": 2,
    "workflow.write": 3,
    "custom_node.manage": 4,
    "service.compose": 5,
    "service.restart": 5,
    "sudo.print_only": 6,
}

RISK_ORDER = ["read", "canvas", "runtime", "file", "package", "service", "human_sudo"]
RISK_REQUIRES_CONFIRMATION = {"runtime", "file", "package", "service", "human_sudo"}


def requires_confirmation(risk_level: str) -> bool:
    return risk_level in RISK_REQUIRES_CONFIRMATION


def max_risk(left: str, right: str) -> str:
    if RISK_ORDER.index(left) >= RISK_ORDER.index(right):
        return left
    return right
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`:

```python
import hashlib
import json
from copy import deepcopy

from .permissions import max_risk, requires_confirmation


class PlanValidationError(ValueError):
    pass


ACTION_REGISTRY = {
    "context.collect": ("context.read", "read"),
    "graph.set_widget": ("graph.edit", "canvas"),
    "graph.add_node": ("graph.edit", "canvas"),
    "graph.connect": ("graph.edit", "canvas"),
    "workflow.save": ("workflow.write", "file"),
    "runtime.free_memory": ("runtime.free_memory", "runtime"),
    "runtime.stop_ollama_model": ("runtime.free_memory", "runtime"),
    "custom_node.install": ("custom_node.manage", "package"),
    "custom_node.disable": ("custom_node.manage", "package"),
    "custom_node.enable": ("custom_node.manage", "package"),
    "compose.set_reserve_vram": ("service.compose", "service"),
    "service.restart_container": ("service.restart", "service"),
    "sudo.print_command": ("sudo.print_only", "human_sudo"),
}


def _normalize_action(action: dict) -> dict:
    action_type = action.get("type")
    if action_type not in ACTION_REGISTRY:
        raise PlanValidationError(f"Unsupported action type: {action_type}")
    payload = action.get("payload", {})
    if not isinstance(payload, dict):
        raise PlanValidationError(f"Action payload must be an object: {action_type}")
    capability, risk = ACTION_REGISTRY[action_type]
    return {
        "type": action_type,
        "payload": deepcopy(payload),
        "capability": capability,
        "risk_level": risk,
    }


def validate_plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise PlanValidationError("Plan must be an object")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise PlanValidationError("Plan summary must be a non-empty string")
    raw_actions = raw.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise PlanValidationError("Plan actions must be a non-empty list")

    actions = [_normalize_action(action) for action in raw_actions]
    risk_level = "read"
    capabilities = []
    for action in actions:
        risk_level = max_risk(risk_level, action["risk_level"])
        if action["capability"] not in capabilities:
            capabilities.append(action["capability"])

    plan = {
        "summary": summary.strip(),
        "actions": actions,
        "risk_level": risk_level,
        "required_capabilities": capabilities,
        "requires_confirmation": requires_confirmation(risk_level),
    }
    plan["plan_hash"] = stable_plan_hash(plan)
    return plan


def stable_plan_hash(plan: dict) -> str:
    copy = deepcopy(plan)
    copy.pop("plan_hash", None)
    payload = json.dumps(copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_actions.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/permissions.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py tests-unit/agent_workbench/test_actions.py
git commit -m "feat: validate agent action plans"
```

### Task 3: Audit Log and Reversible File Snapshots

**Files:**
- Create: `tests-unit/agent_workbench/test_audit_snapshots.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/audit_log.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/snapshots.py`

- [ ] **Step 1: Write failing audit and snapshot tests**

Create `tests-unit/agent_workbench/test_audit_snapshots.py`:

```python
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.audit_log import append_audit_event, read_recent_events
from agent_workbench.snapshots import restore_snapshot, snapshot_file


def test_audit_log_appends_jsonl(tmp_path):
    log_path = tmp_path / "audit.jsonl"

    append_audit_event(log_path, {"event": "dry_run", "plan_hash": "abc"})

    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert rows[0]["event"] == "dry_run"
    assert rows[0]["plan_hash"] == "abc"
    assert "created_at" in rows[0]
    assert read_recent_events(log_path, limit=1)[0]["event"] == "dry_run"


def test_snapshot_file_and_restore(tmp_path):
    target = tmp_path / "workflow.json"
    target.write_text('{"old": true}', encoding="utf-8")
    backup_dir = tmp_path / "backups"

    snapshot = snapshot_file(target, backup_dir, reason="workflow-save")
    target.write_text('{"old": false}', encoding="utf-8")
    restore_snapshot(snapshot, target)

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert "workflow-save" in snapshot.name
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_audit_snapshots.py -q
```

Expected: FAIL with missing `audit_log.py`.

- [ ] **Step 3: Implement audit and snapshot helpers**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/audit_log.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path


def append_audit_event(log_path: Path, event: dict) -> dict:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(event)
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return row


def read_recent_events(log_path: Path, limit: int = 50) -> list[dict]:
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:]]
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/snapshots.py`:

```python
import shutil
from datetime import datetime, timezone
from pathlib import Path


def snapshot_file(target: Path, backup_dir: Path, reason: str) -> Path:
    if not target.exists():
        raise FileNotFoundError(str(target))
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_reason = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in reason)
    snapshot = backup_dir / f"{target.name}.{safe_reason}.{stamp}.bak"
    shutil.copy2(target, snapshot)
    return snapshot


def restore_snapshot(snapshot: Path, target: Path) -> None:
    if not snapshot.exists():
        raise FileNotFoundError(str(snapshot))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot, target)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_audit_snapshots.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/audit_log.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/snapshots.py tests-unit/agent_workbench/test_audit_snapshots.py
git commit -m "feat: add agent audit log and snapshots"
```

### Task 4: Bounded Context Collector

**Files:**
- Create: `tests-unit/agent_workbench/test_context.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/context.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`

- [ ] **Step 1: Write failing context tests**

Create `tests-unit/agent_workbench/test_context.py`:

```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.context import collect_context


def test_collect_context_bounds_workflows_and_custom_nodes(tmp_path):
    (tmp_path / "custom_nodes" / "NodeA").mkdir(parents=True)
    (tmp_path / "custom_nodes" / "NodeB.disabled").mkdir(parents=True)
    workflows = tmp_path / "user" / "default" / "workflows"
    workflows.mkdir(parents=True)
    for index in range(3):
        (workflows / f"wf-{index}.json").write_text("{}", encoding="utf-8")

    context = collect_context(tmp_path, graph={"nodes": [{"id": 1, "type": "KSampler"}]}, max_workflows=2)

    assert context["graph"]["node_count"] == 1
    assert context["custom_nodes"][0]["name"] == "NodeA"
    assert context["custom_nodes"][0]["state"] == "enabled"
    assert context["custom_nodes"][1]["state"] == "disabled"
    assert len(context["workflows"]) == 2
    assert context["workflows_truncated"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_context.py -q
```

Expected: FAIL with missing `context.py`.

- [ ] **Step 3: Implement context collection**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/context.py`:

```python
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
        rows.append({
            "name": child.name.removesuffix(".disabled"),
            "path": str(child.relative_to(root)),
            "state": "disabled" if child.name.endswith(".disabled") else "enabled",
        })
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
```

- [ ] **Step 4: Add `/agent/context` route**

Modify `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py` so it contains:

```python
from pathlib import Path

from aiohttp import web

from .context import collect_context
from .health import build_health_payload


_REGISTERED = False


async def _json_request(request) -> dict:
    if request.can_read_body:
        return await request.json()
    return {}


def register_routes(prompt_server=None) -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    if prompt_server is None:
        from server import PromptServer

        prompt_server = PromptServer.instance

    routes = prompt_server.routes

    @routes.get("/agent/health")
    async def agent_health(request):
        return web.json_response(build_health_payload())

    @routes.post("/agent/context")
    async def agent_context(request):
        body = await _json_request(request)
        graph = body.get("graph")
        context = collect_context(Path.cwd(), graph=graph)
        return web.json_response(context)

    _REGISTERED = True
```

- [ ] **Step 5: Run tests and verify route**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_context.py -q
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
curl -sf -X POST http://127.0.0.1:8188/agent/context -H 'Content-Type: application/json' -d '{"graph":{"nodes":[{"id":1,"type":"KSampler"}]}}'
```

Expected: tests PASS; route JSON includes `"custom_nodes"` and `"graph"`.

- [ ] **Step 6: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/context.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py tests-unit/agent_workbench/test_context.py
git commit -m "feat: collect agent workbench context"
```

### Task 5: Dry-Run and Apply Route Gate

**Files:**
- Modify: `tests-unit/agent_workbench/test_actions.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`

- [ ] **Step 1: Add failing dry-run/apply tests**

Append to `tests-unit/agent_workbench/test_actions.py`:

```python
from agent_workbench.actions import apply_plan, dry_run_plan


def test_dry_run_returns_plan_hash_and_preview():
    result = dry_run_plan({"summary": "inspect", "actions": [{"type": "context.collect", "payload": {}}]})

    assert result["status"] == "dry_run"
    assert result["plan"]["plan_hash"]
    assert result["preview"][0]["type"] == "context.collect"


def test_apply_rejects_changed_hash():
    dry_run = dry_run_plan({"summary": "inspect", "actions": [{"type": "context.collect", "payload": {}}]})

    result = apply_plan(dry_run["plan"], approved_hash="wrong")

    assert result["ok"] is False
    assert result["error"] == "approved_hash_mismatch"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_actions.py -q
```

Expected: FAIL with missing `dry_run_plan`.

- [ ] **Step 3: Implement dry-run and initial apply gate**

Append to `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`:

```python
def dry_run_plan(raw: dict) -> dict:
    plan = validate_plan(raw)
    preview = [
        {
            "type": action["type"],
            "capability": action["capability"],
            "risk_level": action["risk_level"],
            "payload": action["payload"],
        }
        for action in plan["actions"]
    ]
    return {"status": "dry_run", "plan": plan, "preview": preview}


def apply_plan(plan: dict, approved_hash: str) -> dict:
    expected_hash = stable_plan_hash(plan)
    if approved_hash != expected_hash:
        return {"ok": False, "error": "approved_hash_mismatch", "expected_hash": expected_hash}
    if plan.get("requires_confirmation") and not plan.get("confirmed"):
        return {"ok": False, "error": "confirmation_required"}
    return {"ok": True, "status": "accepted", "applied": []}
```

- [ ] **Step 4: Add `/agent/dry-run` and `/agent/apply` routes**

Modify imports in `routes.py`:

```python
from .actions import PlanValidationError, apply_plan, dry_run_plan
```

Add these route handlers inside `register_routes`:

```python
    @routes.post("/agent/dry-run")
    async def agent_dry_run(request):
        body = await _json_request(request)
        try:
            return web.json_response(dry_run_plan(body))
        except PlanValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    @routes.post("/agent/apply")
    async def agent_apply(request):
        body = await _json_request(request)
        plan = body.get("plan", {})
        approved_hash = body.get("approved_hash", "")
        return web.json_response(apply_plan(plan, approved_hash=approved_hash))
```

- [ ] **Step 5: Run tests and route smoke**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_actions.py -q
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
curl -sf -X POST http://127.0.0.1:8188/agent/dry-run -H 'Content-Type: application/json' -d '{"summary":"inspect","actions":[{"type":"context.collect","payload":{}}]}'
```

Expected: tests PASS; route JSON contains `"status": "dry_run"` and a `plan_hash`.

- [ ] **Step 6: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py tests-unit/agent_workbench/test_actions.py
git commit -m "feat: add agent dry-run gate"
```

### Task 6: Frontend Plan Preview and Confirmation UI

**Files:**
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`

- [ ] **Step 1: Replace the frontend with a plan-first operator UI**

Replace `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js` with:

```javascript
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

import "./agent-workbench.css";

function currentGraphSnapshot() {
  const graph = app.graph;
  return {
    nodes: (graph?._nodes || []).map((node) => ({
      id: node.id,
      type: node.type,
      title: node.title,
      pos: node.pos,
      selected: Boolean(node.selected),
      widgets: (node.widgets || []).map((widget) => ({ name: widget.name, value: widget.value })),
    })),
    links: graph?.links || [],
  };
}

async function postJson(path, body) {
  const response = await api.fetchApi(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return await response.json();
}

function renderJson(element, value) {
  element.textContent = JSON.stringify(value, null, 2);
}

function createWorkbenchPanel() {
  const panel = document.createElement("section");
  panel.id = "agent-workbench-panel";
  panel.innerHTML = `
    <header>
      <strong>Agent Workbench</strong>
      <button id="agent-workbench-context" title="Refresh context">Context</button>
    </header>
    <textarea id="agent-workbench-input" placeholder="Describe the ComfyUI operation"></textarea>
    <div class="agent-workbench-actions">
      <button id="agent-workbench-plan">Plan</button>
      <button id="agent-workbench-apply" disabled>Apply</button>
    </div>
    <pre id="agent-workbench-output">Ready for an operation.</pre>
  `;
  document.body.appendChild(panel);

  const input = panel.querySelector("#agent-workbench-input");
  const output = panel.querySelector("#agent-workbench-output");
  const applyButton = panel.querySelector("#agent-workbench-apply");
  let lastDryRun = null;

  panel.querySelector("#agent-workbench-context").addEventListener("click", async () => {
    const context = await postJson("/agent/context", { graph: currentGraphSnapshot() });
    renderJson(output, context);
  });

  panel.querySelector("#agent-workbench-plan").addEventListener("click", async () => {
    const summary = input.value.trim() || "Inspect current ComfyUI context";
    lastDryRun = await postJson("/agent/dry-run", {
      summary,
      actions: [{ type: "context.collect", payload: { graph: currentGraphSnapshot() } }],
    });
    applyButton.disabled = !lastDryRun.plan || lastDryRun.plan.requires_confirmation;
    renderJson(output, lastDryRun);
  });

  applyButton.addEventListener("click", async () => {
    if (!lastDryRun?.plan) {
      return;
    }
    const result = await postJson("/agent/apply", {
      plan: lastDryRun.plan,
      approved_hash: lastDryRun.plan.plan_hash,
    });
    renderJson(output, result);
  });
}

app.registerExtension({
  name: "ComfyUI.AgentWorkbench",
  setup() {
    createWorkbenchPanel();
  },
});
```

- [ ] **Step 2: Add UI states for plan/apply controls**

Append to `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`:

```css
.agent-workbench-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

#agent-workbench-panel button {
  min-height: 32px;
  border: 1px solid rgba(180, 190, 205, 0.35);
  border-radius: 6px;
  background: #202633;
  color: #f4f7fb;
}

#agent-workbench-panel button:disabled {
  opacity: 0.45;
}
```

- [ ] **Step 3: Browser smoke**

Run:

```bash
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
curl -sf http://127.0.0.1:8188/extensions | rg 'ComfyUI-AgentWorkbench'
```

Expected: `/extensions` contains the workbench JS file. In a Windows browser, the ComfyUI page shows an Agent Workbench panel with Context, Plan, and Apply controls.

- [ ] **Step 4: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css
git commit -m "feat: add agent plan preview panel"
```

### Task 7: Graph Action Executor in the Browser

**Files:**
- Create: `custom_nodes/ComfyUI-AgentWorkbench/js/graph-actions.js`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`

- [ ] **Step 1: Add graph action support to the schema**

Extend `ACTION_REGISTRY` in `actions.py` with these existing entries if absent:

```python
ACTION_REGISTRY.update({
    "graph.set_widget": ("graph.edit", "canvas"),
    "graph.add_node": ("graph.edit", "canvas"),
    "graph.connect": ("graph.edit", "canvas"),
})
```

Keep one definition per key in the final file.

- [ ] **Step 2: Create browser graph action executor**

Create `custom_nodes/ComfyUI-AgentWorkbench/js/graph-actions.js`:

```javascript
import { app } from "../../scripts/app.js";

export function applyGraphAction(action) {
  if (action.type === "graph.set_widget") {
    const node = app.graph.getNodeById(action.payload.node_id);
    if (!node) {
      throw new Error(`Node not found: ${action.payload.node_id}`);
    }
    const widget = (node.widgets || []).find((item) => item.name === action.payload.widget);
    if (!widget) {
      throw new Error(`Widget not found: ${action.payload.widget}`);
    }
    widget.value = action.payload.value;
    app.graph.setDirtyCanvas(true, true);
    return { type: action.type, node_id: node.id, widget: widget.name };
  }
  throw new Error(`Unsupported browser graph action: ${action.type}`);
}

export function applyGraphActions(actions) {
  return actions
    .filter((action) => action.type.startsWith("graph."))
    .map((action) => applyGraphAction(action));
}
```

- [ ] **Step 3: Wire graph actions into Apply**

Modify `agent-workbench.js` imports:

```javascript
import { applyGraphActions } from "./graph-actions.js";
```

Modify the apply click handler so it applies browser graph actions after server approval:

```javascript
  applyButton.addEventListener("click", async () => {
    if (!lastDryRun?.plan) {
      return;
    }
    const result = await postJson("/agent/apply", {
      plan: lastDryRun.plan,
      approved_hash: lastDryRun.plan.plan_hash,
    });
    if (result.ok) {
      result.browser_applied = applyGraphActions(lastDryRun.plan.actions);
    }
    renderJson(output, result);
  });
```

- [ ] **Step 4: Manual graph verification**

Open ComfyUI in the Windows browser, select a node with a text widget, and use DevTools to run:

```javascript
await fetch('/agent/dry-run', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    summary: 'Change widget',
    actions: [{type: 'graph.set_widget', payload: {node_id: app.graph._nodes[0].id, widget: app.graph._nodes[0].widgets[0].name, value: app.graph._nodes[0].widgets[0].value}}]
  })
}).then(r => r.json())
```

Expected: the returned plan validates and the panel Apply button can execute the graph action without a server restart.

- [ ] **Step 5: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/js/graph-actions.js custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py
git commit -m "feat: apply validated graph actions"
```

### Task 8: Rule-Based Planner and Provider Abstraction

**Files:**
- Create: `tests-unit/agent_workbench/test_planner.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/planner.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`

- [ ] **Step 1: Write failing planner tests**

Create `tests-unit/agent_workbench/test_planner.py`:

```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.planner import RuleBasedPlanner


def test_rule_planner_free_memory():
    plan = RuleBasedPlanner().plan("释放内存", context={})

    assert plan["actions"][0]["type"] == "runtime.free_memory"


def test_rule_planner_reserve_vram():
    plan = RuleBasedPlanner().plan("把 compose reserve-vram 改到 10", context={})

    assert plan["actions"][0]["type"] == "compose.set_reserve_vram"
    assert plan["actions"][0]["payload"]["value"] == "10"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_planner.py -q
```

Expected: FAIL with missing `planner.py`.

- [ ] **Step 3: Implement the first planner**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/planner.py`:

```python
import os
import re


class RuleBasedPlanner:
    def plan(self, message: str, context: dict) -> dict:
        text = message.strip()
        lowered = text.lower()
        if "reserve-vram" in lowered or "reserve vram" in lowered:
            match = re.search(r"(\d+)", text)
            value = match.group(1) if match else "8"
            return {
                "summary": f"Set compose reserve-vram to {value}",
                "actions": [{"type": "compose.set_reserve_vram", "payload": {"value": value}}],
            }
        if "free" in lowered or "释放" in text or "内存" in text:
            return {
                "summary": "Free ComfyUI memory",
                "actions": [{"type": "runtime.free_memory", "payload": {"unload_models": True, "free_memory": True}}],
            }
        return {
            "summary": f"Inspect context for: {text}",
            "actions": [{"type": "context.collect", "payload": {"message": text}}],
        }


def default_planner() -> RuleBasedPlanner:
    provider = os.environ.get("AGENT_WORKBENCH_PROVIDER", "rules")
    if provider != "rules":
        return RuleBasedPlanner()
    return RuleBasedPlanner()
```

- [ ] **Step 4: Add `/agent/plan` route**

Modify `routes.py` imports:

```python
from .planner import default_planner
```

Add this route handler inside `register_routes`:

```python
    @routes.post("/agent/plan")
    async def agent_plan(request):
        body = await _json_request(request)
        message = body.get("message", "")
        graph = body.get("graph")
        context = collect_context(Path.cwd(), graph=graph)
        raw_plan = default_planner().plan(message, context=context)
        try:
            return web.json_response(dry_run_plan(raw_plan))
        except PlanValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc), "raw_plan": raw_plan}, status=400)
```

- [ ] **Step 5: Wire Plan button to `/agent/plan`**

In `agent-workbench.js`, replace the Plan button handler with:

```javascript
  panel.querySelector("#agent-workbench-plan").addEventListener("click", async () => {
    const message = input.value.trim() || "Inspect current ComfyUI context";
    lastDryRun = await postJson("/agent/plan", {
      message,
      graph: currentGraphSnapshot(),
    });
    applyButton.disabled = !lastDryRun.plan || lastDryRun.plan.requires_confirmation;
    renderJson(output, lastDryRun);
  });
```

- [ ] **Step 6: Run tests and route smoke**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_planner.py -q
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
curl -sf -X POST http://127.0.0.1:8188/agent/plan -H 'Content-Type: application/json' -d '{"message":"释放内存"}'
```

Expected: tests PASS; route returns a dry-run for `runtime.free_memory`.

- [ ] **Step 7: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/planner.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js tests-unit/agent_workbench/test_planner.py
git commit -m "feat: plan agent actions from natural language"
```

### Task 9: Allowlisted Runtime Command Runner

**Files:**
- Create: `tests-unit/agent_workbench/test_commands.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/__init__.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/commands.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/runtime.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`

- [ ] **Step 1: Write failing command safety tests**

Create `tests-unit/agent_workbench/test_commands.py`:

```python
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.commands import CommandRejected, validate_command
from agent_workbench.ops.runtime import build_free_memory_request, stop_ollama_model_command


def test_rejects_sudo_and_shell_operators():
    with pytest.raises(CommandRejected):
        validate_command(["sudo", "systemctl", "stop", "ollama"])
    with pytest.raises(CommandRejected):
        validate_command(["bash", "-lc", "docker ps"])


def test_allows_known_non_sudo_commands():
    assert validate_command(["docker", "ps", "-a"]) == ["docker", "ps", "-a"]
    assert stop_ollama_model_command("nemotron-3-nano:30b") == ["ollama", "stop", "nemotron-3-nano:30b"]
    assert build_free_memory_request() == {"unload_models": True, "free_memory": True}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_commands.py -q
```

Expected: FAIL with missing `ops.commands`.

- [ ] **Step 3: Implement command validation and runtime helpers**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/__init__.py`:

```python
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/commands.py`:

```python
import subprocess


class CommandRejected(ValueError):
    pass


ALLOWED_BINARIES = {"docker", "ollama", "free", "curl"}
DENIED_BINARIES = {"sudo", "bash", "sh", "python", "python3"}
SHELL_TOKENS = {";", "&&", "||", "|", ">", "<", "$(", "`"}


def validate_command(args: list[str]) -> list[str]:
    if not args:
        raise CommandRejected("empty command")
    if args[0] in DENIED_BINARIES:
        raise CommandRejected(f"denied binary: {args[0]}")
    if args[0] not in ALLOWED_BINARIES:
        raise CommandRejected(f"unsupported binary: {args[0]}")
    joined = " ".join(args)
    if any(token in joined for token in SHELL_TOKENS):
        raise CommandRejected("shell syntax is not allowed")
    return args


def run_command(args: list[str], timeout_seconds: int = 60) -> dict:
    safe_args = validate_command(args)
    completed = subprocess.run(
        safe_args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "args": safe_args,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }
```

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/runtime.py`:

```python
def build_free_memory_request() -> dict:
    return {"unload_models": True, "free_memory": True}


def stop_ollama_model_command(model_name: str) -> list[str]:
    return ["ollama", "stop", model_name]


def docker_restart_command(container_name: str = "comfyui-gb10") -> list[str]:
    return ["docker", "restart", container_name]


def free_memory_command() -> list[str]:
    return ["free", "-h"]
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_commands.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops tests-unit/agent_workbench/test_commands.py
git commit -m "feat: add safe runtime command runner"
```

### Task 10: Compose Reserve-VRAM Operation

**Files:**
- Create: `tests-unit/agent_workbench/test_compose_ops.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/compose.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`

- [ ] **Step 1: Write failing compose tests**

Create `tests-unit/agent_workbench/test_compose_ops.py`:

```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.compose import patch_reserve_vram, validate_compose_text


COMPOSE_TEXT = """services:
  comfyui-gb10:
    command:
      - main.py
      - --reserve-vram
      - "8"  # keep this comment
"""


def test_validate_compose_text_reads_service():
    data = validate_compose_text(COMPOSE_TEXT)

    assert "comfyui-gb10" in data["services"]


def test_patch_reserve_vram_preserves_comment_line_shape():
    patched = patch_reserve_vram(COMPOSE_TEXT, "10")

    assert '- "10"  # keep this comment' in patched
    assert '--reserve-vram' in patched
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_compose_ops.py -q
```

Expected: FAIL with missing `ops.compose`.

- [ ] **Step 3: Implement compose validation and targeted patching**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/compose.py`:

```python
from pathlib import Path

import yaml

from ..snapshots import snapshot_file


DEFAULT_COMPOSE_PATH = Path("dgx_spark_ltx_setup/docker-compose.yml")


def validate_compose_text(text: str) -> dict:
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "services" not in data:
        raise ValueError("compose file must contain services")
    if "comfyui-gb10" not in data["services"]:
        raise ValueError("compose file must define comfyui-gb10")
    return data


def patch_reserve_vram(text: str, value: str) -> str:
    validate_compose_text(text)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "- --reserve-vram":
            value_index = index + 1
            if value_index >= len(lines):
                raise ValueError("reserve-vram value line is missing")
            old_line = lines[value_index]
            prefix = old_line.split("-", 1)[0] + "- "
            suffix = ""
            if "#" in old_line:
                suffix = "  #" + old_line.split("#", 1)[1]
            lines[value_index] = f'{prefix}"{value}"{suffix}'
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    raise ValueError("reserve-vram flag not found")


def plan_reserve_vram(compose_path: Path, value: str) -> dict:
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_reserve_vram(original, value)
    return {"path": str(compose_path), "changed": original != patched, "before": original, "after": patched}


def apply_reserve_vram(compose_path: Path, value: str, backup_dir: Path) -> dict:
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_reserve_vram(original, value)
    snapshot = snapshot_file(compose_path, backup_dir, reason="compose-reserve-vram")
    compose_path.write_text(patched, encoding="utf-8")
    return {"path": str(compose_path), "snapshot": str(snapshot), "value": value}
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_compose_ops.py -q
```

Expected: PASS.

- [ ] **Step 5: Add service apply command definition**

When wiring `compose.set_reserve_vram` to real apply in a later task, use this non-shell command:

```python
["docker", "compose", "-f", "dgx_spark_ltx_setup/docker-compose.yml", "up", "-d"]
```

Do not use `restart` after compose edits because restart does not reread changed compose configuration.

- [ ] **Step 6: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/compose.py tests-unit/agent_workbench/test_compose_ops.py
git commit -m "feat: add compose reserve-vram operation"
```

### Task 11: ComfyUI-Manager Custom Node Adapter

**Files:**
- Create: `tests-unit/agent_workbench/test_manager_ops.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/manager.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`

- [ ] **Step 1: Write failing manager adapter tests**

Create `tests-unit/agent_workbench/test_manager_ops.py`:

```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.manager import manager_request_for_action


def test_manager_install_git_url_request():
    request = manager_request_for_action({
        "type": "custom_node.install",
        "payload": {"method": "git_url", "url": "https://example.com/node.git"},
    })

    assert request["path"] == "/customnode/install/git_url"
    assert request["method"] == "POST"
    assert request["body"] == "https://example.com/node.git"


def test_manager_disable_request_uses_queue_disable():
    request = manager_request_for_action({
        "type": "custom_node.disable",
        "payload": {"id": "ComfyUI-TestNode", "version": "1.0.0", "ui_id": "ComfyUI-TestNode"},
    })

    assert request["path"] == "/manager/queue/disable"
    assert request["json"]["id"] == "ComfyUI-TestNode"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_manager_ops.py -q
```

Expected: FAIL with missing `ops.manager`.

- [ ] **Step 3: Implement manager request mapping**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/manager.py`:

```python
from urllib.parse import urlparse


class ManagerActionError(ValueError):
    pass


def _require_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManagerActionError("custom node git_url must be http or https")
    return url


def manager_request_for_action(action: dict) -> dict:
    action_type = action["type"]
    payload = action.get("payload", {})
    if action_type == "custom_node.install" and payload.get("method") == "git_url":
        return {"method": "POST", "path": "/customnode/install/git_url", "body": _require_url(payload["url"])}
    if action_type == "custom_node.install" and payload.get("method") == "manager_queue":
        return {"method": "POST", "path": "/manager/queue/install", "json": payload["node"]}
    if action_type == "custom_node.disable":
        return {
            "method": "POST",
            "path": "/manager/queue/disable",
            "json": {
                "id": payload["id"],
                "version": payload.get("version", "unknown"),
                "ui_id": payload.get("ui_id", payload["id"]),
                "files": payload.get("files", []),
            },
        }
    if action_type == "custom_node.enable":
        node = dict(payload)
        node["skip_post_install"] = True
        return {"method": "POST", "path": "/manager/queue/install", "json": node}
    raise ManagerActionError(f"unsupported manager action: {action_type}")
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_manager_ops.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/manager.py tests-unit/agent_workbench/test_manager_ops.py
git commit -m "feat: map agent actions to comfyui manager"
```

### Task 12: Apply Dispatcher for Runtime, Compose, Manager, and Sudo Print Actions

**Files:**
- Create: `tests-unit/agent_workbench/test_apply_dispatch.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/executor.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`

- [ ] **Step 1: Add failing dispatch tests**

Create `tests-unit/agent_workbench/test_apply_dispatch.py`:

```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.actions import apply_plan, dry_run_plan
from agent_workbench.executor import RecordingExecutor


COMPOSE_TEXT = """services:
  comfyui-gb10:
    command:
      - main.py
      - --reserve-vram
      - "8"  # keep this comment
"""


def test_apply_dispatches_confirmed_compose_change(tmp_path):
    compose_path = tmp_path / "dgx_spark_ltx_setup" / "docker-compose.yml"
    compose_path.parent.mkdir(parents=True)
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")
    dry_run = dry_run_plan({
        "summary": "Set reserve vram",
        "actions": [{"type": "compose.set_reserve_vram", "payload": {"value": "10"}}],
    })
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True
    executor = RecordingExecutor()

    result = apply_plan(plan, approved_hash=dry_run["plan"]["plan_hash"], root=tmp_path, executor=executor)

    assert result["ok"] is True
    assert result["applied"][0]["type"] == "compose.set_reserve_vram"
    assert '- "10"  # keep this comment' in compose_path.read_text(encoding="utf-8")
    assert executor.commands[-1] == ["docker", "compose", "-f", "dgx_spark_ltx_setup/docker-compose.yml", "up", "-d"]


def test_custom_node_apply_returns_manager_request_for_frontend_execution(tmp_path):
    dry_run = dry_run_plan({
        "summary": "Install node",
        "actions": [{"type": "custom_node.install", "payload": {"method": "git_url", "url": "https://example.com/node.git"}}],
    })
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True
    executor = RecordingExecutor()

    result = apply_plan(plan, approved_hash=dry_run["plan"]["plan_hash"], root=tmp_path, executor=executor)

    assert result["ok"] is True
    assert result["applied"][0]["manager_request"]["path"] == "/customnode/install/git_url"
    assert executor.manager_requests[0]["body"] == "https://example.com/node.git"


def test_sudo_action_is_print_only(tmp_path):
    dry_run = dry_run_plan({
        "summary": "Suggest swapoff",
        "actions": [{"type": "sudo.print_command", "payload": {"command": "sudo swapoff -a", "why": "avoid swap pressure"}}],
    })
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True

    result = apply_plan(plan, approved_hash=dry_run["plan"]["plan_hash"], root=tmp_path, executor=RecordingExecutor())

    assert result["ok"] is True
    assert result["applied"][0] == {"type": "sudo.print_command", "command": "sudo swapoff -a", "executed": False}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_apply_dispatch.py -q
```

Expected: FAIL with missing `executor.py` or missing dispatch behavior.

- [ ] **Step 3: Add execution adapters**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/executor.py`:

```python
from .ops.commands import run_command


class RecordingExecutor:
    def __init__(self):
        self.commands = []
        self.manager_requests = []

    def run_command(self, args: list[str]) -> dict:
        self.commands.append(args)
        return {"args": args, "returncode": 0, "stdout": "", "stderr": ""}

    def manager_request(self, request: dict) -> dict:
        self.manager_requests.append(request)
        return {"status": "frontend_required", "request": request}


class DefaultExecutor:
    def run_command(self, args: list[str]) -> dict:
        return run_command(args)

    def manager_request(self, request: dict) -> dict:
        return {"status": "frontend_required", "request": request}
```

- [ ] **Step 4: Implement action dispatch**

Modify `actions.py` imports:

```python
from pathlib import Path

from .executor import DefaultExecutor
from .ops.compose import DEFAULT_COMPOSE_PATH, apply_reserve_vram
from .ops.manager import manager_request_for_action
```

Add this dispatcher above `apply_plan`:

```python
def _agent_backup_dir(root: Path) -> Path:
    return root / "user" / "default" / "agent_workbench" / "backups"


def _dispatch_action(action: dict, root: Path, executor) -> dict:
    action_type = action["type"]
    payload = action.get("payload", {})
    if action_type.startswith("graph."):
        return {"type": action_type, "browser_required": True, "payload": payload}
    if action_type == "context.collect":
        return {"type": action_type, "applied": False, "reason": "context action is read-only"}
    if action_type == "compose.set_reserve_vram":
        compose_path = root / DEFAULT_COMPOSE_PATH
        result = apply_reserve_vram(compose_path, str(payload["value"]), _agent_backup_dir(root))
        command_result = executor.run_command(["docker", "compose", "-f", str(DEFAULT_COMPOSE_PATH), "up", "-d"])
        return {"type": action_type, "compose": result, "command": command_result}
    if action_type == "service.restart_container":
        container = payload.get("container", "comfyui-gb10")
        return {"type": action_type, "command": executor.run_command(["docker", "restart", container])}
    if action_type == "runtime.stop_ollama_model":
        return {"type": action_type, "command": executor.run_command(["ollama", "stop", payload["model"]])}
    if action_type == "runtime.free_memory":
        return {"type": action_type, "http_request": {"path": "/free", "json": payload}}
    if action_type.startswith("custom_node."):
        request = manager_request_for_action(action)
        executor.manager_request(request)
        return {"type": action_type, "manager_request": request}
    if action_type == "sudo.print_command":
        return {"type": action_type, "command": payload["command"], "executed": False}
    raise PlanValidationError(f"No dispatcher for action type: {action_type}")
```

Replace `apply_plan` with:

```python
def apply_plan(plan: dict, approved_hash: str, root: Path | None = None, executor=None) -> dict:
    root = root or Path.cwd()
    executor = executor or DefaultExecutor()
    plan_without_confirmation = deepcopy(plan)
    confirmed = bool(plan_without_confirmation.pop("confirmed", False))
    expected_hash = stable_plan_hash(plan_without_confirmation)
    if approved_hash != expected_hash:
        return {"ok": False, "error": "approved_hash_mismatch", "expected_hash": expected_hash}
    if plan_without_confirmation.get("requires_confirmation") and not confirmed:
        return {"ok": False, "error": "confirmation_required"}
    applied = [_dispatch_action(action, root, executor) for action in plan_without_confirmation["actions"]]
    return {"ok": True, "status": "applied", "applied": applied}
```

- [ ] **Step 5: Update `/agent/apply` route to pass the repo root**

Modify the apply handler in `routes.py`:

```python
    @routes.post("/agent/apply")
    async def agent_apply(request):
        body = await _json_request(request)
        plan = body.get("plan", {})
        approved_hash = body.get("approved_hash", "")
        return web.json_response(apply_plan(plan, approved_hash=approved_hash, root=Path.cwd()))
```

- [ ] **Step 6: Execute frontend-required requests after server approval**

Add this helper to `agent-workbench.js`:

```javascript
async function executeFrontendRequest(request) {
  const options = { method: request.method || "POST", headers: {} };
  if (request.json) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(request.json);
  }
  if (request.body) {
    options.body = request.body;
  }
  const response = await api.fetchApi(request.path, options);
  const result = { path: request.path, status: response.status };
  if (request.path.startsWith("/manager/queue/") && response.status === 200) {
    const queueResponse = await api.fetchApi("/manager/queue/start", { method: "POST" });
    result.queue_start_status = queueResponse.status;
  }
  return result;
}
```

Modify the apply handler after `const result = await postJson(...)`:

```javascript
    if (result.ok) {
      result.browser_applied = applyGraphActions(lastDryRun.plan.actions);
      result.frontend_requests = [];
      for (const applied of result.applied || []) {
        if (applied.manager_request) {
          result.frontend_requests.push(await executeFrontendRequest(applied.manager_request));
        }
        if (applied.http_request) {
          result.frontend_requests.push(await executeFrontendRequest({
            method: "POST",
            path: applied.http_request.path,
            json: applied.http_request.json,
          }));
        }
      }
    }
```

- [ ] **Step 7: Run dispatch tests**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_apply_dispatch.py tests-unit/agent_workbench/test_actions.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/executor.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js tests-unit/agent_workbench/test_apply_dispatch.py
git commit -m "feat: execute confirmed agent actions"
```

### Task 13: Workflow Save and Rollback Actions

**Files:**
- Create: `tests-unit/agent_workbench/test_workflow_ops.py`
- Create: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/workflows.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/actions.py`

- [ ] **Step 1: Write failing workflow tests**

Create `tests-unit/agent_workbench/test_workflow_ops.py`:

```python
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.workflows import save_workflow_with_snapshot


def test_save_workflow_with_snapshot(tmp_path):
    target = tmp_path / "user" / "default" / "workflows" / "sample.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"old": true}', encoding="utf-8")

    result = save_workflow_with_snapshot(target, {"new": True}, tmp_path / "backups")

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert Path(result["snapshot"]).exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_workflow_ops.py -q
```

Expected: FAIL with missing `ops.workflows`.

- [ ] **Step 3: Implement workflow snapshot save**

Create `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/workflows.py`:

```python
import json
from pathlib import Path

from ..snapshots import snapshot_file


def save_workflow_with_snapshot(target: Path, workflow: dict, backup_dir: Path) -> dict:
    if target.exists():
        snapshot = snapshot_file(target, backup_dir, reason="workflow-save")
    else:
        snapshot = None
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(target), "snapshot": str(snapshot) if snapshot else None}
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench/test_workflow_ops.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/workflows.py tests-unit/agent_workbench/test_workflow_ops.py
git commit -m "feat: save workflows with snapshots"
```

### Task 14: End-to-End Verification and Operator Polish

**Files:**
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`
- Modify: `docs/superpowers/specs/2026-06-25-comfyui-agent-workbench-design.md` only if implementation reveals a spec mismatch.

- [ ] **Step 1: Run the focused Python test suite**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench -q
```

Expected: all agent workbench tests PASS.

- [ ] **Step 2: Run syntax verification**

Run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m py_compile custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/*.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/*.py
```

Expected: command exits 0.

- [ ] **Step 3: Restart ComfyUI and verify route health**

Run:

```bash
docker compose -f dgx_spark_ltx_setup/docker-compose.yml restart comfyui-gb10
curl -sf http://127.0.0.1:8188/agent/health
curl -sf -X POST http://127.0.0.1:8188/agent/context -H 'Content-Type: application/json' -d '{"graph":{"nodes":[]}}'
curl -sf -X POST http://127.0.0.1:8188/agent/plan -H 'Content-Type: application/json' -d '{"message":"释放内存"}'
```

Expected: all three requests return JSON; `/agent/plan` returns a dry-run with `runtime.free_memory`.

- [ ] **Step 4: Verify frontend loading**

Run:

```bash
curl -sf http://127.0.0.1:8188/extensions | rg 'ComfyUI-AgentWorkbench'
```

Expected: `/extensions` includes the JS asset.

- [ ] **Step 5: Verify Windows browser workflow**

From Windows, open ComfyUI on the Spark host. Confirm:

- The Agent Workbench panel appears.
- Context displays current graph and custom nodes.
- Typing `释放内存` produces a `runtime.free_memory` dry-run.
- Typing `把 compose reserve-vram 改到 10` produces a service-level plan requiring confirmation.
- Cancelling the confirmation returns `user_cancelled`.
- Graph widget edits can apply without leaving the page.

- [ ] **Step 6: Commit final polish**

```bash
git status --short
git add custom_nodes/ComfyUI-AgentWorkbench tests-unit/agent_workbench
git commit -m "feat: complete agent workbench verification"
```

## Final Verification Gate

Before claiming implementation complete, run:

```bash
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m pytest tests-unit/agent_workbench -q
docker exec -w /workspace/ComfyUI comfyui-gb10 python3 -m py_compile custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/*.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/ops/*.py
curl -sf http://127.0.0.1:8188/agent/health
curl -sf http://127.0.0.1:8188/extensions | rg 'ComfyUI-AgentWorkbench'
```

Expected final state:

- Agent Workbench panel loads in ComfyUI.
- `/agent/health`, `/agent/context`, `/agent/plan`, `/agent/dry-run`, and `/agent/apply` respond.
- Natural-language planning creates validated structured plans.
- Graph changes apply through the browser graph adapter.
- Custom-node and compose actions execute after confirmation, record their results, and expose rollback or frontend follow-up where required.
- Sudo-only actions remain print-only and are never executed by the agent.

# ComfyUI Agent Workbench Design

Date: 2026-06-25
Status: Design spec for user review. Implementation has not started.

## Purpose

Build a native ComfyUI Agent Workbench inside this fork of ComfyUI. The workbench is not a chat-only panel. It is a natural-language control surface that can inspect and operate the current ComfyUI project, including the graph, workflows, installed custom nodes, the local Docker compose service, and selected host operations on the Spark/GB10 machine.

The first client target is Windows using a browser connected to the Spark ComfyUI server. Mac should work later through the same browser UI. The Agent runs server-side on Spark and uses the ComfyUI page only as its operator console.

## Current System Facts

- Repo path: `/home/srain/ComfyUI`.
- Upstream remote: `https://github.com/comfyanonymous/ComfyUI.git`.
- Current ComfyUI reports version `0.21.0` and required frontend `1.43.18`.
- The live service is the Docker container `comfyui-gb10` on port `8188`.
- The live compose file on this machine is `dgx_spark_ltx_setup/docker-compose.yml`.
- The container mounts `/home/srain/ComfyUI` to `/workspace/ComfyUI`.
- The active command includes GB10-specific safety flags such as `--disable-cuda-malloc`, `--disable-pinned-memory`, `--use-pytorch-cross-attention`, and `--reserve-vram 8`.
- Existing extension loading supports custom node web assets through `WEB_DIRECTORY`, and server routes can be added through `PromptServer.instance.routes`.
- Current custom nodes include ComfyUI-Manager, ComfyUI-LTXVideo, ComfyUI-VideoHelperSuite, SwarmComfyCommon, SwarmComfyExtra, and `websocket_image_save.py`.
- Existing ComfyUI APIs provide enough graph and node metadata for an agent to reason over `/object_info`, `/prompt`, `/history`, `/queue`, `/system_stats`, `/features`, and websocket status.

## Non-Goals

- Do not build a separate LibTV-style external browser workspace as the primary experience.
- Do not rely on a visual browser companion for the design workflow.
- Do not execute human-only sudo actions from the agent. The agent may explain and print sudo commands when appropriate, but the human runs them.
- Do not give the language model raw unrestricted shell access.
- Do not fork the full ComfyUI frontend first unless the extension path cannot support the required UX.

## Product Shape

The Agent Workbench appears as a dockable ComfyUI side panel. It contains:

- A natural-language command box.
- Context chips for current graph, selected nodes, last error, queue state, model/runtime state, custom-node state, and service health.
- A plan card that shows what the agent understood, which capabilities it will use, and why.
- A graph diff or workflow diff before edits are applied.
- A permission prompt for every high-risk action.
- A live action log with command outputs, route responses, and verification results.
- A rollback drawer for backups, previous compose files, workflow snapshots, and failed node operations.

The interface should feel like an operator cockpit, not a chatbot. Chat is only the input and explanation layer. The core UI is plans, diffs, approvals, execution, verification, and rollback.

## Capability Scope C: Maximum Agent

The requested scope is C/max functionality. The Agent can operate across these domains:

1. Canvas and workflow actions
   - Inspect the current graph.
   - Add, remove, connect, disconnect, rename, and reposition nodes.
   - Change widget values and prompts.
   - Load, save, clone, and repair workflows.
   - Queue prompts, interrupt runs, free memory, and inspect history.

2. Project and resource actions
   - Search local workflows, inputs, outputs, and known project folders with bounded indexing.
   - Inspect model references in workflows.
   - Detect missing model files or missing node classes.
   - Suggest resource fixes without silently downloading large files.

3. Custom-node actions
   - List installed custom nodes and their enabled/disabled state.
   - Detect missing custom nodes from workflow errors or unknown node types.
   - Install, update, disable, and enable custom nodes through a managed action path.
   - Treat hard deletion as an expert destructive action that requires a separate backup, explicit confirmation, and rollback story. The first implementation should prefer reversible disable over delete.
   - Prefer ComfyUI-Manager APIs or metadata where available.
   - Fall back to controlled git/pip operations only through predefined action handlers.
   - Show dependency and restart impact before applying.

4. Compose and service operations
   - Inspect container health, logs, compose configuration, ports, and memory pressure.
   - Edit `dgx_spark_ltx_setup/docker-compose.yml` through structured YAML changes.
   - Apply compose changes with `docker compose -f dgx_spark_ltx_setup/docker-compose.yml up -d`.
   - Restart `comfyui-gb10` when needed.
   - Verify `/system_stats`, `/extensions`, and websocket availability after restart.
   - Keep backups and expose a rollback action for compose changes.

5. GB10 memory operations
   - Call `/free` and verify memory behavior.
   - Inspect `free -h`, container status, and Ollama loaded models.
   - Stop loaded Ollama models with non-sudo commands when the user approves.
   - Print human-only sudo steps such as `sudo swapoff -a`, `sudo nvidia-smi -lgc ...`, or `sudo systemctl stop ollama` when they are useful, but never run them.

## Architecture

### Frontend Extension

Add a custom node extension, initially under `custom_nodes/ComfyUI-AgentWorkbench`.

Primary files:

- `__init__.py` registers `WEB_DIRECTORY = "js"` and imports backend routes.
- `js/agent-workbench.js` registers the panel with ComfyUI's extension API.
- `js/agent-workbench.css` styles the panel with dense operator UI patterns.

The frontend talks to the backend through new `/agent/*` routes. It also uses the existing ComfyUI frontend graph APIs to collect selected-node and canvas state when needed.

### Backend Routes

Add backend modules in the same custom node package:

- `agent_routes.py`: aiohttp route registration.
- `context.py`: bounded project, graph, runtime, and custom-node context collectors.
- `planner.py`: LLM/provider abstraction and prompt assembly.
- `actions.py`: action schema, validation, dry-run, apply, and verification.
- `ops.py`: Docker, compose, custom-node, and memory operation handlers.
- `permissions.py`: capability levels and approval checks.
- `audit_log.py`: append-only local operation log.

Key routes:

- `GET /agent/health`
- `POST /agent/context`
- `POST /agent/plan`
- `POST /agent/dry-run`
- `POST /agent/apply`
- `POST /agent/rollback`
- `GET /agent/capabilities`
- `GET /agent/logs/recent`

### Planner and Tool Model

The LLM never directly executes shell, Python, or arbitrary JavaScript. It produces a structured action plan. The backend validates the plan against a local action schema and rejects unsupported actions.

Action plan shape:

```json
{
  "summary": "User-facing explanation",
  "risk_level": "canvas|file|package|service|human_sudo",
  "required_capabilities": ["graph.edit", "custom_node.install"],
  "actions": [
    {
      "type": "graph.set_widget",
      "target": {"node_id": 12, "widget": "text"},
      "value": "cinematic lighting",
      "dry_run": true
    }
  ],
  "verification": [
    {"type": "graph.validate"},
    {"type": "service.healthcheck"}
  ],
  "rollback": [
    {"type": "workflow.restore_snapshot"}
  ]
}
```

The first provider implementation should support a local or OpenAI-compatible endpoint configured by environment variables or a local config file. Because this Spark host shares unified memory between ComfyUI and local LLMs, the design must support remote providers and must show local model memory pressure before loading a local model.

## Permission Model

Use explicit capability levels:

- L0: read-only context, logs, graph inspection.
- L1: graph edits in the current browser session.
- L2: queue, interrupt, `/free`, history cleanup, and runtime actions.
- L3: workflow and project file writes.
- L4: custom-node install, update, disable, enable, or remove.
- L5: compose edits, Docker restart, Docker compose up, service health repair.
- L6: human-only sudo recommendations. The agent can explain and print commands, but cannot execute them.

Rules:

- L0 and low-risk L1 can run after normal user request.
- L2 and L3 require a preview when they mutate runtime state or files.
- L4 and L5 always require an explicit confirmation dialog with impact, commands, backups, and rollback.
- L6 is never executable by the agent.
- Every apply call re-checks that the approved plan matches the dry-run hash.

## Safety and Rollback

- Workflow writes create timestamped snapshots before save.
- Compose edits parse YAML and preserve a backup before write.
- Compose apply verifies the container and ComfyUI API after the change.
- Custom-node operations record git URL, commit/ref, package operations, import result, and restart requirement.
- Package install output is captured and summarized.
- Destructive custom-node removal is not part of the first implementation. Disable is preferred over delete until backup and restore semantics are proven.
- Any action that changes runtime state writes an audit log entry.
- If verification fails after a compose or custom-node operation, the UI offers rollback as the next primary action.

## User Experience Details

The Windows user should be able to open ComfyUI at the Spark address, type a plain-language request, review the proposed operation, and approve it without leaving the ComfyUI page.

Example requests the UI should support:

- "把当前工作流改成 3 秒 LTX i2v，保持这张图作为首帧。"
- "为什么这个工作流节点红了，帮我装缺的 custom node。"
- "禁用刚才装的节点，然后重启 ComfyUI。"
- "把 compose 里的 reserve-vram 改到 10，应用并确认服务起来。"
- "先释放内存，停掉 Ollama 里正在加载的模型，然后告诉我还能不能跑 1080p 两段。"

The panel must separate three things visually:

- What the user asked.
- What the agent will actually do.
- What changed after execution.

## Implementation Phases

1. Spec and branch
   - Land this design spec on a dedicated branch.

2. Read-only workbench
   - Add the custom node extension shell.
   - Add `/agent/health`, `/agent/context`, and UI panel.
   - Show current graph, selected nodes, service status, installed custom nodes, and recent errors.

3. Graph and workflow actions
   - Implement validated action DSL for graph edits and workflow file snapshots.
   - Add dry-run, diff, confirmation, apply, and verification.

4. Natural-language planning
   - Add provider configuration.
   - Convert user requests into validated action plans.
   - Keep unsupported plans visible but blocked with a useful explanation.

5. C/max operations
   - Add custom-node install/update/disable/enable.
   - Add compose YAML edit, Docker compose apply, container restart, health verification, and rollback.
   - Add GB10 memory and Ollama non-sudo operations.

6. Polish and hardening
   - Add audit log browser, rollback drawer, permission preferences, better error display, and Windows-first usability checks.
   - Add regression tests and a browser smoke check.

## Test and Verification Plan

- Unit-test action schema validation for allowed and rejected plans.
- Unit-test YAML compose edits against sample compose input.
- Unit-test workflow snapshot and restore behavior.
- Route-test `/agent/health`, `/agent/context`, `/agent/dry-run`, and `/agent/apply`.
- Browser-smoke the side panel loads through `/extensions`.
- Verify a safe graph edit on a test workflow.
- Verify dry-run hash enforcement prevents applying a changed plan.
- Verify compose dry-run generates a readable diff before any service restart.
- Verify custom-node disable uses reversible state before any delete path is allowed.

## Design Decisions Already Made

- Use an in-ComfyUI custom node extension as the first integration layer.
- Do not start from a full ComfyUI frontend fork unless the extension layer blocks required UX.
- Do not use a browser visual companion for design comparison.
- Target Windows browser use first.
- Build C/max operational capability, including custom-node and compose/service operations, with explicit approval gates.
- Keep sudo actions human-only.

## Open Risks

- ComfyUI frontend APIs can change, so graph manipulation code should be isolated behind a small adapter.
- ComfyUI-Manager APIs may not cover every custom-node operation, so fallback operations must stay constrained and auditable.
- Local LLMs may compete with ComfyUI for GB10 unified memory, so provider selection must be visible and configurable.
- Compose/service actions can interrupt active renders, so the agent must detect queue/running state before restart.
- A very broad first implementation could sprawl. The implementation plan should build capability in phases while preserving the final C/max target.

## Acceptance Criteria

The work is successful when a Windows user can open the Spark ComfyUI page and use the Agent Workbench to:

- Ask natural-language questions about the current graph and environment.
- Preview and apply a graph/workflow change.
- Diagnose a missing custom-node problem and install or disable a node with confirmation.
- Preview a compose edit, apply it with Docker compose, restart ComfyUI if needed, and verify service health.
- See exactly what changed and roll back supported file, compose, or node-state changes.
- Trust that sudo-only host operations are explained but not executed by the agent.

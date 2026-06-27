import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

from aiohttp import web

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench import routes as agent_routes
from agent_workbench.health import CORE_CAPABILITIES, build_health_payload

def test_health_payload_names_core_capabilities(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WORKBENCH_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WORKBENCH_LLM_ENDPOINT", raising=False)

    payload = build_health_payload()

    assert payload["ok"] is True
    assert payload["name"] == "ComfyUI Agent Workbench"
    assert payload["version"] == "0.1.0"
    assert "graph.edit" in payload["capabilities"]
    assert "runtime.interrupt" in payload["capabilities"]
    assert "custom_node.manage" in payload["capabilities"]
    assert "service.compose" in payload["capabilities"]
    assert "agent.chat" in payload["capabilities"]
    assert "agent.codex_cli" in payload["capabilities"]
    assert "agent.tool_planning" in payload["capabilities"]
    assert payload["sudo_policy"] == "print_only"
    assert payload["llm"]["configured"] is False

def test_health_payload_capabilities_are_isolated_from_module_constant():
    payload = build_health_payload()

    assert payload["capabilities"] is not CORE_CAPABILITIES
    payload["capabilities"].append("mutated")
    assert "mutated" not in build_health_payload()["capabilities"]

def test_register_routes_adds_agent_health_get_route():
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        matches = [
            route
            for route in app.router.routes()
            if route.method == "GET" and route.resource.canonical == "/agent/health"
        ]

        assert len(matches) == 1
        response = asyncio.run(matches[0].handler(None))
        assert json.loads(response.text)["ok"] is True
    finally:
        agent_routes._REGISTERED = False

def test_custom_node_entrypoint_exposes_frontend_extension(monkeypatch):
    module_name = "agent_workbench_custom_node_entrypoint"
    for loaded_name in list(sys.modules):
        if loaded_name == module_name or loaded_name.startswith(f"{module_name}."):
            del sys.modules[loaded_name]

    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())
    fake_server = types.ModuleType("server")
    fake_server.PromptServer = types.SimpleNamespace(instance=fake_prompt_server)
    monkeypatch.setitem(sys.modules, "server", fake_server)

    spec = importlib.util.spec_from_file_location(
        module_name,
        AGENT_ROOT / "__init__.py",
        submodule_search_locations=[str(AGENT_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    assert module.NODE_CLASS_MAPPINGS == {}
    assert module.NODE_DISPLAY_NAME_MAPPINGS == {}
    assert module.WEB_DIRECTORY == "js"

    web_root = AGENT_ROOT / module.WEB_DIRECTORY
    assert (web_root / "agent-workbench.js").is_file()
    assert (web_root / "agent-workbench.css").is_file()

def test_frontend_loads_stylesheet_without_css_module_import():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert 'import "./agent-workbench.css";' not in script
    assert "/extensions/ComfyUI-AgentWorkbench/agent-workbench.css" in script
    assert 'document.createElement("link")' in script

def test_frontend_panel_creation_is_idempotent():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert 'const WORKBENCH_PANEL_ID = "agent-workbench-panel";' in script
    assert "document.getElementById(WORKBENCH_PANEL_ID)" in script

def test_frontend_registers_workbench_as_comfyui_sidebar_tab():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "app.extensionManager.registerSidebarTab" in script
    assert 'id: "agent-workbench-sidebar"' in script
    assert 'title: "Agent Workbench"' in script
    assert 'type: "custom"' in script
    assert "render: (container)" in script
    assert "createWorkbenchPanel(container)" in script
    assert "createFloatingWorkbenchPanel()" in script
    assert "if (!registerWorkbenchSidebar())" in script
    assert "document.body.appendChild(panel)" not in script

def test_frontend_exposes_plan_first_operator_controls():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()
    renderer = (AGENT_ROOT / "js" / "chat-render.mjs").read_text()
    state_module = (AGENT_ROOT / "js" / "workbench-state.mjs").read_text()

    assert "/agent/context" in script
    assert "/agent/message" in script
    assert "/agent/apply" in script
    assert "/agent/apply-deferred" in script
    assert "currentGraphSnapshot" in script
    assert "chat-store.mjs" in script
    assert "attachments.mjs" in script
    assert "chat-render.mjs" in script
    assert "agent-workbench-thread" in script
    assert "agent-workbench-file" in script
    assert "agent-workbench-send" in script
    assert "agent-workbench-upload" in script
    assert "agent-workbench-clear" in script
    assert 'aria-label="Send message to Agent"' in script
    assert ">发送<" in script
    assert ">上传<" in script
    assert "historyForRequest" in script
    assert "attachmentsForRequest" in script
    assert "允许执行" in renderer
    assert "确认允许高风险操作" in renderer
    assert 'input.addEventListener("keydown"' in script
    assert 'event.key === "Enter"' in script
    assert "event.ctrlKey || event.metaKey" in script
    assert "user_cancelled" in state_module
    assert "requires_confirmation" in state_module
    assert "plan.confirmed" in state_module


def test_frontend_exposes_windows_manual_smoke_manifest():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "/agent/smoke_manifest" in script
    assert "agent-workbench-smoke" in script
    assert "自检" in script
    assert "上下文" in script


def test_frontend_graph_snapshot_includes_slots_for_connection_planning():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "slotRows" in script
    assert "mode: node.mode" in script
    assert "color: node.color" in script
    assert "bgcolor: node.bgcolor" in script
    assert "inputs: slotRows(node.inputs)" in script
    assert "outputs: slotRows(node.outputs)" in script
    assert "type: slot.type" in script


def test_frontend_graph_snapshot_includes_registered_node_types_for_add_planning():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "MAX_NODE_TYPES" in script
    assert "MAX_NODE_TYPE_INPUTS" in script
    assert "nodeTypeInputs(" in script
    assert "nodeTypeOutputs(" in script
    assert "registeredNodeTypes()" in script
    assert "globalThis.LiteGraph?.registered_node_types" in script
    assert "nodeClass?.nodeData" in script
    assert "input_order" in script
    assert "output_name" in script
    assert "node_types: registeredNodeTypes()" in script


def test_frontend_graph_snapshot_collects_visible_ui_errors_for_agent_context():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "currentUiErrors()" in script
    assert "collectDomErrorText" in script
    assert "nodeErrorRows" in script
    assert "ui_errors: currentUiErrors()" in script
    assert "Node is marked red in the current canvas." in script


def test_frontend_graph_snapshot_includes_manager_node_metadata_for_missing_nodes():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "nodeProperties(" in script
    assert "properties: nodeProperties(node.properties)" in script
    assert "cnr_id" in script
    assert "aux_id" in script


def test_frontend_styles_plan_apply_and_confirmation_states():
    stylesheet = (AGENT_ROOT / "js" / "agent-workbench.css").read_text()

    assert ".agent-workbench-actions" in stylesheet
    assert "#agent-workbench-panel button:disabled" in stylesheet
    assert ".agent-workbench-tool-card" in stylesheet
    assert ".agent-workbench-tool-confirm" in stylesheet
    assert ".agent-workbench-tool-allow:not(:disabled)" in stylesheet
    assert ".agent-workbench-tool-cancel:not(:disabled)" in stylesheet


def test_frontend_wires_graph_actions_after_server_approval():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()
    frontend_requests = (AGENT_ROOT / "js" / "frontend-requests.mjs").read_text()
    graph_actions = (AGENT_ROOT / "js" / "graph-actions.js").read_text()

    assert 'import { applyGraphActions } from "./graph-actions.js";' in script
    assert 'import { executeFrontendRequest } from "./frontend-requests.mjs";' in script
    assert "if (result.ok)" in script
    assert "result.browser_applied = applyGraphActions(dryRun.plan.actions)" in script
    assert "executeBrowserRuntimeActions(dryRun.plan.actions)" in script
    assert "Comfy.QueuePrompt" in script
    assert "Comfy.QueuePromptFront" in script
    assert "browser_error" in script
    assert "executeFrontendRequest" in script
    assert "manager_request" in script
    assert "http_request" in script
    assert "request.start_queue === true" in frontend_requests
    assert 'fetchApi("/manager/queue/start"' in frontend_requests
    assert "request.response_filter" in frontend_requests
    assert "result.filtered" in frontend_requests
    assert "response_json" in frontend_requests
    assert "deferred_server_actions" in script
    assert "action_index" in script
    assert 'action.type === "graph.set_widget"' in graph_actions
    assert 'action.type === "graph.add_node"' in graph_actions
    assert 'action.type === "graph.connect"' in graph_actions
    assert 'action.type === "graph.delete_node"' in graph_actions
    assert 'action.type === "graph.duplicate_node"' in graph_actions
    assert 'action.type === "graph.set_color"' in graph_actions
    assert 'action.type === "graph.set_mode"' in graph_actions
    assert 'action.type === "graph.set_title"' in graph_actions
    assert 'action.type === "graph.set_position"' in graph_actions
    assert 'action.type === "graph.disconnect"' in graph_actions
    assert 'action.type === "graph.select_node"' in graph_actions
    assert 'action.type === "graph.select_nodes"' in graph_actions
    assert "app.graph.getNodeById" in graph_actions
    assert "globalThis.LiteGraph.createNode" in graph_actions
    assert ".selectNode(" in graph_actions
    assert ".centerOnNode(" in graph_actions
    assert ".connect(" in graph_actions
    assert ".disconnectInput(" in graph_actions
    assert "disconnectGraphLinks(" in graph_actions
    assert "action.payload.node_id" in graph_actions
    assert "rememberNodeRef(" in graph_actions
    assert "target_node_ref" in graph_actions
    assert "payload.target_slot === undefined" in graph_actions
    assert "matchingLinks(" in graph_actions
    assert "graph.remove(node)" in graph_actions
    assert "cloneGraphNode(" in graph_actions
    assert "node.selected = true" in graph_actions
    assert "selectGraphNodes(" in graph_actions
    assert "node.color =" in graph_actions
    assert "node.mode =" in graph_actions
    assert "node.title =" in graph_actions
    assert "node.pos =" in graph_actions
    assert "globalThis.LiteGraph.BYPASS" in graph_actions
    assert "app.graph.setDirtyCanvas(true, true)" in graph_actions


def test_frontend_disables_apply_while_request_is_in_flight():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "const runningApplies = new Set()" in script
    assert "runningApplies.has(message.id)" in script
    assert "runningApplies.add(message.id)" in script
    assert 'tool_state: { status: "running" }' in script
    assert "runningApplies.delete(message.id)" in script


def test_frontend_restores_apply_state_when_apply_request_throws():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    apply_handler = script[script.index("async function applyToolMessage(message, confirmed) {"):]
    assert "const dryRun = dryRunFromResponse(message?.response);" in apply_handler
    assert "try {\n      const result = await applyDryRun(dryRun, confirmed);" in apply_handler
    assert "catch (error) {" in apply_handler
    assert "finally {\n      runningApplies.delete(message.id);\n      render();\n    }" in apply_handler


def test_browser_smoke_script_covers_live_ui_flow_safely():
    script_path = AGENT_ROOT / "tools" / "browser-smoke.mjs"

    assert script_path.is_file()
    script = script_path.read_text()

    assert "AGENT_WORKBENCH_URL" in script
    assert "CHROMIUM_BIN" in script
    assert "WebSocket" in script
    assert "agent-workbench-panel" in script
    assert "agent-workbench-smoke" in script
    assert "agent-workbench-context" in script
    assert "agent-workbench-plan" in script
    assert "agent-workbench-confirm" in script
    assert "agent-workbench-cancel" in script
    assert "agent-workbench-apply" in script
    assert "openWorkbenchSidebar" in script
    assert "toggleSidebarTab" in script
    assert "agent-workbench-sidebar" in script
    assert "waitForGraphNodeCount" in script
    assert "payload?.graph?.node_count > 0" in script
    assert "runSmokeManifestFlow" in script
    assert "smoke_manifest" in script
    assert "/agent/smoke_manifest" in script
    assert "添加一个 Save Image 节点" in script
    assert "添加 Video Combine 节点，loop count 改成 2" in script
    assert "registered_node_types" in script
    assert "graph.add_node" in script
    assert "关 swap 防止卡死" in script
    assert "executed !== false" in script
    assert "findEditablePromptNode" in script
    assert "CLIPTextEncode" in script
    assert "agent live smoke prompt" in script
    assert "browser_applied" in script
    assert "restorePromptNode" in script
    assert "widget.value = originalValue" in script
    assert "runCopySamplerSeedPlanFlow" in script
    assert "Base KSampler 的种子复制到 Refiner KSampler" in script
    assert "copy_sampler_seed_plan" in script
    assert "runCopySamplerSettingsPlanFlow" in script
    assert "把 Base KSampler 的设置复制到 Refiner KSampler" in script
    assert "copy_sampler_settings_plan" in script
    assert "runServiceLogsPlanFlow" in script
    assert "查看 ComfyUI 最近日志" in script
    assert "service_logs_plan" in script
    assert "finally" in script
    assert "missing_node_plan" in script
    assert "安装当前工作流缺失节点然后重启 ComfyUI" in script
    assert "ComfyUI-Impact-Pack" in script
    assert "model_install_plan" in script
    assert "安装模型 https://example.com/models/hero.safetensors 到 checkpoints" in script
    assert "hero.safetensors" in script
    assert "model_widget_use_plan" in script
    assert "把底模用 juggernautXL.safetensors" in script
    assert "让 LoRA 用 detail.safetensors" in script
    assert "让 LoRA 用 detail.safetensors，强度 0.7" in script
    assert "参考图用 input/pose.png" in script
    assert "保存图片用 renders/shot-a 作为文件名前缀" in script
    assert "manager_queue_status_plan" in script
    assert "查看 Manager 安装队列状态" in script
    assert "manager.queue_status" in script
    assert "manager_queue_control_plan" in script
    assert "开始 Manager 安装队列" in script
    assert "清空 Manager 安装队列" in script
    assert "manager.queue_start" in script
    assert "manager.queue_reset" in script
    assert "custom_node_read_plan" in script
    assert "列出已安装插件" in script
    assert "搜索 custom node Impact Pack" in script
    assert "custom_node.list" in script
    assert "custom_node.search" in script
    assert "frontend_requests" in script
    assert "filtered" in script
    assert "custom_node_state_synonym_plan" in script
    assert "把 ComfyUI-Impact-Pack 插件关掉然后重启服务" in script
    assert "打开 ComfyUI-Impact-Pack 插件并重启" in script
    assert "custom_node_update_installed_plan" in script
    assert "更新已安装插件然后重启服务" in script
    assert "sampler_scheduler_plan" in script
    assert "采样方法改成 dpmpp_2m，调度方式改成 karras" in script
    assert "sampler_relative_plan" in script
    assert "把所有 KSampler 的步数加 5" in script
    assert "把所有 KSampler 的 denoise 降到 0.4" in script
    assert "sampler_multiplier_plan" in script
    assert "把所有 KSampler 的 cfg 减半" in script
    assert "把所有 KSampler 的步数翻倍" in script
    assert "sampler_natural_phrase_plan" in script
    assert "让 KSampler 用 30 步" in script
    assert "sampler_compact_use_plan" in script
    assert "让 KSampler 用 30 步，CFG 7.5" in script
    assert "sampler_compact_string_plan" in script
    assert "KSampler 采样方法 dpmpp_2m，调度方式 karras" in script
    assert "ordinal_node_plan" in script
    assert "把第二个 KSampler 的 cfg 改成 4" in script
    assert "禁用第二个 KSampler 节点" in script
    assert "把第一个 KSampler 移到第二个 KSampler 右边" in script
    assert "lora_insert_plan" in script
    assert "把 LoRA 插到 Checkpoint 和 KSampler 之间" in script
    assert "在 Checkpoint 和 KSampler 之间插入 LoRA 节点，LoRA 用 detail.safetensors，强度 0.7" in script
    assert "relative_position_plan" in script
    assert "把 Base KSampler 移到 Refiner KSampler 右边" in script
    assert "把 Base KSampler 放到 Refiner KSampler 下面" in script
    assert "auto_layout_plan" in script
    assert "整理这个工作流" in script
    assert "collapsed_node_plan" in script
    assert "折叠这个节点" in script
    assert "展开所有 KSampler 节点" in script
    assert "graph.set_collapsed" in script
    assert "node_mode_plan" in script
    assert "旁路这个节点" in script
    assert "禁用 KSampler 节点" in script
    assert "启用 12 号节点" in script
    assert "graph.set_mode" in script
    assert "downstream_mode_plan" in script
    assert "禁用 KSampler 后面的节点" in script
    assert "downstream_delete_plan" in script
    assert "删除 KSampler 后面的节点" in script
    assert "upstream_select_plan" in script
    assert "选中这个节点上游节点" in script
    assert "upstream_duplicate_plan" in script
    assert "复制这个节点上游节点" in script
    assert "downstream_move_plan" in script
    assert "把 KSampler 后面的节点往右移动 100" in script
    assert "upstream_move_plan" in script
    assert "把这个节点上游节点往上移动 40" in script
    assert "node_size_plan" in script
    assert "把这个节点框大小改成 420x260" in script
    assert "resize KSampler node box to 360 x 180" in script
    assert "graph.set_size" in script
    assert "prompt_remove_plan" in script
    assert "把正向提示词里的 watermark 去掉" in script
    assert "prompt:" in script
    assert "ipadapter_timing_plan" in script
    assert "IPAdapter 的权重改成 0.7，开始时间改成 0.1，结束时间改成 0.8" in script
    assert "controlnet_natural_timing_plan" in script
    assert "ControlNet 强度 0.75，开始 0.1，结束 0.8" in script
    assert "ipadapter_model_timing_plan" in script
    assert "IPAdapter 用 plus-face.safetensors，权重 0.7，开始时间 0.1，结束时间 0.8" in script
    assert "latent_size_batch_plan" in script
    assert "Empty Latent 设成 1024x576，batch 4" in script
    assert "video_combine_loop_plan" in script
    assert "Video Combine 的循环次数改成 2，帧率改成 24，保存前缀改成 renders/shot-a" in script

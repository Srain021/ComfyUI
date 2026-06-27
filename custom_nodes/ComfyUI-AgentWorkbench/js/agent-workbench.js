import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  attachmentFromFile,
  attachmentsForRequest,
  filesFromDropEvent,
  filesFromPasteEvent,
} from "./attachments.mjs";
import { createChatStore, historyForRequest } from "./chat-store.mjs";
import {
  dryRunFromResponse,
  renderChatTimeline,
  responseText,
  toolCardsFromResponse,
} from "./chat-render.mjs";
import { executeFrontendRequest } from "./frontend-requests.mjs";
import { applyGraphActions } from "./graph-actions.js";
import {
  buildApplyRequest,
  planNeedsBrowserWorkflow,
} from "./workbench-state.mjs";

const WORKBENCH_STYLESHEET_ID = "agent-workbench-stylesheet";
const WORKBENCH_STYLESHEET_HREF = "/extensions/ComfyUI-AgentWorkbench/agent-workbench.css";
const WORKBENCH_PANEL_ID = "agent-workbench-panel";
const WORKBENCH_SIDEBAR_ID = "agent-workbench-sidebar";
const CHAT_STORE_KEY = "ComfyUI.AgentWorkbench.chat.v1";
const MAX_GRAPH_NODES = 500;
const MAX_GRAPH_LINKS = 1000;
const MAX_NODE_TYPES = 1000;
const MAX_NODE_TYPE_INPUTS = 128;
const MAX_NODE_SLOTS = 64;
const MAX_UI_ERRORS = 20;
const MAX_UI_ERROR_TEXT_LENGTH = 800;
const MAX_WIDGET_VALUE_LENGTH = 500;
const MAX_NODE_PROPERTY_VALUE_LENGTH = 200;
const MANAGER_NODE_PROPERTY_KEYS = ["cnr_id", "aux_id", "ver"];
const NODE_ERROR_FIELDS = [
  "errors",
  "error",
  "last_error",
  "validation_error",
  "validation_errors",
  "execution_error",
  "exception",
];
const DOM_ERROR_SELECTORS = [
  ".p-toast-message-error",
  ".p-toast-message-warn",
  ".p-message-error",
  ".p-message-warn",
  "[role='alert']",
  "[aria-live='assertive']",
  "[data-testid*='error' i]",
  "[data-testid*='warn' i]",
  "[class*='error' i]",
  "[class*='warn' i]",
];

function loadWorkbenchStylesheet() {
  if (document.getElementById(WORKBENCH_STYLESHEET_ID)) {
    return;
  }

  const link = document.createElement("link");
  link.id = WORKBENCH_STYLESHEET_ID;
  link.rel = "stylesheet";
  link.href = WORKBENCH_STYLESHEET_HREF;
  document.head.appendChild(link);
}

function boundedValue(value) {
  if (typeof value === "string" && value.length > MAX_WIDGET_VALUE_LENGTH) {
    return `${value.slice(0, MAX_WIDGET_VALUE_LENGTH)}...`;
  }
  return value;
}

function boundedErrorText(value) {
  let text = "";
  if (typeof value === "string") {
    text = value;
  } else if (value instanceof Error) {
    text = value.message || value.stack || "";
  } else if (value !== undefined && value !== null) {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  }
  text = text.replace(/\s+/g, " ").trim();
  if (text.length > MAX_UI_ERROR_TEXT_LENGTH) {
    return `${text.slice(0, MAX_UI_ERROR_TEXT_LENGTH)}...`;
  }
  return text;
}

function nodeProperties(properties) {
  if (!properties || typeof properties !== "object") {
    return undefined;
  }
  const row = {};
  for (const key of MANAGER_NODE_PROPERTY_KEYS) {
    const value = properties[key];
    if (typeof value !== "string" || !value) {
      continue;
    }
    row[key] = value.length > MAX_NODE_PROPERTY_VALUE_LENGTH
      ? `${value.slice(0, MAX_NODE_PROPERTY_VALUE_LENGTH)}...`
      : value;
  }
  return Object.keys(row).length ? row : undefined;
}

function slotRows(slots) {
  return (slots || []).slice(0, MAX_NODE_SLOTS).map((slot) => ({
    name: slot.name,
    type: slot.type,
  }));
}

function pushUiError(rows, seen, row) {
  const text = boundedErrorText(row.text);
  if (!text) {
    return;
  }
  const normalized = { ...row, text };
  const key = [
    normalized.source,
    normalized.node_id,
    normalized.node_type,
    normalized.title,
    normalized.text,
  ].join("|");
  if (seen.has(key)) {
    return;
  }
  seen.add(key);
  rows.push(normalized);
}

function visibleElementText(element) {
  if (!(element instanceof HTMLElement)) {
    return "";
  }
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") {
    return "";
  }
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 && rect.height <= 0) {
    return "";
  }
  return boundedErrorText(element.innerText || element.textContent || "");
}

function domErrorSource(element) {
  const signature = `${element.id || ""} ${element.className || ""}`.toLowerCase();
  if (signature.includes("toast")) {
    return "toast";
  }
  if (element.getAttribute("role") === "alert") {
    return "alert";
  }
  return "dom";
}

function domErrorSeverity(element) {
  const signature = `${element.id || ""} ${element.className || ""}`.toLowerCase();
  return signature.includes("warn") ? "warning" : "error";
}

function collectDomErrorText() {
  const rows = [];
  const seen = new Set();
  for (const selector of DOM_ERROR_SELECTORS) {
    let elements = [];
    try {
      elements = Array.from(document.querySelectorAll(selector));
    } catch {
      continue;
    }
    for (const element of elements) {
      pushUiError(rows, seen, {
        source: domErrorSource(element),
        severity: domErrorSeverity(element),
        text: visibleElementText(element),
      });
      if (rows.length >= MAX_UI_ERRORS) {
        return rows;
      }
    }
  }
  return rows;
}

function parseCssColor(value) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  const text = value.trim().toLowerCase();
  if (text.includes("red")) {
    return { r: 255, g: 0, b: 0 };
  }
  const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const raw = hex[1].length === 3
      ? hex[1].split("").map((char) => `${char}${char}`).join("")
      : hex[1];
    return {
      r: parseInt(raw.slice(0, 2), 16),
      g: parseInt(raw.slice(2, 4), 16),
      b: parseInt(raw.slice(4, 6), 16),
    };
  }
  const rgb = text.match(/^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
  if (rgb) {
    return {
      r: Number(rgb[1]),
      g: Number(rgb[2]),
      b: Number(rgb[3]),
    };
  }
  return null;
}

function isRedishColor(value) {
  const color = parseCssColor(value);
  if (!color) {
    return false;
  }
  return color.r >= 70 && color.r > color.g * 1.3 && color.r > color.b * 1.2;
}

function isRedNode(node) {
  return isRedishColor(node?.color) || isRedishColor(node?.bgcolor);
}

function errorTextsFromValue(value, depth = 0) {
  if (depth > 3 || value === undefined || value === null) {
    return [];
  }
  if (typeof value === "string") {
    const text = boundedErrorText(value);
    return text ? [text] : [];
  }
  if (value instanceof Error) {
    const text = boundedErrorText(value);
    return text ? [text] : [];
  }
  if (Array.isArray(value)) {
    return value.slice(0, 12).flatMap((item) => errorTextsFromValue(item, depth + 1));
  }
  if (typeof value === "object") {
    return Object.entries(value)
      .slice(0, 16)
      .flatMap(([key, child]) => {
        const lowerKey = key.toLowerCase();
        if (
          depth > 1
          && !["message", "text", "detail", "details", "error", "errors", "reason"].includes(lowerKey)
        ) {
          return [];
        }
        return errorTextsFromValue(child, depth + 1);
      });
  }
  return [];
}

function nodeErrorRows() {
  const rows = [];
  const seen = new Set();
  const nodes = app.graph?._nodes || [];
  for (const node of nodes.slice(0, MAX_GRAPH_NODES)) {
    const baseRow = {
      source: "node",
      severity: "error",
      node_id: node.id,
      node_type: node.type,
      title: node.title,
    };
    const texts = NODE_ERROR_FIELDS.flatMap((field) => errorTextsFromValue(node[field]));
    for (const text of texts) {
      pushUiError(rows, seen, { ...baseRow, text });
      if (rows.length >= MAX_UI_ERRORS) {
        return rows;
      }
    }
    if (!texts.length && isRedNode(node)) {
      pushUiError(rows, seen, {
        ...baseRow,
        text: "Node is marked red in the current canvas.",
      });
      if (rows.length >= MAX_UI_ERRORS) {
        return rows;
      }
    }
  }
  return rows;
}

function currentUiErrors() {
  const rows = [];
  const seen = new Set();
  for (const row of [...collectDomErrorText(), ...nodeErrorRows()]) {
    pushUiError(rows, seen, row);
    if (rows.length >= MAX_UI_ERRORS) {
      return rows;
    }
  }
  return rows;
}

function nodeInputType(inputSpec) {
  if (!Array.isArray(inputSpec) || !inputSpec.length) {
    return undefined;
  }
  if (Array.isArray(inputSpec[0])) {
    return "COMBO";
  }
  if (typeof inputSpec[0] === "string") {
    return inputSpec[0];
  }
  return undefined;
}

function nodeTypeInputs(nodeData) {
  const rows = [];
  const input = nodeData?.input || {};
  const inputOrder = nodeData?.input_order || {};
  for (const section of ["required", "optional"]) {
    const sectionInput = input[section] || {};
    const names = Array.isArray(inputOrder[section]) ? inputOrder[section] : Object.keys(sectionInput);
    for (const name of names) {
      if (typeof name !== "string" || !name) {
        continue;
      }
      const row = { name };
      const type = nodeInputType(sectionInput[name]);
      if (type) {
        row.type = type;
      }
      rows.push(row);
      if (rows.length >= MAX_NODE_TYPE_INPUTS) {
        return rows;
      }
    }
  }
  return rows;
}

function nodeTypeOutputs(nodeData) {
  const outputTypes = Array.isArray(nodeData?.output) ? nodeData.output : [];
  const outputNames = Array.isArray(nodeData?.output_name) ? nodeData.output_name : [];
  return outputTypes.slice(0, MAX_NODE_TYPE_INPUTS).map((type, index) => {
    const name = typeof outputNames[index] === "string" && outputNames[index]
      ? outputNames[index]
      : type;
    const row = { name };
    if (typeof type === "string" && type) {
      row.type = type;
    }
    return row;
  });
}

function registeredNodeTypes() {
  const registered = globalThis.LiteGraph?.registered_node_types || {};
  return Object.entries(registered)
    .slice(0, MAX_NODE_TYPES)
    .filter(([type]) => typeof type === "string" && type)
    .map(([type, nodeClass]) => {
      const title = nodeClass?.title || nodeClass?.prototype?.title || type;
      const category = nodeClass?.category || nodeClass?.prototype?.category;
      const inputs = nodeTypeInputs(nodeClass?.nodeData);
      const outputs = nodeTypeOutputs(nodeClass?.nodeData);
      const row = { type, title };
      if (category) {
        row.category = category;
      }
      if (inputs.length) {
        row.inputs = inputs;
      }
      if (outputs.length) {
        row.outputs = outputs;
      }
      return row;
    });
}

function currentGraphSnapshot() {
  const graph = app.graph;
  const links = graph?.links || [];
  const linkRows = Array.isArray(links) ? links : Object.values(links);
  return {
    nodes: (graph?._nodes || []).slice(0, MAX_GRAPH_NODES).map((node) => ({
      id: node.id,
      type: node.type,
      title: node.title,
      mode: node.mode,
      color: node.color,
      bgcolor: node.bgcolor,
      pos: node.pos,
      selected: Boolean(node.selected),
      properties: nodeProperties(node.properties),
      widgets: (node.widgets || []).map((widget) => ({
        name: widget.name,
        value: boundedValue(widget.value),
      })),
      inputs: slotRows(node.inputs),
      outputs: slotRows(node.outputs),
    })),
    links: linkRows.slice(0, MAX_GRAPH_LINKS).filter(Boolean).map((link) => ({
      id: link.id,
      origin_id: link.origin_id,
      origin_slot: link.origin_slot,
      target_id: link.target_id,
      target_slot: link.target_slot,
      type: link.type,
    })),
    node_types: registeredNodeTypes(),
    ui_errors: currentUiErrors(),
  };
}

function currentWorkflowSnapshot() {
  if (typeof app.graph?.serialize === "function") {
    return app.graph.serialize();
  }
  return currentGraphSnapshot();
}

async function postJson(path, body) {
  const response = await api.fetchApi(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({ ok: false, error: "invalid_json_response" }));
  if (!response.ok && typeof payload === "object" && payload !== null) {
    payload.http_status = response.status;
  }
  return payload;
}

async function getJson(path) {
  const response = await api.fetchApi(path, { method: "GET" });
  const payload = await response.json().catch(() => ({ ok: false, error: "invalid_json_response" }));
  if (!response.ok && typeof payload === "object" && payload !== null) {
    payload.http_status = response.status;
  }
  return payload;
}

function commandStore() {
  const candidates = [
    app.extensionManager?.commandStore,
    app.commandStore,
    globalThis.comfyAPI?.commandStore,
    globalThis.comfyAPI?.stores?.commandStore,
  ];
  return candidates.find((candidate) => typeof candidate?.execute === "function");
}

async function executeComfyCommand(commandId) {
  const store = commandStore();
  if (store) {
    const result = await store.execute(commandId, {
      metadata: {
        subscribe_to_run: false,
        trigger_source: "agent_workbench",
      },
    });
    return { command: commandId, via: "commandStore", result: result ?? null };
  }
  const queueButton = document.querySelector('[data-testid="queue-button"]');
  if (commandId === "Comfy.QueuePrompt" && queueButton instanceof HTMLElement) {
    queueButton.click();
    return { command: commandId, via: "queue-button" };
  }
  throw new Error(`Comfy command store unavailable for ${commandId}`);
}

async function executeBrowserRuntimeAction(action) {
  if (action.type !== "runtime.queue_prompt") {
    return null;
  }
  const commandId = action.payload?.front === true ? "Comfy.QueuePromptFront" : "Comfy.QueuePrompt";
  const result = await executeComfyCommand(commandId);
  return { type: action.type, front: action.payload?.front === true, ...result };
}

async function executeBrowserRuntimeActions(actions) {
  const rows = [];
  for (const action of actions) {
    if (action.type === "runtime.queue_prompt") {
      rows.push(await executeBrowserRuntimeAction(action));
    }
  }
  return rows;
}

function createWorkbenchPanel(container) {
  const host = container || document.body;
  const existing = document.getElementById(WORKBENCH_PANEL_ID);
  if (existing) {
    existing.classList.remove("agent-workbench-floating");
    host.append(existing);
    return existing;
  }

  const panel = document.createElement("section");
  panel.id = WORKBENCH_PANEL_ID;
  panel.innerHTML = `
    <header>
      <strong>Agent Workbench</strong>
      <div class="agent-workbench-header-actions">
        <button id="agent-workbench-smoke" title="Show Windows browser smoke checklist">自检</button>
        <button id="agent-workbench-context" title="Refresh context">上下文</button>
      </div>
    </header>
    <section id="agent-workbench-thread" aria-live="polite"></section>
    <section class="agent-workbench-composer">
      <div id="agent-workbench-attachments" aria-live="polite"></div>
      <textarea id="agent-workbench-input" placeholder="告诉 Agent 你要怎么改节点、插件或服务"></textarea>
      <input id="agent-workbench-file" type="file" multiple accept="image/*,.txt,.md,.json,.csv,.yaml,.yml,.log,.py,.js,.ts,.css,.html" hidden />
      <div class="agent-workbench-actions">
        <button id="agent-workbench-upload" type="button" aria-label="Upload files">上传</button>
        <button id="agent-workbench-send" type="button" aria-label="Send message to Agent">发送</button>
        <button id="agent-workbench-clear" type="button" aria-label="Clear chat history">清空</button>
      </div>
    </section>
  `;
  host.append(panel);

  const store = createChatStore({ key: CHAT_STORE_KEY });
  const thread = panel.querySelector("#agent-workbench-thread");
  const input = panel.querySelector("#agent-workbench-input");
  const sendButton = panel.querySelector("#agent-workbench-send");
  const uploadButton = panel.querySelector("#agent-workbench-upload");
  const clearButton = panel.querySelector("#agent-workbench-clear");
  const fileInput = panel.querySelector("#agent-workbench-file");
  const attachmentsTray = panel.querySelector("#agent-workbench-attachments");
  let pendingAttachments = [];
  let requestInFlight = false;
  const runningApplies = new Set();

  function isActionableDryRun(response) {
    return toolCardsFromResponse(response).length > 0;
  }

  function renderPendingAttachments() {
    attachmentsTray.replaceChildren();
    if (!pendingAttachments.length) {
      attachmentsTray.hidden = true;
      return;
    }
    attachmentsTray.hidden = false;
    for (const attachment of pendingAttachments) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `agent-workbench-pending-attachment agent-workbench-attachment-${attachment.kind || "file"}`;
      chip.title = "移除附件";
      chip.textContent = attachment.name || attachment.kind || "attachment";
      chip.addEventListener("click", () => {
        pendingAttachments = pendingAttachments.filter((row) => row.id !== attachment.id);
        renderPendingAttachments();
      });
      attachmentsTray.append(chip);
    }
  }

  function render() {
    const messages = store.load();
    renderChatTimeline(thread, messages, {
      onApplyTool: applyToolMessage,
      onCancelTool: cancelToolMessage,
    });
  }

  function appendAssistantResponse(response, fallbackText = "") {
    return store.append({
      role: "assistant",
      text: responseText(response) || fallbackText,
      response,
      tool_state: isActionableDryRun(response) ? { status: "pending" } : undefined,
    });
  }

  async function applyDryRun(dryRun, confirmed) {
    const applyRequest = buildApplyRequest(
      dryRun,
      confirmed,
      currentWorkflowSnapshot(),
    );
    if (!applyRequest) {
      return { ok: false, error: "missing_plan" };
    }
    const plan = applyRequest.plan;
    const approvedHash = applyRequest.approved_hash;
    const result = await postJson("/agent/apply", applyRequest);
    if (result.ok) {
      try {
        result.browser_applied = applyGraphActions(dryRun.plan.actions);
        result.browser_runtime = await executeBrowserRuntimeActions(dryRun.plan.actions);
      } catch (error) {
        result.ok = false;
        result.browser_error = error instanceof Error ? error.message : String(error);
      }
    }
    if (result.ok) {
      try {
        result.frontend_requests = [];
        for (const applied of result.applied || []) {
          if (applied.manager_request) {
            result.frontend_requests.push(await executeFrontendRequest(applied.manager_request, api.fetchApi.bind(api)));
          }
          if (applied.http_request) {
            result.frontend_requests.push(await executeFrontendRequest({
              method: "POST",
              path: applied.http_request.path,
              json: applied.http_request.json,
            }, api.fetchApi.bind(api)));
          }
        }
      } catch (error) {
        result.ok = false;
        result.frontend_error = error instanceof Error ? error.message : String(error);
      }
    }
    if (result.ok) {
      try {
        result.deferred_server_actions = [];
        for (const applied of result.applied || []) {
          if (applied.deferred === true && Number.isInteger(applied.action_index)) {
            const deferredRequest = {
              plan,
              approved_hash: approvedHash,
              action_index: applied.action_index,
            };
            if (planNeedsBrowserWorkflow(plan)) {
              deferredRequest.browser_workflow = currentWorkflowSnapshot();
            }
            result.deferred_server_actions.push(await postJson("/agent/apply-deferred", deferredRequest));
          }
        }
      } catch (error) {
        result.ok = false;
        result.deferred_error = error instanceof Error ? error.message : String(error);
      }
    }
    return result;
  }

  async function applyToolMessage(message, confirmed) {
    const dryRun = dryRunFromResponse(message?.response);
    if (!message?.id || runningApplies.has(message.id) || !dryRun?.plan) {
      return;
    }
    runningApplies.add(message.id);
    store.update(message.id, { tool_state: { status: "running" } });
    render();
    try {
      const result = await applyDryRun(dryRun, confirmed);
      store.update(message.id, {
        tool_state: {
          status: result.ok ? "applied" : "failed",
          result,
        },
      });
      store.append({
        role: "tool",
        text: responseText(result),
        response: result,
      });
    } catch (error) {
      const result = {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      };
      store.update(message.id, { tool_state: { status: "failed", result } });
      store.append({
        role: "tool",
        text: responseText(result),
        response: result,
      });
    } finally {
      runningApplies.delete(message.id);
      render();
    }
  }

  function cancelToolMessage(message) {
    if (!message?.id) {
      return;
    }
    const result = { ok: false, error: "user_cancelled" };
    store.update(message.id, { tool_state: { status: "cancelled", result } });
    store.append({
      role: "tool",
      text: "已取消这个计划。",
      response: result,
    });
    render();
  }

  async function addFiles(files) {
    const rows = [];
    for (const file of Array.from(files || [])) {
      rows.push(await attachmentFromFile(file));
    }
    pendingAttachments = [...pendingAttachments, ...rows];
    renderPendingAttachments();
  }

  async function sendMessage() {
    if (requestInFlight) {
      return;
    }
    const message = input.value.trim();
    if (!message && !pendingAttachments.length) {
      return;
    }
    requestInFlight = true;
    sendButton.disabled = true;
    const attachments = pendingAttachments;
    const previousMessages = store.load();
    const outgoingText = message || "请查看我上传的附件。";
    store.append({ role: "user", text: outgoingText, attachments });
    input.value = "";
    pendingAttachments = [];
    renderPendingAttachments();
    const thinking = store.append({ role: "assistant", text: "正在思考..." });
    render();
    try {
      const response = await postJson("/agent/message", {
        message: outgoingText,
        graph: currentGraphSnapshot(),
        history: historyForRequest(previousMessages),
        attachments: attachmentsForRequest(attachments),
      });
      store.update(thinking.id, {
        text: responseText(response),
        response,
        tool_state: isActionableDryRun(response) ? { status: "pending" } : undefined,
      });
    } catch (error) {
      store.update(thinking.id, {
        text: error instanceof Error ? error.message : String(error),
        response: {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        },
      });
    } finally {
      requestInFlight = false;
      sendButton.disabled = false;
      render();
    }
  }

  panel.querySelector("#agent-workbench-context").addEventListener("click", async () => {
    const response = await postJson("/agent/context", { graph: currentGraphSnapshot() });
    store.append({
      role: "assistant",
      text: "已读取当前 ComfyUI 上下文。",
      response,
    });
    render();
  });

  panel.querySelector("#agent-workbench-smoke").addEventListener("click", async () => {
    appendAssistantResponse(await getJson("/agent/smoke_manifest"), "已加载自检清单。");
    render();
  });

  uploadButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    await addFiles(fileInput.files);
    fileInput.value = "";
  });
  sendButton.addEventListener("click", sendMessage);
  clearButton.addEventListener("click", () => {
    store.clear();
    appendAssistantResponse({
      ok: true,
      status: "assistant_reply",
      assistant: {
        title: "ComfyUI Codex Agent",
        message: "历史已清空。你可以继续发文字、图片，或让我操作当前工作流。",
      },
    });
    render();
  });

  input.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      sendMessage();
    }
  });
  input.addEventListener("paste", async (event) => {
    const files = filesFromPasteEvent(event);
    if (files.length) {
      event.preventDefault();
      await addFiles(files);
    }
  });
  panel.addEventListener("dragover", (event) => {
    if (event.dataTransfer?.types?.includes("Files")) {
      event.preventDefault();
      panel.classList.add("agent-workbench-dragover");
    }
  });
  panel.addEventListener("dragleave", () => {
    panel.classList.remove("agent-workbench-dragover");
  });
  panel.addEventListener("drop", async (event) => {
    const files = filesFromDropEvent(event);
    if (files.length) {
      event.preventDefault();
      panel.classList.remove("agent-workbench-dragover");
      await addFiles(files);
    }
  });

  if (!store.load().length) {
    appendAssistantResponse({
      ok: true,
      status: "assistant_reply",
      assistant: {
        title: "ComfyUI Codex Agent",
        message: "我在 ComfyUI 侧边栏里。你可以发自然语言、粘贴截图、上传文本或图片；需要改节点、安装/禁用 custom nodes、改 compose 或重启服务时，我会先给你计划卡片，等你允许再执行。",
      },
    });
  }
  renderPendingAttachments();
  render();

  return panel;
}

function registerWorkbenchSidebar() {
  if (typeof app.extensionManager?.registerSidebarTab !== "function") {
    return false;
  }
  app.extensionManager.registerSidebarTab({
    id: "agent-workbench-sidebar",
    title: "Agent Workbench",
    icon: "agent-workbench-sidebar-icon",
    type: "custom",
    render: (container) => {
      container.classList.add("agent-workbench-sidebar-host");
      createWorkbenchPanel(container);
    },
  });
  return true;
}

function createFloatingWorkbenchPanel() {
  const panel = createWorkbenchPanel(document.body);
  panel.classList.add("agent-workbench-floating");
  return panel;
}

app.registerExtension({
  name: "ComfyUI.AgentWorkbench",
  setup() {
    loadWorkbenchStylesheet();
    if (!registerWorkbenchSidebar()) {
      createFloatingWorkbenchPanel();
    }
  },
});

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { applyGraphActions } from "./graph-actions.js";

const WORKBENCH_STYLESHEET_ID = "agent-workbench-stylesheet";
const WORKBENCH_STYLESHEET_HREF = "/extensions/ComfyUI-AgentWorkbench/agent-workbench.css";
const MAX_GRAPH_NODES = 500;
const MAX_GRAPH_LINKS = 1000;
const MAX_NODE_SLOTS = 64;
const MAX_WIDGET_VALUE_LENGTH = 500;

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

function slotRows(slots) {
  return (slots || []).slice(0, MAX_NODE_SLOTS).map((slot) => ({
    name: slot.name,
    type: slot.type,
  }));
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
      pos: node.pos,
      selected: Boolean(node.selected),
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
  };
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

function renderJson(element, value) {
  element.textContent = JSON.stringify(value, null, 2);
}

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

function createWorkbenchPanel() {
  if (document.getElementById("agent-workbench-panel")) {
    return;
  }

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
      <button id="agent-workbench-cancel" hidden>Cancel</button>
    </div>
    <label class="agent-workbench-confirm" hidden>
      <input id="agent-workbench-confirm" type="checkbox" />
      <span>Confirm elevated action</span>
    </label>
    <pre id="agent-workbench-output">Ready.</pre>
  `;
  document.body.appendChild(panel);

  const input = panel.querySelector("#agent-workbench-input");
  const output = panel.querySelector("#agent-workbench-output");
  const applyButton = panel.querySelector("#agent-workbench-apply");
  const confirmRow = panel.querySelector(".agent-workbench-confirm");
  const confirmCheckbox = panel.querySelector("#agent-workbench-confirm");
  const cancelButton = panel.querySelector("#agent-workbench-cancel");
  let lastDryRun = null;

  function refreshApplyState() {
    const needsConfirmation = Boolean(lastDryRun?.plan?.requires_confirmation);
    confirmRow.hidden = !needsConfirmation;
    cancelButton.hidden = !needsConfirmation;
    applyButton.disabled = !lastDryRun?.plan || (needsConfirmation && !confirmCheckbox.checked);
  }

  panel.querySelector("#agent-workbench-context").addEventListener("click", async () => {
    applyButton.disabled = true;
    lastDryRun = null;
    confirmCheckbox.checked = false;
    refreshApplyState();
    renderJson(output, await postJson("/agent/context", { graph: currentGraphSnapshot() }));
  });

  panel.querySelector("#agent-workbench-plan").addEventListener("click", async () => {
    const message = input.value.trim() || "Inspect current ComfyUI context";
    confirmCheckbox.checked = false;
    lastDryRun = await postJson("/agent/plan", {
      message,
      graph: currentGraphSnapshot(),
    });
    refreshApplyState();
    renderJson(output, lastDryRun);
  });

  confirmCheckbox.addEventListener("change", refreshApplyState);

  cancelButton.addEventListener("click", () => {
    lastDryRun = null;
    confirmCheckbox.checked = false;
    refreshApplyState();
    renderJson(output, { ok: false, error: "user_cancelled" });
  });

  applyButton.addEventListener("click", async () => {
    if (!lastDryRun?.plan) {
      return;
    }
    const plan = { ...lastDryRun.plan };
    if (lastDryRun.plan.requires_confirmation) {
      plan.confirmed = confirmCheckbox.checked;
    }
    const result = await postJson("/agent/apply", {
      plan,
      approved_hash: lastDryRun.plan.plan_hash,
    });
    if (result.ok) {
      try {
        result.browser_applied = applyGraphActions(lastDryRun.plan.actions);
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
      } catch (error) {
        result.ok = false;
        result.frontend_error = error instanceof Error ? error.message : String(error);
      }
    }
    renderJson(output, result);
  });
}

app.registerExtension({
  name: "ComfyUI.AgentWorkbench",
  setup() {
    loadWorkbenchStylesheet();
    createWorkbenchPanel();
  },
});

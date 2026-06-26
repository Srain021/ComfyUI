#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const WORKBENCH_URL = process.env.AGENT_WORKBENCH_URL || "http://127.0.0.1:8188/";
const CDP_HOST = process.env.AGENT_WORKBENCH_CDP_HOST || "127.0.0.1";
const CDP_PORT = Number(process.env.AGENT_WORKBENCH_CDP_PORT || 9222);
const CDP_BASE_URL = `http://${CDP_HOST}:${CDP_PORT}`;
const SMOKE_MANIFEST_PATH = "/agent/smoke_manifest";
const SMOKE_PROMPT = `agent live smoke prompt ${new Date().toISOString()}`;
const CHROMIUM_ARGS = [
  "--headless=new",
  "--disable-gpu",
  "--no-sandbox",
  `--remote-debugging-address=${CDP_HOST}`,
  `--remote-debugging-port=${CDP_PORT}`,
];

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\"'\"'")}'`;
}

function chromiumCandidates() {
  const envBin = process.env.CHROMIUM_BIN;
  if (envBin) {
    return [envBin];
  }
  if (process.platform === "win32") {
    return ["chrome", "chrome.exe", "msedge", "msedge.exe"];
  }
  return ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge"];
}

function resolveChromiumBin() {
  const candidates = chromiumCandidates();
  for (const candidate of candidates) {
    if (candidate.includes("/") || candidate.includes("\\")) {
      return candidate;
    }
    const probe = process.platform === "win32"
      ? spawnSync("where", [candidate], { encoding: "utf8" })
      : spawnSync("sh", ["-lc", `command -v ${shellQuote(candidate)}`], { encoding: "utf8" });
    if (probe.status === 0 && probe.stdout.trim()) {
      return probe.stdout.trim().split(/\r?\n/)[0];
    }
  }
  throw new Error(`Chromium not found. Set CHROMIUM_BIN to one of: ${candidates.join(", ")}`);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${options.method || "GET"} ${url} failed with ${response.status}: ${text}`);
  }
  return JSON.parse(text);
}

async function cdpAvailable() {
  try {
    await fetchJson(`${CDP_BASE_URL}/json/version`);
    return true;
  } catch {
    return false;
  }
}

async function waitForCdp(timeoutMs = 15000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await cdpAvailable()) {
      return;
    }
    await sleep(250);
  }
  throw new Error(`Chrome DevTools endpoint did not start on ${CDP_BASE_URL}`);
}

function launchChromium() {
  const bin = resolveChromiumBin();
  const userDataDir = mkdtempSync(join(tmpdir(), "comfyui-agent-browser-smoke-"));
  const args = [...CHROMIUM_ARGS, `--user-data-dir=${userDataDir}`, WORKBENCH_URL];
  const child = spawn(bin, args, { stdio: ["ignore", "pipe", "pipe"] });
  const logTail = [];
  const remember = (chunk) => {
    logTail.push(String(chunk));
    while (logTail.join("").length > 8000) {
      logTail.shift();
    }
  };
  child.stdout.on("data", remember);
  child.stderr.on("data", remember);
  child.on("error", (error) => remember(error.message));
  return { child, bin, userDataDir, logTail };
}

async function ensureBrowser() {
  if (await cdpAvailable()) {
    return { launched: false, chromium: null };
  }
  const chromium = launchChromium();
  try {
    await waitForCdp();
  } catch (error) {
    chromium.child.kill("SIGTERM");
    rmSync(chromium.userDataDir, { recursive: true, force: true });
    const logs = chromium.logTail.join("").trim();
    throw new Error(`${error.message}${logs ? `\nChromium logs:\n${logs}` : ""}`);
  }
  return { launched: true, chromium };
}

async function decodeMessageData(data) {
  if (typeof data === "string") {
    return data;
  }
  if (Buffer.isBuffer(data)) {
    return data.toString("utf8");
  }
  if (data instanceof ArrayBuffer) {
    return Buffer.from(data).toString("utf8");
  }
  if (ArrayBuffer.isView(data)) {
    return Buffer.from(data.buffer, data.byteOffset, data.byteLength).toString("utf8");
  }
  if (data && typeof data.text === "function") {
    return await data.text();
  }
  return String(data);
}

class CdpClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.nextId = 0;
    this.pending = new Map();
    this.ws = null;
  }

  async connect() {
    assert(typeof WebSocket === "function", "Node.js global WebSocket is unavailable; use Node 22+");
    this.ws = new WebSocket(this.wsUrl);
    this.ws.addEventListener("message", async (event) => {
      const message = JSON.parse(await decodeMessageData(event.data));
      if (!message.id || !this.pending.has(message.id)) {
        return;
      }
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) {
        pending.reject(new Error(`${message.error.message}: ${JSON.stringify(message.error.data || {})}`));
        return;
      }
      pending.resolve(message.result || {});
    });
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
  }

  send(method, params = {}, timeoutMs = 10000) {
    const id = ++this.nextId;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP command timed out: ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

async function getOrCreatePageTarget() {
  const targets = await fetchJson(`${CDP_BASE_URL}/json/list`);
  const pageTarget = targets.find((target) => (
    target.type === "page"
    && target.webSocketDebuggerUrl
    && String(target.url || "").startsWith(WORKBENCH_URL)
  )) || targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
  if (pageTarget) {
    return pageTarget;
  }
  try {
    return await fetchJson(`${CDP_BASE_URL}/json/new?${encodeURIComponent(WORKBENCH_URL)}`, { method: "PUT" });
  } catch {
    return fetchJson(`${CDP_BASE_URL}/json/new?${encodeURIComponent(WORKBENCH_URL)}`);
  }
}

async function evaluateExpression(client, expression) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (result.exceptionDetails) {
    const details = result.exceptionDetails;
    const text = details.exception?.description || details.text || "Runtime.evaluate failed";
    throw new Error(text);
  }
  return result.result?.value;
}

function callInPage(fn, ...args) {
  return `(${fn.toString()})(${args.map((arg) => JSON.stringify(arg)).join(",")})`;
}

async function pageCall(client, fn, ...args) {
  return evaluateExpression(client, callInPage(fn, ...args));
}

async function waitFor(label, read, predicate, timeoutMs = 20000) {
  const started = Date.now();
  let lastValue = null;
  let lastError = null;
  while (Date.now() - started < timeoutMs) {
    try {
      lastValue = await read();
      if (predicate(lastValue)) {
        return lastValue;
      }
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  const suffix = lastError ? lastError.message : JSON.stringify(lastValue);
  throw new Error(`Timed out waiting for ${label}: ${suffix}`);
}

async function openWorkbenchSidebar(client) {
  await waitFor(
    "Agent Workbench sidebar tab",
    () => pageCall(client, () => {
      if (document.getElementById("agent-workbench-panel")) {
        return { registered: true, active: true, panel: true };
      }
      const sidebar = window.app?.extensionManager?.sidebarTab;
      const tabs = Array.isArray(sidebar?.sidebarTabs) ? sidebar.sidebarTabs : [];
      const registered = tabs.some((tab) => tab?.id === "agent-workbench-sidebar");
      if (!registered) {
        return { registered: false, active: false, panel: false };
      }
      if (sidebar.activeSidebarTabId !== "agent-workbench-sidebar") {
        if (typeof sidebar.toggleSidebarTab === "function") {
          sidebar.toggleSidebarTab("agent-workbench-sidebar");
        } else {
          const icon = document.querySelector(".agent-workbench-sidebar-icon");
          icon?.closest("button,[role='button'],a,div")?.click();
        }
      }
      return {
        registered: true,
        active: sidebar.activeSidebarTabId === "agent-workbench-sidebar",
        panel: Boolean(document.getElementById("agent-workbench-panel")),
      };
    }),
    (state) => state?.registered === true,
  );
}

async function connectWorkbenchPage() {
  const target = await getOrCreatePageTarget();
  const client = new CdpClient(target.webSocketDebuggerUrl);
  await client.connect();
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  if (!String(target.url || "").startsWith(WORKBENCH_URL)) {
    await client.send("Page.navigate", { url: WORKBENCH_URL });
  }
  await waitFor(
    "document ready",
    () => pageCall(client, () => document.readyState),
    (state) => state === "interactive" || state === "complete",
  );
  await openWorkbenchSidebar(client);
  await waitFor(
    "Agent Workbench panel",
    () => pageCall(client, () => Boolean(
      document.getElementById("agent-workbench-panel")
      && document.getElementById("agent-workbench-smoke")
      && document.getElementById("agent-workbench-context")
      && document.getElementById("agent-workbench-thread")
      && document.getElementById("agent-workbench-send")
      && document.getElementById("agent-workbench-file")
    )),
    Boolean,
  );
  return client;
}

async function clickById(client, id) {
  const result = await pageCall(client, (elementId) => {
    function latestToolElement(selector) {
      const elements = Array.from(document.querySelectorAll(selector));
      return elements.length ? elements[elements.length - 1] : null;
    }
    const legacyMap = {
      "agent-workbench-plan": () => document.getElementById("agent-workbench-send"),
      "agent-workbench-apply": () => latestToolElement(".agent-workbench-tool-allow"),
      "agent-workbench-cancel": () => latestToolElement(".agent-workbench-tool-cancel"),
      "agent-workbench-confirm": () => latestToolElement(".agent-workbench-tool-confirm input"),
    };
    const element = legacyMap[elementId]?.() || document.getElementById(elementId);
    if (!element) {
      return { ok: false, error: `Missing element: ${elementId}` };
    }
    element.click();
    return {
      ok: true,
      disabled: element.disabled === true,
      hidden: element.hidden === true,
    };
  }, id);
  assert(result?.ok, result?.error || `Failed to click ${id}`);
  return result;
}

async function setInput(client, value) {
  const result = await pageCall(client, (text) => {
    const input = document.getElementById("agent-workbench-input");
    if (!input) {
      return { ok: false, error: "Missing agent-workbench-input" };
    }
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return { ok: true, value: input.value };
  }, value);
  assert(result?.ok, result?.error || "Failed to set workbench input");
  return result.value;
}

async function readOutput(client) {
  return pageCall(client, () => {
    const rows = JSON.parse(localStorage.getItem("ComfyUI.AgentWorkbench.chat.v1") || "[]");
    const latest = rows.slice().reverse().find((row) => row && row.response);
    if (latest?.response?.dry_run?.status === "dry_run") {
      return latest.response.dry_run;
    }
    if (latest?.response) {
      return latest.response;
    }
    const thread = document.getElementById("agent-workbench-thread");
    const text = thread?.textContent || "";
    try {
      return JSON.parse(text);
    } catch {
      return { raw_output: text };
    }
  });
}

function hasAction(payload, actionType) {
  return payload?.plan?.actions?.some((action) => action.type === actionType);
}

function findApplied(payload, actionType) {
  return (payload?.applied || []).find((row) => row?.type === actionType);
}

async function waitForOutput(client, label, predicate) {
  return waitFor(label, () => readOutput(client), predicate);
}

async function waitForGraphNodeCount(client) {
  return waitFor(
    "loaded ComfyUI graph nodes",
    () => pageCall(client, () => {
      const comfyApp = globalThis.app || globalThis.comfyAPI?.app;
      const graph = comfyApp?.graph || comfyApp?.canvas?.graph;
      const nodes = graph?._nodes || graph?.nodes || [];
      return nodes.length;
    }),
    (nodeCount) => Number.isInteger(nodeCount) && nodeCount > 0,
  );
}

async function runContextFlow(client, summary) {
  const expectedNodeCount = await waitForGraphNodeCount(client);
  await clickById(client, "agent-workbench-context");
  const context = await waitForOutput(
    client,
    "context output",
    (payload) => payload?.graph?.node_count > 0,
  );
  summary.context = {
    node_count: context.graph.node_count,
    expected_node_count: expectedNodeCount,
    selected_node_ids: context.graph.selected_node_ids,
  };
}

async function runSmokeManifestFlow(client, summary) {
  await clickById(client, "agent-workbench-smoke");
  const manifest = await waitForOutput(
    client,
    "smoke_manifest output",
    (payload) => payload?.ok === true && payload?.surface === "windows_browser",
  );
  const stepIds = (manifest.manual_steps || []).map((step) => step.id);
  for (const required of ["context", "plan_prompt_edit", "confirm_elevated", "cancel_plan", "apply_prompt_edit"]) {
    assert(stepIds.includes(required), `smoke manifest is missing step: ${required}`);
  }
  assert(
    manifest.sample_prompts?.prompt_edit === "把这个 prompt 节点的文本更新成 glowing blue forest",
    "smoke manifest prompt edit sample drifted",
  );
  assert(
    (manifest.agent_routes || []).includes(SMOKE_MANIFEST_PATH),
    "smoke manifest does not advertise its route",
  );
  summary.smoke_manifest = {
    surface: manifest.surface,
    manual_steps: stepIds,
    prompt_edit: manifest.sample_prompts.prompt_edit,
  };
}

async function runChatTimelinePlanCardFlow(client, summary) {
  await clickById(client, "agent-workbench-clear");
  await setInput(client, "关 swap 防止卡死");
  await clickById(client, "agent-workbench-plan");
  const dryRun = await waitForOutput(
    client,
    "chat timeline dry-run card",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "sudo.print_command"),
  );
  const state = await pageCall(client, () => {
    const messages = JSON.parse(localStorage.getItem("ComfyUI.AgentWorkbench.chat.v1") || "[]");
    const thread = document.getElementById("agent-workbench-thread");
    const cards = Array.from(document.querySelectorAll(".agent-workbench-tool-card"));
    const latestCard = cards.length ? cards[cards.length - 1] : null;
    return {
      messages: messages.map((row) => ({ role: row.role, text: row.text, has_response: Boolean(row.response) })),
      row_count: thread?.querySelectorAll(".agent-workbench-message").length || 0,
      has_allow_button: Boolean(latestCard?.querySelector(".agent-workbench-tool-allow")),
      has_cancel_button: Boolean(latestCard?.querySelector(".agent-workbench-tool-cancel")),
      latest_card_text: latestCard?.textContent || "",
    };
  });
  assert(state.messages.some((row) => row.role === "user" && row.text === "关 swap 防止卡死"), "chat history did not keep the user turn");
  assert(state.messages.some((row) => row.role === "assistant" && row.has_response), "chat history did not keep the assistant response");
  assert(state.row_count >= 3, "chat timeline did not render persisted rows");
  assert(state.has_allow_button, "tool card is missing allow button");
  assert(state.has_cancel_button, "tool card is missing cancel button");
  assert(state.latest_card_text.includes("允许执行"), "tool card does not expose allow action");
  await clickById(client, "agent-workbench-cancel");
  await waitForOutput(client, "chat tool card cancel output", (payload) => payload?.error === "user_cancelled");

  summary.chat_timeline_plan_card = {
    action: dryRun.plan.actions[0].type,
    row_count: state.row_count,
    has_allow_button: state.has_allow_button,
    has_cancel_button: state.has_cancel_button,
  };
}

async function runSudoConfirmCancelApplyFlow(client, summary) {
  await setInput(client, "关 swap 防止卡死");
  await clickById(client, "agent-workbench-plan");
  const firstPlan = await waitForOutput(
    client,
    "sudo dry-run plan",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "sudo.print_command"),
  );
  assert(firstPlan.plan.requires_confirmation === true, "sudo.print_command plan must require confirmation");
  await clickById(client, "agent-workbench-confirm");
  await clickById(client, "agent-workbench-cancel");
  const cancelled = await waitForOutput(
    client,
    "cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "关 swap 防止卡死");
  await clickById(client, "agent-workbench-plan");
  const secondPlan = await waitForOutput(
    client,
    "sudo dry-run plan after cancel",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "sudo.print_command"),
  );
  await clickById(client, "agent-workbench-confirm");
  await clickById(client, "agent-workbench-apply");
  const applied = await waitForOutput(
    client,
    "sudo print-only apply result",
    (payload) => payload?.ok === true && Boolean(findApplied(payload, "sudo.print_command")),
  );
  const sudoAction = findApplied(applied, "sudo.print_command");
  if (sudoAction.executed !== false) {
    throw new Error(`sudo.print_command must stay print-only: ${JSON.stringify(sudoAction)}`);
  }

  summary.sudo_print_only = {
    cancelled: cancelled.error,
    command: sudoAction.command,
    executed: sudoAction.executed,
    plan_hash: secondPlan.plan.plan_hash,
  };
}

async function runComposeCommandValuePlanFlow(client, summary) {
  await setInput(client, "把 compose reserve-vram 改成 12 并应用配置");
  await clickById(client, "agent-workbench-plan");
  const dryRun = await waitForOutput(
    client,
    "compose command value dry-run",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "compose.set_command_value"),
  );
  const action = dryRun.plan.actions.find((row) => row.type === "compose.set_command_value");
  assert(dryRun.plan.requires_confirmation === true, "compose command value plan must require confirmation");
  assert(dryRun.plan.risk_level === "service", "compose command value plan must be service risk");
  assert(action.payload.flag === "--reserve-vram", "compose command value planned the wrong flag");
  assert(action.payload.value === "12", "compose command value planned the wrong value");
  await clickById(client, "agent-workbench-cancel");
  const cancelled = await waitForOutput(
    client,
    "compose command value cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  summary.compose_command_value_plan = {
    flag: action.payload.flag,
    value: action.payload.value,
    risk_level: dryRun.plan.risk_level,
    cancelled: cancelled.error,
  };
}

async function postAgentPlan(message, graph) {
  return fetchJson(new URL("/agent/plan", WORKBENCH_URL).toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, graph }),
  });
}

async function runMissingNodeManagerPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "安装当前工作流缺失节点然后重启 ComfyUI",
    {
      nodes: [
        { id: 1, type: "SaveImage", title: "Save Image" },
        {
          id: 2,
          type: "ImpactWildcard",
          title: "Impact Wildcard",
          properties: { cnr_id: "ComfyUI-Impact-Pack" },
        },
      ],
      node_types: [{ type: "SaveImage", title: "Save Image" }],
    },
  );
  assert(dryRun?.status === "dry_run", "missing-node manager plan did not return dry_run");
  assert(hasAction(dryRun, "custom_node.install"), "missing-node manager plan did not install a custom node");
  assert(hasAction(dryRun, "service.restart_container"), "missing-node manager plan did not include restart");
  const installAction = dryRun.plan.actions.find((action) => action.type === "custom_node.install");
  assert(
    installAction.payload?.node?.id === "ComfyUI-Impact-Pack",
    `missing-node manager plan used wrong node id: ${JSON.stringify(installAction.payload || {})}`,
  );

  summary.missing_node_plan = {
    node_id: installAction.payload.node.id,
    method: installAction.payload.method,
    restart: true,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runModelInstallPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "安装模型 https://example.com/models/hero.safetensors 到 checkpoints，base SDXL",
    { nodes: [], links: [], node_types: [] },
  );
  assert(dryRun?.status === "dry_run", "model install plan did not return dry_run");
  assert(hasAction(dryRun, "model.install"), "model install plan did not include model.install");
  const installAction = dryRun.plan.actions.find((action) => action.type === "model.install");
  assert(
    installAction.payload?.model?.filename === "hero.safetensors",
    `model install plan used wrong filename: ${JSON.stringify(installAction.payload || {})}`,
  );
  assert(
    installAction.payload?.model?.save_path === "checkpoints",
    `model install plan used wrong save_path: ${JSON.stringify(installAction.payload || {})}`,
  );
  assert(dryRun.plan.requires_confirmation === true, "model install plan must require confirmation");

  summary.model_install_plan = {
    filename: installAction.payload.model.filename,
    save_path: installAction.payload.model.save_path,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runModelWidgetUsePlanFlow(summary) {
  const graph = {
    nodes: [
      {
        id: 2,
        type: "CheckpointLoaderSimple",
        title: "Load Checkpoint",
        widgets: [{ name: "ckpt_name", value: "old.safetensors" }],
      },
      {
        id: 3,
        type: "LoraLoader",
        title: "Load LoRA",
        widgets: [
          { name: "lora_name", value: "old_lora.safetensors" },
          { name: "strength_model", value: 1.0 },
          { name: "strength_clip", value: 1.0 },
        ],
      },
      {
        id: 4,
        type: "LoadImage",
        title: "Load Image",
        widgets: [
          { name: "image", value: "old.png" },
          { name: "upload", value: "image" },
        ],
      },
      {
        id: 5,
        type: "SaveImage",
        title: "Save Image",
        widgets: [{ name: "filename_prefix", value: "ComfyUI" }],
      },
    ],
    links: [],
    node_types: [],
  };
  const cases = [
    ["把底模用 juggernautXL.safetensors", 2, "ckpt_name", "juggernautXL.safetensors"],
    ["让 LoRA 用 detail.safetensors", 3, "lora_name", "detail.safetensors"],
    ["参考图用 input/pose.png", 4, "image", "input/pose.png"],
    ["保存图片用 renders/shot-a 作为文件名前缀", 5, "filename_prefix", "renders/shot-a"],
  ];
  const planned = [];
  for (const [message, nodeId, widgetName, value] of cases) {
    const dryRun = await postAgentPlan(message, graph);
    assert(dryRun?.status === "dry_run", `model widget use plan did not return dry_run for: ${message}`);
    const action = dryRun.plan?.actions?.find((row) => row.type === "graph.set_widget");
    assert(action?.payload?.node_id === nodeId, `model widget use plan targeted wrong node for: ${message}`);
    assert(action?.payload?.widget === widgetName, `model widget use plan targeted wrong widget for: ${message}`);
    assert(action?.payload?.value === value, `model widget use plan used wrong value for: ${message}`);
    planned.push(action.payload);
  }
  const loraStrengthDryRun = await postAgentPlan("让 LoRA 用 detail.safetensors，强度 0.7", graph);
  assert(loraStrengthDryRun?.status === "dry_run", "LoRA model+strength use plan did not return dry_run");
  const loraStrengthActions = loraStrengthDryRun.plan?.actions || [];
  assert(
    loraStrengthActions.some((action) => (
      action.payload?.node_id === 3
      && action.payload?.widget === "lora_name"
      && action.payload?.value === "detail.safetensors"
    )),
    "LoRA model+strength use plan did not set lora_name",
  );
  assert(
    loraStrengthActions.some((action) => (
      action.payload?.node_id === 3
      && action.payload?.widget === "strength_model"
      && action.payload?.value === 0.7
    )),
    "LoRA model+strength use plan did not set strength_model",
  );

  summary.model_widget_use_plan = {
    planned,
    lora_strength: loraStrengthActions.map((action) => action.payload),
    risk_level: "canvas",
  };
}

async function runManagerQueueStatusPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "查看 Manager 安装队列状态",
    { nodes: [], links: [], node_types: [] },
  );
  assert(dryRun?.status === "dry_run", "manager queue status plan did not return dry_run");
  assert(hasAction(dryRun, "manager.queue_status"), "manager queue status plan did not include manager.queue_status");
  assert(dryRun.plan.requires_confirmation === false, "manager queue status must not require confirmation");
  assert(dryRun.plan.risk_level === "read", "manager queue status must be read risk");

  summary.manager_queue_status_plan = {
    action: "manager.queue_status",
    risk_level: dryRun.plan.risk_level,
    requires_confirmation: dryRun.plan.requires_confirmation,
  };
}

async function runManagerQueueControlPlanFlow(summary) {
  const startDryRun = await postAgentPlan(
    "开始 Manager 安装队列",
    { nodes: [], links: [], node_types: [] },
  );
  assert(startDryRun?.status === "dry_run", "manager queue start plan did not return dry_run");
  assert(hasAction(startDryRun, "manager.queue_start"), "manager queue start plan did not include queue_start");
  assert(startDryRun.plan.requires_confirmation === true, "manager queue start must require confirmation");
  assert(startDryRun.plan.risk_level === "package", "manager queue start must be package risk");

  const resetDryRun = await postAgentPlan(
    "清空 Manager 安装队列",
    { nodes: [], links: [], node_types: [] },
  );
  assert(resetDryRun?.status === "dry_run", "manager queue reset plan did not return dry_run");
  assert(hasAction(resetDryRun, "manager.queue_reset"), "manager queue reset plan did not include queue_reset");
  assert(resetDryRun.plan.requires_confirmation === true, "manager queue reset must require confirmation");
  assert(resetDryRun.plan.risk_level === "package", "manager queue reset must be package risk");

  summary.manager_queue_control_plan = {
    start_action: "manager.queue_start",
    reset_action: "manager.queue_reset",
    risk_level: startDryRun.plan.risk_level,
    requires_confirmation: startDryRun.plan.requires_confirmation,
  };
}

async function runCustomNodeReadPlanFlow(client, summary) {
  const listDryRun = await postAgentPlan(
    "列出已安装插件",
    { nodes: [], links: [], node_types: [] },
  );
  assert(listDryRun?.status === "dry_run", "custom node list plan did not return dry_run");
  assert(hasAction(listDryRun, "custom_node.list"), "custom node list plan did not include custom_node.list");
  assert(listDryRun.plan.requires_confirmation === false, "custom node list plan must not require confirmation");
  assert(listDryRun.plan.risk_level === "read", "custom node list plan must be read risk");

  const searchDryRun = await postAgentPlan(
    "搜索 custom node Impact Pack",
    { nodes: [], links: [], node_types: [] },
  );
  assert(searchDryRun?.status === "dry_run", "custom node search plan did not return dry_run");
  assert(hasAction(searchDryRun, "custom_node.search"), "custom node search plan did not include custom_node.search");
  assert(searchDryRun.plan.requires_confirmation === false, "custom node search plan must not require confirmation");
  assert(searchDryRun.plan.risk_level === "read", "custom node search plan must be read risk");
  const searchAction = searchDryRun.plan.actions.find((row) => row.type === "custom_node.search");
  assert(searchAction.payload.query === "Impact Pack", "custom node search plan used wrong query");

  await setInput(client, "列出已安装插件");
  await clickById(client, "agent-workbench-plan");
  const uiDryRun = await waitForOutput(
    client,
    "custom node list dry-run",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "custom_node.list"),
  );
  await clickById(client, "agent-workbench-apply");
  const applied = await waitForOutput(
    client,
    "custom node list apply result",
    (payload) => payload?.ok === true
      && payload?.frontend_requests?.some((request) => (
        request.path === "/customnode/installed"
        && request.filtered?.type === "custom_node.list"
      )),
  );
  const frontendRequest = applied.frontend_requests.find((request) => request.path === "/customnode/installed");

  summary.custom_node_read_plan = {
    list_action: "custom_node.list",
    search_action: "custom_node.search",
    search_query: searchAction.payload.query,
    frontend_filtered_count: frontendRequest.filtered.count,
    requires_confirmation: uiDryRun.plan.requires_confirmation,
    risk_level: uiDryRun.plan.risk_level,
  };
}

async function runCustomNodeStateSynonymPlanFlow(summary) {
  const disableDryRun = await postAgentPlan(
    "把 ComfyUI-Impact-Pack 插件关掉然后重启服务",
    { nodes: [], links: [], node_types: [] },
  );
  assert(disableDryRun?.status === "dry_run", "custom node close synonym plan did not return dry_run");
  assert(hasAction(disableDryRun, "custom_node.disable"), "custom node close synonym plan did not disable the plugin");
  assert(hasAction(disableDryRun, "service.restart_container"), "custom node close synonym plan did not include restart");
  assert(disableDryRun.plan.requires_confirmation === true, "custom node close synonym plan must require confirmation");
  assert(disableDryRun.plan.risk_level === "service", "custom node close synonym plan must be service risk");
  const disableAction = disableDryRun.plan.actions.find((row) => row.type === "custom_node.disable");
  assert(disableAction.payload.id === "ComfyUI-Impact-Pack", "custom node close synonym plan targeted wrong plugin");

  const enableDryRun = await postAgentPlan(
    "打开 ComfyUI-Impact-Pack 插件并重启",
    { nodes: [], links: [], node_types: [] },
  );
  assert(enableDryRun?.status === "dry_run", "custom node open synonym plan did not return dry_run");
  assert(hasAction(enableDryRun, "custom_node.enable"), "custom node open synonym plan did not enable the plugin");
  assert(hasAction(enableDryRun, "service.restart_container"), "custom node open synonym plan did not include restart");
  assert(enableDryRun.plan.requires_confirmation === true, "custom node open synonym plan must require confirmation");
  assert(enableDryRun.plan.risk_level === "service", "custom node open synonym plan must be service risk");
  const enableAction = enableDryRun.plan.actions.find((row) => row.type === "custom_node.enable");
  assert(enableAction.payload.id === "ComfyUI-Impact-Pack", "custom node open synonym plan targeted wrong plugin");

  summary.custom_node_state_synonym_plan = {
    disable: disableAction.payload,
    enable: enableAction.payload,
    restart: true,
    risk_level: disableDryRun.plan.risk_level,
    requires_confirmation: disableDryRun.plan.requires_confirmation,
  };
}

async function runCustomNodeUpdateInstalledPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "更新已安装插件然后重启服务",
    { nodes: [], links: [], node_types: [] },
  );
  assert(dryRun?.status === "dry_run", "custom node installed update plan did not return dry_run");
  assert(hasAction(dryRun, "custom_node.update_all"), "custom node installed update plan did not update all plugins");
  assert(hasAction(dryRun, "service.restart_container"), "custom node installed update plan did not include restart");
  assert(dryRun.plan.requires_confirmation === true, "custom node installed update plan must require confirmation");
  assert(dryRun.plan.risk_level === "service", "custom node installed update plan must be service risk");

  summary.custom_node_update_installed_plan = {
    update_all: true,
    restart: true,
    risk_level: dryRun.plan.risk_level,
    requires_confirmation: dryRun.plan.requires_confirmation,
  };
}

async function runServiceLogsPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "查看 ComfyUI 最近日志",
    { nodes: [], links: [], node_types: [] },
  );
  assert(dryRun?.status === "dry_run", "service logs plan did not return dry_run");
  assert(hasAction(dryRun, "service.logs"), "service logs plan did not include service.logs");
  assert(dryRun.plan.requires_confirmation === false, "service logs plan must not require confirmation");
  assert(dryRun.plan.risk_level === "read", "service logs plan must be read risk");
  const action = dryRun.plan.actions.find((row) => row.type === "service.logs");
  assert(action.payload.container === "comfyui-gb10", "service logs plan used the wrong container");
  assert(action.payload.tail === 80, "service logs plan used the wrong tail limit");

  summary.service_logs_plan = {
    action: "service.logs",
    container: action.payload.container,
    tail: action.payload.tail,
    risk_level: dryRun.plan.risk_level,
    requires_confirmation: dryRun.plan.requires_confirmation,
  };
}

async function runCopySamplerSeedPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "把 Base KSampler 的种子复制到 Refiner KSampler",
    {
      nodes: [
        {
          id: 9,
          type: "KSampler",
          title: "Base KSampler",
          widgets: [{ name: "seed", value: 12345 }],
        },
        {
          id: 10,
          type: "KSampler",
          title: "Refiner KSampler",
          widgets: [{ name: "seed", value: 999 }],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "copy sampler seed plan did not return dry_run");
  assert(hasAction(dryRun, "graph.set_widget"), "copy sampler seed plan did not include graph.set_widget");
  assert(!hasAction(dryRun, "graph.duplicate_node"), "copy sampler seed plan must not duplicate a node");
  const action = dryRun.plan.actions.find((row) => row.type === "graph.set_widget");
  assert(action.payload.node_id === 10, "copy sampler seed plan targeted the wrong node");
  assert(action.payload.widget === "seed", "copy sampler seed plan targeted the wrong widget");
  assert(action.payload.value === 12345, "copy sampler seed plan copied the wrong value");

  summary.copy_sampler_seed_plan = {
    node_id: action.payload.node_id,
    widget: action.payload.widget,
    value: action.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runCopySamplerSettingsPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "把 Base KSampler 的设置复制到 Refiner KSampler",
    {
      nodes: [
        {
          id: 9,
          type: "KSampler",
          title: "Base KSampler",
          widgets: [
            { name: "seed", value: 12345 },
            { name: "steps", value: 28 },
            { name: "cfg", value: 7.5 },
            { name: "sampler_name", value: "dpmpp_2m" },
            { name: "scheduler", value: "karras" },
            { name: "denoise", value: 0.45 },
          ],
        },
        {
          id: 10,
          type: "KSampler",
          title: "Refiner KSampler",
          widgets: [
            { name: "seed", value: 999 },
            { name: "steps", value: 12 },
            { name: "cfg", value: 4.0 },
            { name: "sampler_name", value: "euler" },
            { name: "scheduler", value: "normal" },
            { name: "denoise", value: 0.7 },
            { name: "control_after_generate", value: "randomize" },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "copy sampler settings plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const widgetActions = actions.filter((row) => row.type === "graph.set_widget");
  assert(widgetActions.length === 6, `copy sampler settings plan copied ${widgetActions.length} widgets instead of 6`);
  assert(
    widgetActions.every((action) => action.payload?.node_id === 10),
    "copy sampler settings plan targeted the wrong node",
  );
  assert(
    widgetActions.some((action) => action.payload?.widget === "seed" && action.payload?.value === 12345),
    "copy sampler settings plan did not copy seed",
  );
  assert(
    widgetActions.some((action) => action.payload?.widget === "steps" && action.payload?.value === 28),
    "copy sampler settings plan did not copy steps",
  );
  assert(
    widgetActions.some((action) => action.payload?.widget === "cfg" && action.payload?.value === 7.5),
    "copy sampler settings plan did not copy cfg",
  );
  assert(
    widgetActions.some((action) => action.payload?.widget === "sampler_name" && action.payload?.value === "dpmpp_2m"),
    "copy sampler settings plan did not copy sampler_name",
  );
  assert(
    widgetActions.some((action) => action.payload?.widget === "scheduler" && action.payload?.value === "karras"),
    "copy sampler settings plan did not copy scheduler",
  );
  assert(
    widgetActions.some((action) => action.payload?.widget === "denoise" && action.payload?.value === 0.45),
    "copy sampler settings plan did not copy denoise",
  );
  assert(
    !widgetActions.some((action) => action.payload?.widget === "control_after_generate"),
    "copy sampler settings plan copied a target-only widget",
  );

  summary.copy_sampler_settings_plan = {
    copied: widgetActions.map((action) => action.payload),
    risk_level: dryRun.plan.risk_level,
  };
}

async function runSamplerSchedulerPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "把 KSampler 的采样方法改成 dpmpp_2m，调度方式改成 karras",
    {
      nodes: [
        {
          id: 9,
          type: "KSampler",
          title: "KSampler",
          widgets: [
            { name: "sampler_name", value: "euler" },
            { name: "scheduler", value: "normal" },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "sampler scheduler plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const samplerAction = actions.find((action) => action.payload?.widget === "sampler_name");
  const schedulerAction = actions.find((action) => action.payload?.widget === "scheduler");
  assert(samplerAction?.payload?.value === "dpmpp_2m", "sampler scheduler plan used wrong sampler value");
  assert(schedulerAction?.payload?.value === "karras", "sampler scheduler plan used wrong scheduler value");

  summary.sampler_scheduler_plan = {
    sampler: samplerAction.payload.value,
    scheduler: schedulerAction.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runSamplerRelativePlanFlow(summary) {
  const graph = {
    nodes: [
      {
        id: 9,
        type: "KSampler",
        title: "KSampler",
        widgets: [
          { name: "steps", value: 20 },
          { name: "denoise", value: 1.0 },
        ],
      },
      {
        id: 10,
        type: "KSampler",
        title: "Refiner KSampler",
        widgets: [
          { name: "steps", value: 12 },
          { name: "denoise", value: 0.7 },
        ],
      },
    ],
    links: [],
    node_types: [],
  };
  const stepsDryRun = await postAgentPlan("把所有 KSampler 的步数加 5", graph);
  assert(stepsDryRun?.status === "dry_run", "sampler relative steps plan did not return dry_run");
  const stepActions = stepsDryRun.plan?.actions || [];
  assert(
    stepActions.some((action) => action.payload?.node_id === 9 && action.payload?.widget === "steps" && action.payload?.value === 25),
    "sampler relative steps plan did not increment the base sampler",
  );
  assert(
    stepActions.some((action) => action.payload?.node_id === 10 && action.payload?.widget === "steps" && action.payload?.value === 17),
    "sampler relative steps plan did not increment the refiner sampler",
  );

  const denoiseDryRun = await postAgentPlan("把所有 KSampler 的 denoise 降到 0.4", graph);
  assert(denoiseDryRun?.status === "dry_run", "sampler denoise set plan did not return dry_run");
  const denoiseActions = denoiseDryRun.plan?.actions || [];
  assert(
    denoiseActions.filter((action) => action.payload?.widget === "denoise" && action.payload?.value === 0.4).length === 2,
    "sampler denoise set plan did not set both denoise widgets",
  );

  summary.sampler_relative_plan = {
    steps: stepActions.map((action) => action.payload),
    denoise: denoiseActions.map((action) => action.payload),
    risk_level: stepsDryRun.plan.risk_level,
  };
}

async function runRelativePositionPlanFlow(summary) {
  const graph = {
    nodes: [
      { id: 9, type: "KSampler", title: "Base KSampler", pos: [10, 20] },
      { id: 10, type: "KSampler", title: "Refiner KSampler", pos: [400, 80] },
    ],
    links: [],
    node_types: [],
  };

  const rightDryRun = await postAgentPlan("把 Base KSampler 移到 Refiner KSampler 右边", graph);
  assert(rightDryRun?.status === "dry_run", "relative right position plan did not return dry_run");
  const rightAction = rightDryRun.plan?.actions?.find((row) => row.type === "graph.set_position");
  assert(rightAction?.payload?.node_id === 9, "relative right position plan targeted the wrong node");
  assert(
    JSON.stringify(rightAction.payload.pos) === JSON.stringify([620, 80]),
    "relative right position plan used the wrong position",
  );

  const belowDryRun = await postAgentPlan("把 Base KSampler 放到 Refiner KSampler 下面", graph);
  assert(belowDryRun?.status === "dry_run", "relative below position plan did not return dry_run");
  const belowAction = belowDryRun.plan?.actions?.find((row) => row.type === "graph.set_position");
  assert(belowAction?.payload?.node_id === 9, "relative below position plan targeted the wrong node");
  assert(
    JSON.stringify(belowAction.payload.pos) === JSON.stringify([400, 260]),
    "relative below position plan used the wrong position",
  );

  summary.relative_position_plan = {
    right: rightAction.payload,
    below: belowAction.payload,
    risk_level: rightDryRun.plan.risk_level,
  };
}

async function runAutoLayoutPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "整理这个工作流",
    {
      nodes: [
        { id: 1, type: "CheckpointLoaderSimple", title: "Checkpoint", pos: [500, 100] },
        { id: 3, type: "CLIPTextEncode", title: "Positive Prompt", pos: [100, 220] },
        { id: 4, type: "CLIPTextEncode", title: "Negative Prompt", pos: [160, 360] },
        { id: 9, type: "KSampler", title: "KSampler", pos: [700, 260] },
        { id: 8, type: "VAEDecode", title: "VAE Decode", pos: [40, 80] },
        { id: 10, type: "SaveImage", title: "Save Image", pos: [900, 420] },
      ],
      links: [
        { origin_id: 1, origin_slot: 0, target_id: 9, target_slot: 0 },
        { origin_id: 3, origin_slot: 0, target_id: 9, target_slot: 1 },
        { origin_id: 4, origin_slot: 0, target_id: 9, target_slot: 2 },
        { origin_id: 9, origin_slot: 0, target_id: 8, target_slot: 0 },
        { origin_id: 8, origin_slot: 0, target_id: 10, target_slot: 0 },
      ],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "auto layout plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  assert(
    actions.filter((action) => action.type === "graph.set_position").length === 6,
    "auto layout plan did not position all nodes",
  );
  const expected = new Map([
    [1, [40, 80]],
    [3, [40, 260]],
    [4, [40, 440]],
    [9, [260, 80]],
    [8, [480, 80]],
    [10, [700, 80]],
  ]);
  for (const [nodeId, pos] of expected) {
    const action = actions.find((row) => row.payload?.node_id === nodeId);
    assert(action, `auto layout plan did not include node ${nodeId}`);
    assert(
      JSON.stringify(action.payload.pos) === JSON.stringify(pos),
      `auto layout plan positioned node ${nodeId} incorrectly`,
    );
  }

  summary.auto_layout_plan = {
    positions: actions.map((action) => action.payload),
    risk_level: dryRun.plan.risk_level,
  };
}

async function runCollapsedNodePlanFlow(summary) {
  const graph = {
    nodes: [
      { id: 7, type: "CLIPTextEncode", title: "Prompt", selected: true },
      { id: 9, type: "KSampler", title: "KSampler", collapsed: true },
      { id: 10, type: "KSampler", title: "Refiner KSampler", collapsed: true },
    ],
    links: [],
    node_types: [],
  };

  const collapseDryRun = await postAgentPlan("折叠这个节点", graph);
  assert(collapseDryRun?.status === "dry_run", "collapsed node plan did not return dry_run");
  const collapseAction = collapseDryRun.plan?.actions?.find((row) => row.type === "graph.set_collapsed");
  assert(collapseAction?.payload?.node_id === 7, "collapsed node plan targeted the wrong node");
  assert(collapseAction?.payload?.collapsed === true, "collapsed node plan did not collapse the node");

  const expandDryRun = await postAgentPlan("展开所有 KSampler 节点", graph);
  assert(expandDryRun?.status === "dry_run", "expand nodes plan did not return dry_run");
  const expandActions = expandDryRun.plan?.actions || [];
  assert(
    expandActions.filter((action) => action.type === "graph.set_collapsed" && action.payload?.collapsed === false).length === 2,
    "expand nodes plan did not expand both KSampler nodes",
  );

  summary.collapsed_node_plan = {
    collapse: collapseAction.payload,
    expand: expandActions.map((action) => action.payload),
    risk_level: collapseDryRun.plan.risk_level,
  };
}

async function runNodeModePlanFlow(summary) {
  const bypassDryRun = await postAgentPlan(
    "旁路这个节点",
    {
      nodes: [
        { id: 7, type: "CLIPTextEncode", title: "Prompt", selected: true },
        { id: 9, type: "KSampler", title: "KSampler" },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(bypassDryRun?.status === "dry_run", "node bypass plan did not return dry_run");
  const bypassAction = bypassDryRun.plan?.actions?.find((row) => row.type === "graph.set_mode");
  assert(bypassAction?.payload?.node_id === 7, "node bypass plan targeted the wrong node");
  assert(bypassAction?.payload?.mode === "bypass", "node bypass plan used the wrong mode");

  const muteDryRun = await postAgentPlan(
    "禁用 KSampler 节点",
    {
      nodes: [
        { id: 7, type: "CLIPTextEncode", title: "Prompt" },
        { id: 9, type: "KSampler", title: "KSampler" },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(muteDryRun?.status === "dry_run", "node mute plan did not return dry_run");
  const muteAction = muteDryRun.plan?.actions?.find((row) => row.type === "graph.set_mode");
  assert(muteAction?.payload?.node_id === 9, "node mute plan targeted the wrong node");
  assert(muteAction?.payload?.mode === "mute", "node mute plan used the wrong mode");

  const enableDryRun = await postAgentPlan(
    "启用 12 号节点",
    {
      nodes: [
        { id: 12, type: "KSampler", title: "KSampler", mode: 4 },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(enableDryRun?.status === "dry_run", "node enable plan did not return dry_run");
  const enableAction = enableDryRun.plan?.actions?.find((row) => row.type === "graph.set_mode");
  assert(enableAction?.payload?.node_id === 12, "node enable plan targeted the wrong node");
  assert(enableAction?.payload?.mode === "always", "node enable plan used the wrong mode");

  summary.node_mode_plan = {
    bypass: bypassAction.payload,
    mute: muteAction.payload,
    enable: enableAction.payload,
    risk_level: bypassDryRun.plan.risk_level,
  };
}

async function runGraphNeighborhoodPlanFlow(summary) {
  const graph = {
    nodes: [
      {
        id: 20,
        type: "SaveImage",
        title: "Unrelated Save Image",
        pos: [660, 360],
        widgets: [{ name: "filename_prefix", value: "wrong" }],
      },
      { id: 1, type: "CheckpointLoaderSimple", title: "Checkpoint", pos: [0, 100] },
      { id: 3, type: "CLIPTextEncode", title: "Positive Prompt", pos: [0, 260] },
      { id: 4, type: "CLIPTextEncode", title: "Negative Prompt", pos: [0, 420] },
      { id: 9, type: "KSampler", title: "KSampler", pos: [220, 160], widgets: [{ name: "steps", value: 20 }] },
      { id: 8, type: "VAEDecode", title: "VAE Decode", pos: [440, 160] },
      {
        id: 10,
        type: "SaveImage",
        title: "Save Image",
        selected: true,
        pos: [660, 160],
        widgets: [{ name: "filename_prefix", value: "ComfyUI" }],
      },
    ],
    links: [
      { origin_id: 1, origin_slot: 0, target_id: 9, target_slot: 0 },
      { origin_id: 3, origin_slot: 0, target_id: 9, target_slot: 1 },
      { origin_id: 4, origin_slot: 0, target_id: 9, target_slot: 2 },
      { origin_id: 9, origin_slot: 0, target_id: 8, target_slot: 0 },
      { origin_id: 8, origin_slot: 0, target_id: 10, target_slot: 0 },
    ],
    node_types: [],
  };

  const downstreamDryRun = await postAgentPlan("禁用 KSampler 后面的节点", graph);
  assert(downstreamDryRun?.status === "dry_run", "downstream node mode plan did not return dry_run");
  const downstreamActions = downstreamDryRun.plan?.actions || [];
  assert(
    downstreamActions.length === 2
      && downstreamActions.every((action) => action.type === "graph.set_mode" && action.payload?.mode === "mute"),
    "downstream node mode plan did not mute downstream nodes",
  );
  assert(
    downstreamActions.some((action) => action.payload?.node_id === 8)
      && downstreamActions.some((action) => action.payload?.node_id === 10)
      && !downstreamActions.some((action) => action.payload?.node_id === 9),
    "downstream node mode plan selected the wrong nodes",
  );

  const downstreamColorDryRun = await postAgentPlan("把 KSampler 后面的节点标黄", graph);
  assert(downstreamColorDryRun?.status === "dry_run", "downstream node color plan did not return dry_run");
  const downstreamColorActions = downstreamColorDryRun.plan?.actions || [];
  assert(
    downstreamColorActions.length === 2
      && downstreamColorActions.every((action) => action.type === "graph.set_color" && action.payload?.color === "#f2c94c"),
    "downstream node color plan did not color downstream nodes yellow",
  );
  assert(
    downstreamColorActions.some((action) => action.payload?.node_id === 8)
      && downstreamColorActions.some((action) => action.payload?.node_id === 10)
      && !downstreamColorActions.some((action) => action.payload?.node_id === 9),
    "downstream node color plan selected the wrong nodes",
  );

  const downstreamDeleteDryRun = await postAgentPlan("删除 KSampler 后面的节点", graph);
  assert(downstreamDeleteDryRun?.status === "dry_run", "downstream node delete plan did not return dry_run");
  const downstreamDeleteActions = downstreamDeleteDryRun.plan?.actions || [];
  assert(
    downstreamDeleteActions.length === 2
      && downstreamDeleteActions.every((action) => action.type === "graph.delete_node"),
    "downstream node delete plan did not delete downstream nodes",
  );
  assert(
    downstreamDeleteActions.some((action) => action.payload?.node_id === 8)
      && downstreamDeleteActions.some((action) => action.payload?.node_id === 10)
      && !downstreamDeleteActions.some((action) => action.payload?.node_id === 9),
    "downstream node delete plan selected the wrong nodes",
  );

  const upstreamDryRun = await postAgentPlan("选中这个节点上游节点", graph);
  assert(upstreamDryRun?.status === "dry_run", "upstream node select plan did not return dry_run");
  const upstreamAction = upstreamDryRun.plan?.actions?.find((action) => action.type === "graph.select_nodes");
  assert(upstreamAction, "upstream node select plan did not include graph.select_nodes");
  assert(
    JSON.stringify(upstreamAction.payload?.node_ids) === JSON.stringify([1, 3, 4, 9, 8]),
    "upstream node select plan selected the wrong nodes",
  );
  assert(upstreamAction.payload?.focus === false, "upstream node select plan should not focus nodes");

  const upstreamDuplicateDryRun = await postAgentPlan("复制这个节点上游节点", graph);
  assert(upstreamDuplicateDryRun?.status === "dry_run", "upstream node duplicate plan did not return dry_run");
  const upstreamDuplicateActions = upstreamDuplicateDryRun.plan?.actions || [];
  assert(
    upstreamDuplicateActions.length === 5
      && upstreamDuplicateActions.every((action) => action.type === "graph.duplicate_node"),
    "upstream node duplicate plan did not duplicate upstream nodes",
  );
  assert(
    JSON.stringify(upstreamDuplicateActions.map((action) => action.payload?.node_id)) === JSON.stringify([1, 3, 4, 9, 8]),
    "upstream node duplicate plan selected the wrong nodes",
  );
  assert(
    upstreamDuplicateActions.every((action) => action.payload?.select === false),
    "upstream node duplicate plan should not individually select every duplicate",
  );

  const downstreamDisconnectDryRun = await postAgentPlan("断开 KSampler 后面的节点的所有输入", graph);
  assert(downstreamDisconnectDryRun?.status === "dry_run", "downstream node disconnect plan did not return dry_run");
  const downstreamDisconnectActions = downstreamDisconnectDryRun.plan?.actions || [];
  assert(
    downstreamDisconnectActions.length === 2
      && downstreamDisconnectActions.every((action) => action.type === "graph.disconnect"),
    "downstream node disconnect plan did not disconnect downstream nodes",
  );
  assert(
    JSON.stringify(downstreamDisconnectActions.map((action) => action.payload?.target_node_id)) === JSON.stringify([8, 10]),
    "downstream node disconnect plan selected the wrong target nodes",
  );

  const upstreamDisconnectDryRun = await postAgentPlan("断开这个节点上游节点的所有输出", graph);
  assert(upstreamDisconnectDryRun?.status === "dry_run", "upstream node disconnect plan did not return dry_run");
  const upstreamDisconnectActions = upstreamDisconnectDryRun.plan?.actions || [];
  assert(
    upstreamDisconnectActions.length === 5
      && upstreamDisconnectActions.every((action) => action.type === "graph.disconnect"),
    "upstream node disconnect plan did not disconnect upstream nodes",
  );
  assert(
    JSON.stringify(upstreamDisconnectActions.map((action) => action.payload?.origin_node_id)) === JSON.stringify([1, 3, 4, 9, 8]),
    "upstream node disconnect plan selected the wrong origin nodes",
  );

  const downstreamWidgetDryRun = await postAgentPlan(
    "把 KSampler 后面的 Save Image 节点的文件名前缀改成 renders/shot-a",
    graph,
  );
  assert(downstreamWidgetDryRun?.status === "dry_run", "downstream node widget plan did not return dry_run");
  const downstreamWidgetActions = downstreamWidgetDryRun.plan?.actions || [];
  assert(
    downstreamWidgetActions.length === 1
      && downstreamWidgetActions[0]?.type === "graph.set_widget",
    "downstream node widget plan did not set one downstream widget",
  );
  assert(
    downstreamWidgetActions[0]?.payload?.node_id === 10
      && downstreamWidgetActions[0]?.payload?.widget === "filename_prefix"
      && downstreamWidgetActions[0]?.payload?.value === "renders/shot-a",
    "downstream node widget plan selected the wrong node or value",
  );

  const upstreamWidgetDryRun = await postAgentPlan("把这个节点上游 KSampler 的 steps 改成 24", graph);
  assert(upstreamWidgetDryRun?.status === "dry_run", "upstream node widget plan did not return dry_run");
  const upstreamWidgetActions = upstreamWidgetDryRun.plan?.actions || [];
  assert(
    upstreamWidgetActions.length === 1
      && upstreamWidgetActions[0]?.type === "graph.set_widget",
    "upstream node widget plan did not set one upstream widget",
  );
  assert(
    upstreamWidgetActions[0]?.payload?.node_id === 9
      && upstreamWidgetActions[0]?.payload?.widget === "steps"
      && upstreamWidgetActions[0]?.payload?.value === 24,
    "upstream node widget plan selected the wrong node or value",
  );

  const upstreamColorDryRun = await postAgentPlan("把这个节点上游节点标蓝", graph);
  assert(upstreamColorDryRun?.status === "dry_run", "upstream node color plan did not return dry_run");
  const upstreamColorActions = upstreamColorDryRun.plan?.actions || [];
  assert(
    upstreamColorActions.length === 5
      && upstreamColorActions.every((action) => action.type === "graph.set_color" && action.payload?.color === "#4f8cff"),
    "upstream node color plan did not color upstream nodes blue",
  );
  assert(
    JSON.stringify(upstreamColorActions.map((action) => action.payload?.node_id)) === JSON.stringify([1, 3, 4, 9, 8]),
    "upstream node color plan selected the wrong nodes",
  );

  const downstreamAlignDryRun = await postAgentPlan("把 KSampler 后面的节点纵向对齐", graph);
  assert(downstreamAlignDryRun?.status === "dry_run", "downstream node align plan did not return dry_run");
  const downstreamAlignActions = downstreamAlignDryRun.plan?.actions || [];
  assert(
    downstreamAlignActions.length === 2
      && downstreamAlignActions.every((action) => action.type === "graph.set_position"),
    "downstream node align plan did not position downstream nodes",
  );
  assert(
    downstreamAlignActions.some((action) => (
      action.payload?.node_id === 8
      && JSON.stringify(action.payload?.pos) === JSON.stringify([440, 160])
    ))
      && downstreamAlignActions.some((action) => (
        action.payload?.node_id === 10
        && JSON.stringify(action.payload?.pos) === JSON.stringify([440, 160])
      ))
      && !downstreamAlignActions.some((action) => action.payload?.node_id === 9),
    "downstream node align plan selected the wrong nodes or positions",
  );

  const upstreamDistributeDryRun = await postAgentPlan("把这个节点上游节点纵向等间距排列", graph);
  assert(upstreamDistributeDryRun?.status === "dry_run", "upstream node distribute plan did not return dry_run");
  const upstreamDistributeActions = upstreamDistributeDryRun.plan?.actions || [];
  assert(
    upstreamDistributeActions.length === 5
      && upstreamDistributeActions.every((action) => action.type === "graph.set_position"),
    "upstream node distribute plan did not position upstream nodes",
  );
  const upstreamDistributeExpected = new Map([
    [1, [0, 100]],
    [9, [220, 180]],
    [8, [440, 260]],
    [3, [0, 340]],
    [4, [0, 420]],
  ]);
  for (const [nodeId, pos] of upstreamDistributeExpected) {
    const action = upstreamDistributeActions.find((row) => row.payload?.node_id === nodeId);
    assert(action, `upstream node distribute plan did not include node ${nodeId}`);
    assert(
      JSON.stringify(action.payload?.pos) === JSON.stringify(pos),
      `upstream node distribute plan positioned node ${nodeId} incorrectly`,
    );
  }

  const downstreamMoveDryRun = await postAgentPlan("把 KSampler 后面的节点往右移动 100", graph);
  assert(downstreamMoveDryRun?.status === "dry_run", "downstream node move plan did not return dry_run");
  const downstreamMoveActions = downstreamMoveDryRun.plan?.actions || [];
  assert(
    downstreamMoveActions.length === 2
      && downstreamMoveActions.every((action) => action.type === "graph.set_position"),
    "downstream node move plan did not move downstream nodes",
  );
  assert(
    downstreamMoveActions.some((action) => (
      action.payload?.node_id === 8
      && JSON.stringify(action.payload?.pos) === JSON.stringify([540, 160])
    ))
      && downstreamMoveActions.some((action) => (
        action.payload?.node_id === 10
        && JSON.stringify(action.payload?.pos) === JSON.stringify([760, 160])
      ))
      && !downstreamMoveActions.some((action) => action.payload?.node_id === 9),
    "downstream node move plan selected the wrong nodes or positions",
  );

  const upstreamMoveDryRun = await postAgentPlan("把这个节点上游节点往上移动 40", graph);
  assert(upstreamMoveDryRun?.status === "dry_run", "upstream node move plan did not return dry_run");
  const upstreamMoveActions = upstreamMoveDryRun.plan?.actions || [];
  assert(
    upstreamMoveActions.length === 5
      && upstreamMoveActions.every((action) => action.type === "graph.set_position"),
    "upstream node move plan did not move upstream nodes",
  );
  const upstreamMoveExpected = new Map([
    [1, [0, 60]],
    [3, [0, 220]],
    [4, [0, 380]],
    [9, [220, 120]],
    [8, [440, 120]],
  ]);
  for (const [nodeId, pos] of upstreamMoveExpected) {
    const action = upstreamMoveActions.find((row) => row.payload?.node_id === nodeId);
    assert(action, `upstream node move plan did not include node ${nodeId}`);
    assert(
      JSON.stringify(action.payload?.pos) === JSON.stringify(pos),
      `upstream node move plan positioned node ${nodeId} incorrectly`,
    );
  }

  summary.downstream_mode_plan = {
    muted: downstreamActions.map((action) => action.payload),
    risk_level: downstreamDryRun.plan.risk_level,
  };
  summary.downstream_color_plan = {
    colored: downstreamColorActions.map((action) => action.payload),
    risk_level: downstreamColorDryRun.plan.risk_level,
  };
  summary.downstream_delete_plan = {
    deleted: downstreamDeleteActions.map((action) => action.payload),
    risk_level: downstreamDeleteDryRun.plan.risk_level,
  };
  summary.upstream_select_plan = {
    selected: upstreamAction.payload.node_ids,
    risk_level: upstreamDryRun.plan.risk_level,
  };
  summary.upstream_duplicate_plan = {
    duplicated: upstreamDuplicateActions.map((action) => action.payload),
    risk_level: upstreamDuplicateDryRun.plan.risk_level,
  };
  summary.downstream_disconnect_plan = {
    disconnected: downstreamDisconnectActions.map((action) => action.payload),
    risk_level: downstreamDisconnectDryRun.plan.risk_level,
  };
  summary.upstream_disconnect_plan = {
    disconnected: upstreamDisconnectActions.map((action) => action.payload),
    risk_level: upstreamDisconnectDryRun.plan.risk_level,
  };
  summary.downstream_widget_plan = {
    edited: downstreamWidgetActions.map((action) => action.payload),
    risk_level: downstreamWidgetDryRun.plan.risk_level,
  };
  summary.upstream_widget_plan = {
    edited: upstreamWidgetActions.map((action) => action.payload),
    risk_level: upstreamWidgetDryRun.plan.risk_level,
  };
  summary.upstream_color_plan = {
    colored: upstreamColorActions.map((action) => action.payload),
    risk_level: upstreamColorDryRun.plan.risk_level,
  };
  summary.downstream_align_plan = {
    aligned: downstreamAlignActions.map((action) => action.payload),
    risk_level: downstreamAlignDryRun.plan.risk_level,
  };
  summary.upstream_distribute_plan = {
    distributed: upstreamDistributeActions.map((action) => action.payload),
    risk_level: upstreamDistributeDryRun.plan.risk_level,
  };
  summary.downstream_move_plan = {
    moved: downstreamMoveActions.map((action) => action.payload),
    risk_level: downstreamMoveDryRun.plan.risk_level,
  };
  summary.upstream_move_plan = {
    moved: upstreamMoveActions.map((action) => action.payload),
    risk_level: upstreamMoveDryRun.plan.risk_level,
  };
}

async function runNodeSizePlanFlow(summary) {
  const graph = {
    nodes: [
      { id: 7, type: "CLIPTextEncode", title: "Prompt", selected: true, size: [200, 100] },
      { id: 9, type: "KSampler", title: "KSampler", size: [260, 140] },
    ],
    links: [],
    node_types: [],
  };

  const selectedDryRun = await postAgentPlan("把这个节点框大小改成 420x260", graph);
  assert(selectedDryRun?.status === "dry_run", "selected node size plan did not return dry_run");
  const selectedAction = selectedDryRun.plan?.actions?.find((row) => row.type === "graph.set_size");
  assert(selectedAction?.payload?.node_id === 7, "selected node size plan targeted the wrong node");
  assert(
    JSON.stringify(selectedAction.payload.size) === JSON.stringify([420, 260]),
    "selected node size plan used the wrong size",
  );

  const titledDryRun = await postAgentPlan("resize KSampler node box to 360 x 180", graph);
  assert(titledDryRun?.status === "dry_run", "titled node size plan did not return dry_run");
  const titledAction = titledDryRun.plan?.actions?.find((row) => row.type === "graph.set_size");
  assert(titledAction?.payload?.node_id === 9, "titled node size plan targeted the wrong node");
  assert(
    JSON.stringify(titledAction.payload.size) === JSON.stringify([360, 180]),
    "titled node size plan used the wrong size",
  );

  summary.node_size_plan = {
    selected: selectedAction.payload,
    titled: titledAction.payload,
    risk_level: selectedDryRun.plan.risk_level,
  };
}

async function runSamplerMultiplierPlanFlow(summary) {
  const graph = {
    nodes: [
      {
        id: 9,
        type: "KSampler",
        title: "KSampler",
        widgets: [
          { name: "steps", value: 20 },
          { name: "cfg", value: 7.0 },
        ],
      },
      {
        id: 10,
        type: "KSampler",
        title: "Refiner KSampler",
        widgets: [
          { name: "steps", value: 12 },
          { name: "cfg", value: 5.0 },
        ],
      },
    ],
    links: [],
    node_types: [],
  };
  const cfgDryRun = await postAgentPlan("把所有 KSampler 的 cfg 减半", graph);
  assert(cfgDryRun?.status === "dry_run", "sampler cfg multiplier plan did not return dry_run");
  const cfgActions = cfgDryRun.plan?.actions || [];
  assert(
    cfgActions.some((action) => action.payload?.node_id === 9 && action.payload?.widget === "cfg" && action.payload?.value === 3.5),
    "sampler cfg multiplier plan did not halve the base sampler",
  );
  assert(
    cfgActions.some((action) => action.payload?.node_id === 10 && action.payload?.widget === "cfg" && action.payload?.value === 2.5),
    "sampler cfg multiplier plan did not halve the refiner sampler",
  );

  const stepsDryRun = await postAgentPlan("把所有 KSampler 的步数翻倍", graph);
  assert(stepsDryRun?.status === "dry_run", "sampler steps multiplier plan did not return dry_run");
  const stepActions = stepsDryRun.plan?.actions || [];
  assert(
    stepActions.some((action) => action.payload?.node_id === 9 && action.payload?.widget === "steps" && action.payload?.value === 40),
    "sampler steps multiplier plan did not double the base sampler",
  );
  assert(
    stepActions.some((action) => action.payload?.node_id === 10 && action.payload?.widget === "steps" && action.payload?.value === 24),
    "sampler steps multiplier plan did not double the refiner sampler",
  );

  summary.sampler_multiplier_plan = {
    cfg: cfgActions.map((action) => action.payload),
    steps: stepActions.map((action) => action.payload),
    risk_level: cfgDryRun.plan.risk_level,
  };
}

async function runSamplerNaturalPhrasePlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "让 KSampler 用 30 步",
    {
      nodes: [
        {
          id: 9,
          type: "KSampler",
          title: "KSampler",
          widgets: [
            { name: "steps", value: 20 },
            { name: "cfg", value: 7.0 },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "sampler natural phrase plan did not return dry_run");
  const action = dryRun.plan?.actions?.find((row) => row.type === "graph.set_widget");
  assert(action?.payload?.node_id === 9, "sampler natural phrase plan targeted the wrong node");
  assert(action?.payload?.widget === "steps", "sampler natural phrase plan targeted the wrong widget");
  assert(action?.payload?.value === 30, "sampler natural phrase plan used the wrong step count");

  summary.sampler_natural_phrase_plan = {
    node_id: action.payload.node_id,
    widget: action.payload.widget,
    value: action.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runSamplerCompactUsePlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "让 KSampler 用 30 步，CFG 7.5",
    {
      nodes: [
        {
          id: 9,
          type: "KSampler",
          title: "KSampler",
          widgets: [
            { name: "steps", value: 20 },
            { name: "cfg", value: 7.0 },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "sampler compact use plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  assert(
    actions.some((row) => row.payload?.node_id === 9 && row.payload?.widget === "steps" && row.payload?.value === 30),
    "sampler compact use plan did not set steps",
  );
  assert(
    actions.some((row) => row.payload?.node_id === 9 && row.payload?.widget === "cfg" && row.payload?.value === 7.5),
    "sampler compact use plan did not set cfg",
  );

  summary.sampler_compact_use_plan = {
    actions: actions.map((action) => action.payload),
    risk_level: dryRun.plan.risk_level,
  };
}

async function runSamplerCompactStringPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "KSampler 采样方法 dpmpp_2m，调度方式 karras",
    {
      nodes: [
        {
          id: 9,
          type: "KSampler",
          title: "KSampler",
          widgets: [
            { name: "sampler_name", value: "euler" },
            { name: "scheduler", value: "normal" },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "sampler compact string plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  assert(
    actions.some((row) => row.payload?.node_id === 9 && row.payload?.widget === "sampler_name" && row.payload?.value === "dpmpp_2m"),
    "sampler compact string plan did not set sampler_name",
  );
  assert(
    actions.some((row) => row.payload?.node_id === 9 && row.payload?.widget === "scheduler" && row.payload?.value === "karras"),
    "sampler compact string plan did not set scheduler",
  );

  summary.sampler_compact_string_plan = {
    actions: actions.map((action) => action.payload),
    risk_level: dryRun.plan.risk_level,
  };
}

async function runOrdinalNodePlanFlow(summary) {
  const graph = {
    nodes: [
      {
        id: 9,
        type: "KSampler",
        title: "Base KSampler",
        pos: [10, 20],
        widgets: [{ name: "cfg", value: 7.0 }],
      },
      {
        id: 10,
        type: "KSampler",
        title: "Refiner KSampler",
        pos: [400, 80],
        widgets: [{ name: "cfg", value: 5.0 }],
      },
    ],
    links: [],
    node_types: [],
  };

  const widgetDryRun = await postAgentPlan("把第二个 KSampler 的 cfg 改成 4", graph);
  assert(widgetDryRun?.status === "dry_run", "ordinal widget plan did not return dry_run");
  const widgetAction = widgetDryRun.plan?.actions?.find((row) => row.type === "graph.set_widget");
  assert(widgetAction?.payload?.node_id === 10, "ordinal widget plan targeted the wrong node");
  assert(widgetAction?.payload?.widget === "cfg", "ordinal widget plan targeted the wrong widget");
  assert(widgetAction?.payload?.value === 4.0, "ordinal widget plan used the wrong value");

  const modeDryRun = await postAgentPlan("禁用第二个 KSampler 节点", graph);
  assert(modeDryRun?.status === "dry_run", "ordinal mode plan did not return dry_run");
  const modeAction = modeDryRun.plan?.actions?.find((row) => row.type === "graph.set_mode");
  assert(modeAction?.payload?.node_id === 10, "ordinal mode plan targeted the wrong node");
  assert(modeAction?.payload?.mode === "mute", "ordinal mode plan used the wrong mode");

  const positionDryRun = await postAgentPlan("把第一个 KSampler 移到第二个 KSampler 右边", graph);
  assert(positionDryRun?.status === "dry_run", "ordinal position plan did not return dry_run");
  const positionAction = positionDryRun.plan?.actions?.find((row) => row.type === "graph.set_position");
  assert(positionAction?.payload?.node_id === 9, "ordinal position plan targeted the wrong node");
  assert(
    JSON.stringify(positionAction.payload.pos) === JSON.stringify([620, 80]),
    "ordinal position plan used the wrong position",
  );

  summary.ordinal_node_plan = {
    widget: widgetAction.payload,
    mode: modeAction.payload,
    position: positionAction.payload,
    risk_level: widgetDryRun.plan.risk_level,
  };
}

async function runLoraInsertPlanFlow(summary) {
  const graph = {
    nodes: [
      {
        id: 1,
        type: "CheckpointLoaderSimple",
        title: "Checkpoint",
        outputs: [
          { name: "MODEL", type: "MODEL" },
          { name: "CLIP", type: "CLIP" },
        ],
      },
      {
        id: 9,
        type: "KSampler",
        title: "KSampler",
        inputs: [{ name: "model", type: "MODEL" }],
      },
    ],
    links: [],
    node_types: [
      {
        type: "LoraLoader",
        title: "Load LoRA",
        inputs: [
          { name: "model", type: "MODEL" },
          { name: "clip", type: "CLIP" },
        ],
        outputs: [
          { name: "MODEL", type: "MODEL" },
          { name: "CLIP", type: "CLIP" },
        ],
        input: {
          required: {
            lora_name: [["detail.safetensors"], {}],
            strength_model: ["FLOAT", {}],
          },
        },
        input_order: { required: ["lora_name", "strength_model"] },
      },
    ],
  };

  const reversedDryRun = await postAgentPlan("把 LoRA 插到 Checkpoint 和 KSampler 之间", graph);
  assert(reversedDryRun?.status === "dry_run", "LoRA reversed insert plan did not return dry_run");
  const reversedActions = reversedDryRun.plan?.actions || [];
  const reversedAdd = reversedActions.find((action) => action.type === "graph.add_node");
  const reversedConnects = reversedActions.filter((action) => action.type === "graph.connect");
  assert(reversedAdd?.payload?.node_type === "LoraLoader", "LoRA reversed insert plan did not add LoraLoader");
  assert(reversedAdd?.payload?.ref === "new_node", "LoRA reversed insert plan must name the new node ref");
  assert(reversedConnects.length === 2, "LoRA reversed insert plan did not produce two connect actions");

  const widgetDryRun = await postAgentPlan(
    "在 Checkpoint 和 KSampler 之间插入 LoRA 节点，LoRA 用 detail.safetensors，强度 0.7",
    graph,
  );
  assert(widgetDryRun?.status === "dry_run", "LoRA widget insert plan did not return dry_run");
  const widgetAdd = widgetDryRun.plan?.actions?.find((action) => action.type === "graph.add_node");
  assert(widgetAdd?.payload?.node_type === "LoraLoader", "LoRA widget insert plan did not add LoraLoader");
  assert(
    widgetAdd.payload.widgets?.lora_name === "detail.safetensors",
    "LoRA widget insert plan did not set lora_name",
  );
  assert(widgetAdd.payload.widgets?.strength_model === 0.7, "LoRA widget insert plan did not set strength_model");

  summary.lora_insert_plan = {
    reversed: {
      node_type: reversedAdd.payload.node_type,
      connect_count: reversedConnects.length,
    },
    widgets: widgetAdd.payload.widgets,
    risk_level: widgetDryRun.plan.risk_level,
  };
}

async function runPromptRemovePlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "把正向提示词里的 watermark 去掉",
    {
      nodes: [
        {
          id: 7,
          type: "CLIPTextEncode",
          title: "Positive Prompt",
          widgets: [{ name: "text", value: "portrait, watermark, cinematic" }],
        },
        {
          id: 8,
          type: "CLIPTextEncode",
          title: "Negative Prompt",
          widgets: [{ name: "text", value: "blurry" }],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "prompt remove plan did not return dry_run");
  const action = dryRun.plan?.actions?.find((row) => row.type === "graph.set_widget");
  assert(action?.payload?.node_id === 7, "prompt remove plan targeted the wrong node");
  assert(action?.payload?.widget === "text", "prompt remove plan targeted the wrong widget");
  assert(action?.payload?.value === "portrait, cinematic", "prompt remove plan produced the wrong text");

  summary.prompt_remove_plan = {
    node_id: action.payload.node_id,
    widget: action.payload.widget,
    value: action.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runIpAdapterTimingPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "把 IPAdapter 的权重改成 0.7，开始时间改成 0.1，结束时间改成 0.8",
    {
      nodes: [
        {
          id: 50,
          type: "IPAdapterAdvanced",
          title: "IPAdapter Advanced",
          widgets: [
            { name: "weight", value: 1.0 },
            { name: "start_at", value: 0.0 },
            { name: "end_at", value: 1.0 },
            { name: "weight_type", value: "linear" },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "IPAdapter timing plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const weightAction = actions.find((action) => action.payload?.widget === "weight");
  const startAction = actions.find((action) => action.payload?.widget === "start_at");
  const endAction = actions.find((action) => action.payload?.widget === "end_at");
  assert(weightAction?.payload?.value === 0.7, "IPAdapter timing plan used wrong weight");
  assert(startAction?.payload?.value === 0.1, "IPAdapter timing plan used wrong start_at");
  assert(endAction?.payload?.value === 0.8, "IPAdapter timing plan used wrong end_at");

  summary.ipadapter_timing_plan = {
    weight: weightAction.payload.value,
    start_at: startAction.payload.value,
    end_at: endAction.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runControlNetNaturalTimingPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "ControlNet 强度 0.75，开始 0.1，结束 0.8",
    {
      nodes: [
        {
          id: 40,
          type: "ControlNetApplyAdvanced",
          title: "Apply ControlNet",
          widgets: [
            { name: "strength", value: 1.0 },
            { name: "start_percent", value: 0.0 },
            { name: "end_percent", value: 1.0 },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "ControlNet natural timing plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const strengthAction = actions.find((action) => action.payload?.widget === "strength");
  const startAction = actions.find((action) => action.payload?.widget === "start_percent");
  const endAction = actions.find((action) => action.payload?.widget === "end_percent");
  assert(strengthAction?.payload?.value === 0.75, "ControlNet natural timing plan used wrong strength");
  assert(startAction?.payload?.value === 0.1, "ControlNet natural timing plan used wrong start_percent");
  assert(endAction?.payload?.value === 0.8, "ControlNet natural timing plan used wrong end_percent");

  summary.controlnet_natural_timing_plan = {
    strength: strengthAction.payload.value,
    start_percent: startAction.payload.value,
    end_percent: endAction.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runIpAdapterModelTimingPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "IPAdapter 用 plus-face.safetensors，权重 0.7，开始时间 0.1，结束时间 0.8",
    {
      nodes: [
        {
          id: 50,
          type: "IPAdapterAdvanced",
          title: "IPAdapter Advanced",
          widgets: [
            { name: "ipadapter_file", value: "old.safetensors" },
            { name: "weight", value: 1.0 },
            { name: "start_at", value: 0.0 },
            { name: "end_at", value: 1.0 },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "IPAdapter model timing plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const fileAction = actions.find((action) => action.payload?.widget === "ipadapter_file");
  const weightAction = actions.find((action) => action.payload?.widget === "weight");
  const startAction = actions.find((action) => action.payload?.widget === "start_at");
  const endAction = actions.find((action) => action.payload?.widget === "end_at");
  assert(fileAction?.payload?.value === "plus-face.safetensors", "IPAdapter model timing plan used wrong file");
  assert(weightAction?.payload?.value === 0.7, "IPAdapter model timing plan used wrong weight");
  assert(startAction?.payload?.value === 0.1, "IPAdapter model timing plan used wrong start_at");
  assert(endAction?.payload?.value === 0.8, "IPAdapter model timing plan used wrong end_at");

  summary.ipadapter_model_timing_plan = {
    file: fileAction.payload.value,
    weight: weightAction.payload.value,
    start_at: startAction.payload.value,
    end_at: endAction.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runLatentSizeBatchPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "Empty Latent 设成 1024x576，batch 4",
    {
      nodes: [
        {
          id: 4,
          type: "EmptyLatentImage",
          title: "Empty Latent Image",
          widgets: [
            { name: "width", value: 512 },
            { name: "height", value: 512 },
            { name: "batch_size", value: 1 },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "latent size/batch plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const widthAction = actions.find((action) => action.payload?.widget === "width");
  const heightAction = actions.find((action) => action.payload?.widget === "height");
  const batchAction = actions.find((action) => action.payload?.widget === "batch_size");
  assert(widthAction?.payload?.value === 1024, "latent size/batch plan used wrong width");
  assert(heightAction?.payload?.value === 576, "latent size/batch plan used wrong height");
  assert(batchAction?.payload?.value === 4, "latent size/batch plan used wrong batch_size");

  summary.latent_size_batch_plan = {
    width: widthAction.payload.value,
    height: heightAction.payload.value,
    batch_size: batchAction.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runVideoCombineLoopPlanFlow(summary) {
  const dryRun = await postAgentPlan(
    "把 Video Combine 的循环次数改成 2，帧率改成 24，保存前缀改成 renders/shot-a",
    {
      nodes: [
        {
          id: 42,
          type: "VHS_VideoCombine",
          title: "Video Combine",
          widgets: [
            { name: "frame_rate", value: 8 },
            { name: "loop_count", value: 0 },
            { name: "filename_prefix", value: "ComfyUI" },
          ],
        },
      ],
      links: [],
      node_types: [],
    },
  );
  assert(dryRun?.status === "dry_run", "Video Combine loop plan did not return dry_run");
  const actions = dryRun.plan?.actions || [];
  const loopAction = actions.find((action) => action.payload?.widget === "loop_count");
  const frameRateAction = actions.find((action) => action.payload?.widget === "frame_rate");
  const prefixAction = actions.find((action) => action.payload?.widget === "filename_prefix");
  assert(loopAction?.payload?.value === 2, "Video Combine loop plan used wrong loop_count");
  assert(frameRateAction?.payload?.value === 24, "Video Combine loop plan used wrong frame_rate");
  assert(prefixAction?.payload?.value === "renders/shot-a", "Video Combine loop plan used wrong filename_prefix");

  summary.video_combine_loop_plan = {
    loop_count: loopAction.payload.value,
    frame_rate: frameRateAction.payload.value,
    filename_prefix: prefixAction.payload.value,
    risk_level: dryRun.plan.risk_level,
  };
}

async function runRegisteredNodePlanFlow(client, summary) {
  const registry = await pageCall(client, () => {
    const registered = globalThis.LiteGraph?.registered_node_types || {};
    const videoCombineInputs = registered.VHS_VideoCombine?.nodeData?.input_order?.required || [];
    const clipTextOutputs = registered.CLIPTextEncode?.nodeData?.output || [];
    return {
      count: Object.keys(registered).length,
      has_save_image: Boolean(registered.SaveImage),
      has_preview_image: Boolean(registered.PreviewImage),
      has_video_combine: Boolean(registered.VHS_VideoCombine),
      has_clip_text_encode: Boolean(registered.CLIPTextEncode),
      video_combine_inputs: videoCombineInputs,
      clip_text_outputs: clipTextOutputs,
    };
  });
  assert(registry.count > 0, "LiteGraph registered_node_types is empty");
  assert(registry.has_save_image, "SaveImage node type is not registered");
  assert(registry.has_preview_image, "PreviewImage node type is not registered");
  assert(registry.has_video_combine, "VHS_VideoCombine node type is not registered");
  assert(registry.has_clip_text_encode, "CLIPTextEncode node type is not registered");
  assert(registry.video_combine_inputs.includes("loop_count"), "VHS_VideoCombine loop_count input is not in nodeData");
  assert(registry.clip_text_outputs.includes("CONDITIONING"), "CLIPTextEncode CONDITIONING output is not in nodeData");

  await setInput(client, "添加一个 Save Image 节点");
  await clickById(client, "agent-workbench-plan");
  const dryRun = await waitForOutput(
    client,
    "registered node add dry-run",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "graph.add_node"),
  );
  const addAction = dryRun.plan.actions.find((action) => action.type === "graph.add_node");
  assert(addAction.payload.node_type === "SaveImage", "Save Image display title did not resolve to SaveImage");
  await clickById(client, "agent-workbench-cancel");
  await waitForOutput(client, "registered node add cancel output", (payload) => payload?.error === "user_cancelled");

  await setInput(client, "添加 Video Combine 节点，loop count 改成 2");
  await clickById(client, "agent-workbench-plan");
  const schemaDryRun = await waitForOutput(
    client,
    "registered node schema add dry-run",
    (payload) => payload?.status === "dry_run" && hasAction(payload, "graph.add_node"),
  );
  const schemaAddAction = schemaDryRun.plan.actions.find((action) => action.type === "graph.add_node");
  assert(
    schemaAddAction.payload.node_type === "VHS_VideoCombine",
    "Video Combine display title did not resolve to VHS_VideoCombine",
  );
  assert(
    schemaAddAction.payload.widgets?.loop_count === 2,
    `Video Combine loop_count schema widget was not planned: ${JSON.stringify(schemaAddAction.payload.widgets || {})}`,
  );
  await clickById(client, "agent-workbench-cancel");
  const schemaCancelled = await waitForOutput(
    client,
    "registered node schema add cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "添加一个正向提示词节点，内容写成 neon skyline，并把它接到 KSampler 的 positive");
  await clickById(client, "agent-workbench-plan");
  const newToExistingDryRun = await waitForOutput(
    client,
    "new node to existing node dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && hasAction(payload, "graph.add_node")
      && hasAction(payload, "graph.connect")
    ),
  );
  const newToExistingAdd = newToExistingDryRun.plan.actions.find((action) => action.type === "graph.add_node");
  const newToExistingConnect = newToExistingDryRun.plan.actions.find((action) => action.type === "graph.connect");
  assert(newToExistingAdd.payload.ref === "new_node", "new-to-existing add plan must name the new node ref");
  assert(
    newToExistingConnect.payload.origin_node_ref === "new_node",
    "new-to-existing connect plan must use the new node as origin ref",
  );
  assert(
    newToExistingConnect.payload.target_slot === 1,
    `new-to-existing connect plan did not target KSampler positive slot: ${JSON.stringify(newToExistingConnect.payload)}`,
  );
  await clickById(client, "agent-workbench-cancel");
  const newToExistingCancelled = await waitForOutput(
    client,
    "new node to existing node cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "在 KSampler 和 Save Image 之间插入 VAE 解码节点");
  await clickById(client, "agent-workbench-plan");
  const insertDryRun = await waitForOutput(
    client,
    "insert node between existing nodes dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && Array.isArray(payload.plan?.actions)
      && payload.plan.actions.filter((action) => action.type === "graph.connect").length === 2
      && hasAction(payload, "graph.add_node")
    ),
  );
  const insertAdd = insertDryRun.plan.actions.find((action) => action.type === "graph.add_node");
  const insertConnects = insertDryRun.plan.actions.filter((action) => action.type === "graph.connect");
  assert(insertAdd.payload.node_type === "VAEDecode", "insert plan did not add VAEDecode");
  assert(insertAdd.payload.ref === "new_node", "insert add plan must name the new node ref");
  assert(
    insertConnects.some((action) => action.payload.target_node_ref === "new_node"),
    "insert plan must connect an existing node into the new node",
  );
  assert(
    insertConnects.some((action) => action.payload.origin_node_ref === "new_node"),
    "insert plan must connect the new node into an existing node",
  );
  await clickById(client, "agent-workbench-cancel");
  const insertCancelled = await waitForOutput(
    client,
    "insert node between existing nodes cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "在 KSampler 后面添加 VAE 解码节点");
  await clickById(client, "agent-workbench-plan");
  const addAfterDryRun = await waitForOutput(
    client,
    "add node after existing node dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && hasAction(payload, "graph.add_node")
      && hasAction(payload, "graph.connect")
    ),
  );
  const addAfterAdd = addAfterDryRun.plan.actions.find((action) => action.type === "graph.add_node");
  const addAfterConnect = addAfterDryRun.plan.actions.find((action) => action.type === "graph.connect");
  assert(addAfterAdd.payload.node_type === "VAEDecode", "add-after plan did not add VAEDecode");
  assert(addAfterAdd.payload.ref === "new_node", "add-after add plan must name the new node ref");
  assert(
    addAfterConnect.payload.target_node_ref === "new_node",
    "add-after connect plan must connect the existing node into the new node",
  );
  await clickById(client, "agent-workbench-cancel");
  const addAfterCancelled = await waitForOutput(
    client,
    "add node after existing node cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "在 Save Image 前面添加 VAE 解码节点");
  await clickById(client, "agent-workbench-plan");
  const addBeforeDryRun = await waitForOutput(
    client,
    "add node before existing node dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && hasAction(payload, "graph.add_node")
      && hasAction(payload, "graph.connect")
    ),
  );
  const addBeforeAdd = addBeforeDryRun.plan.actions.find((action) => action.type === "graph.add_node");
  const addBeforeConnect = addBeforeDryRun.plan.actions.find((action) => action.type === "graph.connect");
  assert(addBeforeAdd.payload.node_type === "VAEDecode", "add-before plan did not add VAEDecode");
  assert(addBeforeAdd.payload.ref === "new_node", "add-before add plan must name the new node ref");
  assert(
    addBeforeConnect.payload.origin_node_ref === "new_node",
    "add-before connect plan must connect the new node into the existing node",
  );
  await clickById(client, "agent-workbench-cancel");
  const addBeforeCancelled = await waitForOutput(
    client,
    "add node before existing node cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "把 Save Image 节点替换成 Preview Image 节点");
  await clickById(client, "agent-workbench-plan");
  const replaceDryRun = await waitForOutput(
    client,
    "replace node dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && hasAction(payload, "graph.add_node")
      && hasAction(payload, "graph.connect")
      && hasAction(payload, "graph.delete_node")
    ),
  );
  const replaceAdd = replaceDryRun.plan.actions.find((action) => action.type === "graph.add_node");
  const replaceConnects = replaceDryRun.plan.actions.filter((action) => action.type === "graph.connect");
  const replaceDelete = replaceDryRun.plan.actions.find((action) => action.type === "graph.delete_node");
  assert(replaceAdd.payload.node_type === "PreviewImage", "replace plan did not add PreviewImage");
  assert(replaceAdd.payload.ref === "replacement_node", "replace add plan must name the replacement node ref");
  assert(
    replaceConnects.some((action) => action.payload.target_node_ref === "replacement_node"),
    "replace plan must move incoming links to the replacement node",
  );
  assert(Number.isInteger(replaceDelete.payload.node_id), "replace plan must delete the old node by id");
  await clickById(client, "agent-workbench-cancel");
  const replaceCancelled = await waitForOutput(
    client,
    "replace node cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "把 VAE Decode 改接到 Save Image");
  await clickById(client, "agent-workbench-plan");
  const rerouteDryRun = await waitForOutput(
    client,
    "reroute node output dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && hasAction(payload, "graph.disconnect")
      && hasAction(payload, "graph.connect")
    ),
  );
  const rerouteDisconnect = rerouteDryRun.plan.actions.find((action) => action.type === "graph.disconnect");
  const rerouteConnect = rerouteDryRun.plan.actions.find((action) => action.type === "graph.connect");
  assert(
    Number.isInteger(rerouteDisconnect.payload.origin_node_id),
    "reroute plan must disconnect the old origin output",
  );
  assert(
    Number.isInteger(rerouteConnect.payload.target_node_id),
    "reroute plan must connect to a concrete target node",
  );
  await clickById(client, "agent-workbench-cancel");
  const rerouteCancelled = await waitForOutput(
    client,
    "reroute node output cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  await setInput(client, "把 Save Image 的 images 输入改接到 VAE Decode");
  await clickById(client, "agent-workbench-plan");
  const rerouteInputDryRun = await waitForOutput(
    client,
    "reroute target input dry-run",
    (payload) => (
      payload?.status === "dry_run"
      && hasAction(payload, "graph.disconnect")
      && hasAction(payload, "graph.connect")
    ),
  );
  const rerouteInputDisconnect = rerouteInputDryRun.plan.actions.find((action) => action.type === "graph.disconnect");
  const rerouteInputConnect = rerouteInputDryRun.plan.actions.find((action) => action.type === "graph.connect");
  assert(
    Number.isInteger(rerouteInputDisconnect.payload.target_node_id),
    "input reroute plan must disconnect the target input",
  );
  assert(
    Number.isInteger(rerouteInputDisconnect.payload.target_slot),
    "input reroute plan must disconnect a concrete target slot",
  );
  assert(
    rerouteInputConnect.payload.target_node_id === rerouteInputDisconnect.payload.target_node_id,
    "input reroute plan must reconnect the same target node",
  );
  assert(
    rerouteInputConnect.payload.target_slot === rerouteInputDisconnect.payload.target_slot,
    "input reroute plan must reconnect the same target slot",
  );
  await clickById(client, "agent-workbench-cancel");
  const rerouteInputCancelled = await waitForOutput(
    client,
    "reroute target input cancel output",
    (payload) => payload?.error === "user_cancelled",
  );

  summary.registered_node_plan = {
    registered_node_type_count: registry.count,
    node_type: addAction.payload.node_type,
    schema_node_type: schemaAddAction.payload.node_type,
    schema_widgets: schemaAddAction.payload.widgets,
    new_to_existing: {
      node_type: newToExistingAdd.payload.node_type,
      widgets: newToExistingAdd.payload.widgets,
      origin_ref: newToExistingConnect.payload.origin_node_ref,
      target_node_id: newToExistingConnect.payload.target_node_id,
      target_slot: newToExistingConnect.payload.target_slot,
      cancelled: newToExistingCancelled.error,
    },
    insert_between: {
      node_type: insertAdd.payload.node_type,
      incoming: insertConnects.find((action) => action.payload.target_node_ref === "new_node")?.payload,
      outgoing: insertConnects.find((action) => action.payload.origin_node_ref === "new_node")?.payload,
      cancelled: insertCancelled.error,
    },
    add_after: {
      node_type: addAfterAdd.payload.node_type,
      connect: addAfterConnect.payload,
      cancelled: addAfterCancelled.error,
    },
    add_before: {
      node_type: addBeforeAdd.payload.node_type,
      connect: addBeforeConnect.payload,
      cancelled: addBeforeCancelled.error,
    },
    replace_node: {
      node_type: replaceAdd.payload.node_type,
      incoming: replaceConnects.find((action) => action.payload.target_node_ref === "replacement_node")?.payload,
      deleted_node_id: replaceDelete.payload.node_id,
      cancelled: replaceCancelled.error,
    },
    reroute_output: {
      disconnect: rerouteDisconnect.payload,
      connect: rerouteConnect.payload,
      cancelled: rerouteCancelled.error,
    },
    reroute_input: {
      disconnect: rerouteInputDisconnect.payload,
      connect: rerouteInputConnect.payload,
      cancelled: rerouteInputCancelled.error,
    },
    cancelled: schemaCancelled.error,
  };
}

function removeGraphNodeById(nodeId) {
  const comfyApp = globalThis.app || globalThis.comfyAPI?.app;
  const graph = comfyApp?.graph || comfyApp?.canvas?.graph;
  const node = graph?.getNodeById?.(nodeId) || (graph?._nodes || graph?.nodes || []).find((item) => String(item.id) === String(nodeId));
  if (!node) {
    return { ok: true, removed: false, nodeId };
  }
  if (typeof graph?.remove !== "function") {
    return { ok: false, error: "Graph remove is unavailable", nodeId };
  }
  graph.remove(node);
  comfyApp?.canvas?.setDirty?.(true, true);
  graph?.setDirtyCanvas?.(true, true);
  return { ok: true, removed: true, nodeId };
}

async function runAddConnectApplyFlow(client, summary) {
  let addedNodeId = null;
  try {
    await setInput(client, "添加一个 VAE 解码节点并把 KSampler 接到它");
    await clickById(client, "agent-workbench-plan");
    const dryRun = await waitForOutput(
      client,
      "add and connect dry-run",
      (payload) => (
        payload?.status === "dry_run"
        && hasAction(payload, "graph.add_node")
        && hasAction(payload, "graph.connect")
      ),
    );
    const addAction = dryRun.plan.actions.find((action) => action.type === "graph.add_node");
    const connectAction = dryRun.plan.actions.find((action) => action.type === "graph.connect");
    assert(addAction.payload.ref === "new_node", "add+connect plan must name the new node ref");
    assert(connectAction.payload.target_node_ref === "new_node", "connect plan must target the new node ref");

    await clickById(client, "agent-workbench-apply");
    const applied = await waitForOutput(
      client,
      "add and connect apply result",
      (payload) => (
        payload?.ok === true
        && Array.isArray(payload.browser_applied)
        && payload.browser_applied.some((row) => row.type === "graph.add_node" && row.ref === "new_node")
        && payload.browser_applied.some((row) => row.type === "graph.connect")
      ),
    );
    const addRow = applied.browser_applied.find((row) => row.type === "graph.add_node");
    const connectRow = applied.browser_applied.find((row) => row.type === "graph.connect");
    addedNodeId = addRow.node_id;
    summary.add_connect_apply = {
      added_node_id: addedNodeId,
      node_type: addRow.node_type,
      ref: addRow.ref,
      origin_node_id: connectRow.origin_node_id,
      target_node_id: connectRow.target_node_id,
      target_slot: connectRow.target_slot,
    };
  } finally {
    if (addedNodeId !== null && addedNodeId !== undefined) {
      const cleanup = await pageCall(client, removeGraphNodeById, addedNodeId);
      assert(cleanup?.ok, cleanup?.error || "Could not remove temporary add/connect node");
      summary.add_connect_cleanup = cleanup;
    }
  }
}

function findEditablePromptNode() {
  const comfyApp = globalThis.app || globalThis.comfyAPI?.app;
  const graph = comfyApp?.graph || comfyApp?.canvas?.graph;
  const nodes = graph?._nodes || graph?.nodes || [];
  const promptNode = nodes.find((node) => {
    const label = `${node?.type || ""} ${node?.title || ""}`.toLowerCase();
    const isPromptNode = label.includes("cliptextencode") || label.includes("prompt") || label.includes("提示词");
    return isPromptNode && (node.widgets || []).some((widget) => widget.name === "text");
  });
  if (!promptNode) {
    return { ok: false, error: "No editable CLIPTextEncode prompt node found" };
  }
  const widget = promptNode.widgets.find((item) => item.name === "text");
  const selectedIds = nodes.filter((node) => node.selected === true).map((node) => node.id);
  for (const node of nodes) {
    node.selected = false;
  }
  promptNode.selected = true;
  if (typeof comfyApp?.canvas?.selectNode === "function") {
    comfyApp.canvas.selectNode(promptNode, false);
  }
  comfyApp?.canvas?.setDirty?.(true, true);
  graph?.setDirtyCanvas?.(true, true);
  return {
    ok: true,
    nodeId: promptNode.id,
    nodeType: promptNode.type,
    title: promptNode.title,
    widgetName: widget.name,
    originalValue: widget.value,
    selectedIds,
  };
}

function restorePromptNode(nodeId, widgetName, originalValue, selectedIds) {
  const comfyApp = globalThis.app || globalThis.comfyAPI?.app;
  const graph = comfyApp?.graph || comfyApp?.canvas?.graph;
  const nodes = graph?._nodes || graph?.nodes || [];
  const node = graph?.getNodeById?.(nodeId) || nodes.find((item) => String(item.id) === String(nodeId));
  if (!node) {
    return { ok: false, error: `Missing prompt node ${nodeId}` };
  }
  const widget = (node.widgets || []).find((item) => item.name === widgetName);
  if (!widget) {
    return { ok: false, error: `Missing prompt widget ${widgetName}` };
  }
  widget.value = originalValue;
  const selectedLookup = new Set((selectedIds || []).map((id) => String(id)));
  const selectedNodes = {};
  for (const item of nodes) {
    item.selected = selectedLookup.has(String(item.id));
    if (item.selected) {
      selectedNodes[item.id] = item;
    }
  }
  if (comfyApp?.canvas && "selected_nodes" in comfyApp.canvas) {
    comfyApp.canvas.selected_nodes = selectedNodes;
  }
  comfyApp?.canvas?.setDirty?.(true, true);
  graph?.setDirtyCanvas?.(true, true);
  return { ok: true, nodeId, widgetName, restoredValue: widget.value };
}

async function readPromptWidget(client, nodeId, widgetName) {
  return pageCall(client, (id, name) => {
    const comfyApp = globalThis.app || globalThis.comfyAPI?.app;
    const graph = comfyApp?.graph || comfyApp?.canvas?.graph;
    const node = graph?.getNodeById?.(id) || (graph?._nodes || graph?.nodes || []).find((item) => String(item.id) === String(id));
    const widget = (node?.widgets || []).find((item) => item.name === name);
    return { nodeId: node?.id, widgetName: widget?.name, value: widget?.value };
  }, nodeId, widgetName);
}

async function runPromptEditFlow(client, summary) {
  const promptNode = await pageCall(client, findEditablePromptNode);
  assert(promptNode?.ok, promptNode?.error || "Could not select prompt node");
  summary.prompt_node = {
    node_id: promptNode.nodeId,
    node_type: promptNode.nodeType,
    title: promptNode.title,
    widget: promptNode.widgetName,
  };
  try {
    await setInput(client, `prompt: ${SMOKE_PROMPT}`);
    await clickById(client, "agent-workbench-plan");
    const dryRun = await waitForOutput(
      client,
      "prompt graph edit dry-run",
      (payload) => payload?.status === "dry_run" && hasAction(payload, "graph.set_widget"),
    );
    const graphAction = dryRun.plan.actions.find((action) => action.type === "graph.set_widget");
    assert(String(graphAction.payload.node_id) === String(promptNode.nodeId), "prompt edit targeted the wrong node");
    assert(graphAction.payload.widget === promptNode.widgetName, "prompt edit targeted the wrong widget");
    assert(graphAction.payload.value === SMOKE_PROMPT, "prompt edit planned the wrong value");

    await clickById(client, "agent-workbench-apply");
    const applied = await waitForOutput(
      client,
      "prompt graph edit apply result",
      (payload) => (
        payload?.ok === true
        && Array.isArray(payload.browser_applied)
        && payload.browser_applied.some((row) => row.type === "graph.set_widget")
      ),
    );
    const edited = await readPromptWidget(client, promptNode.nodeId, promptNode.widgetName);
    assert(edited.value === SMOKE_PROMPT, "prompt widget did not change after browser_applied graph edit");
    summary.prompt_edit = {
      planned_value: graphAction.payload.value,
      applied: applied.browser_applied.find((row) => row.type === "graph.set_widget"),
      observed_value: edited.value,
    };
  } finally {
    const restore = await pageCall(
      client,
      restorePromptNode,
      promptNode.nodeId,
      promptNode.widgetName,
      promptNode.originalValue,
      promptNode.selectedIds,
    );
    assert(restore?.ok, restore?.error || "Could not restore prompt node");
    summary.prompt_restore = restore;
  }
}

async function runSmoke(client, browserInfo) {
  const summary = {
    ok: true,
    url: WORKBENCH_URL,
    cdp_port: CDP_PORT,
    launched_chromium: browserInfo.launched,
  };
  await runContextFlow(client, summary);
  await runSmokeManifestFlow(client, summary);
  await runChatTimelinePlanCardFlow(client, summary);
  await runRegisteredNodePlanFlow(client, summary);
  await runMissingNodeManagerPlanFlow(summary);
  await runModelInstallPlanFlow(summary);
  await runModelWidgetUsePlanFlow(summary);
  await runManagerQueueStatusPlanFlow(summary);
  await runManagerQueueControlPlanFlow(summary);
  await runCustomNodeReadPlanFlow(client, summary);
  await runCustomNodeStateSynonymPlanFlow(summary);
  await runCustomNodeUpdateInstalledPlanFlow(summary);
  await runServiceLogsPlanFlow(summary);
  await runCopySamplerSeedPlanFlow(summary);
  await runCopySamplerSettingsPlanFlow(summary);
  await runSamplerSchedulerPlanFlow(summary);
  await runSamplerRelativePlanFlow(summary);
  await runSamplerMultiplierPlanFlow(summary);
  await runSamplerNaturalPhrasePlanFlow(summary);
  await runSamplerCompactUsePlanFlow(summary);
  await runSamplerCompactStringPlanFlow(summary);
  await runOrdinalNodePlanFlow(summary);
  await runLoraInsertPlanFlow(summary);
  await runRelativePositionPlanFlow(summary);
  await runAutoLayoutPlanFlow(summary);
  await runCollapsedNodePlanFlow(summary);
  await runNodeModePlanFlow(summary);
  await runGraphNeighborhoodPlanFlow(summary);
  await runNodeSizePlanFlow(summary);
  await runPromptRemovePlanFlow(summary);
  await runIpAdapterTimingPlanFlow(summary);
  await runControlNetNaturalTimingPlanFlow(summary);
  await runIpAdapterModelTimingPlanFlow(summary);
  await runLatentSizeBatchPlanFlow(summary);
  await runVideoCombineLoopPlanFlow(summary);
  await runComposeCommandValuePlanFlow(client, summary);
  await runAddConnectApplyFlow(client, summary);
  await runSudoConfirmCancelApplyFlow(client, summary);
  await runPromptEditFlow(client, summary);
  return summary;
}

async function stopChromium(chromium) {
  if (!chromium) {
    return;
  }
  chromium.child.kill("SIGTERM");
  await sleep(500);
  if (!chromium.child.killed) {
    chromium.child.kill("SIGKILL");
  }
  rmSync(chromium.userDataDir, { recursive: true, force: true });
}

async function main() {
  let browserInfo = null;
  let client = null;
  try {
    browserInfo = await ensureBrowser();
    client = await connectWorkbenchPage();
    const summary = await runSmoke(client, browserInfo);
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    client?.close();
    if (browserInfo?.launched) {
      await stopChromium(browserInfo.chromium);
    }
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});

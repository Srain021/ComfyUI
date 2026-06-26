import { formatWorkbenchResponse } from "./workbench-response.mjs";

function safeText(value) {
  return typeof value === "string" ? value : "";
}

function responseTitle(response) {
  if (response?.assistant?.title) {
    return response.assistant.title;
  }
  return formatWorkbenchResponse(response || {}).title;
}

export function responseText(response) {
  if (response?.assistant?.message) {
    return response.assistant.message;
  }
  return formatWorkbenchResponse(response || {}).message;
}

function maxRisk(actions) {
  const order = ["read", "canvas", "package", "service", "elevated"];
  let best = "read";
  for (const action of actions || []) {
    const risk = action?.risk_level;
    if (order.indexOf(risk) > order.indexOf(best)) {
      best = risk;
    }
  }
  return best;
}

export function toolCardsFromResponse(response) {
  if (response?.status !== "dry_run" || !response.plan || !Array.isArray(response.plan.actions)) {
    return [];
  }
  if (
    response.plan.actions.length === 1
    && response.plan.actions[0]?.type === "context.collect"
  ) {
    return [];
  }
  return [
    {
      title: response.plan.requires_confirmation ? "需要允许" : "可执行计划",
      summary: response.plan.summary || "Agent 生成了一个可执行计划",
      requires_confirmation: Boolean(response.plan.requires_confirmation),
      plan_hash: response.plan.plan_hash,
      risk_level: response.plan.risk_level || maxRisk(response.plan.actions),
      actions: response.plan.actions,
    },
  ];
}

function appendText(parent, className, value) {
  const element = parent.ownerDocument.createElement("div");
  element.className = className;
  element.textContent = value;
  parent.append(element);
  return element;
}

function renderAttachments(parent, attachments) {
  if (!Array.isArray(attachments) || !attachments.length) {
    return;
  }
  const tray = parent.ownerDocument.createElement("div");
  tray.className = "agent-workbench-message-attachments";
  for (const attachment of attachments) {
    const chip = parent.ownerDocument.createElement("span");
    chip.className = `agent-workbench-attachment-chip agent-workbench-attachment-${attachment.kind || "file"}`;
    chip.textContent = attachment.name || attachment.kind || "attachment";
    tray.append(chip);
  }
  parent.append(tray);
}

function renderToolCard(parent, message, card, callbacks) {
  const document = parent.ownerDocument;
  const cardElement = document.createElement("section");
  cardElement.className = "agent-workbench-tool-card";
  cardElement.dataset.risk = card.risk_level || "read";

  appendText(cardElement, "agent-workbench-tool-title", card.title);
  appendText(cardElement, "agent-workbench-tool-summary", card.summary);
  appendText(cardElement, "agent-workbench-tool-risk", `风险级别: ${card.risk_level || "read"}`);

  const actions = document.createElement("ol");
  actions.className = "agent-workbench-tool-actions";
  for (const action of card.actions.slice(0, 6)) {
    const item = document.createElement("li");
    item.textContent = `${action.type}${action.capability ? ` · ${action.capability}` : ""}`;
    actions.append(item);
  }
  cardElement.append(actions);

  if (message.tool_state?.status) {
    appendText(cardElement, "agent-workbench-tool-state", message.tool_state.status);
  }

  const controls = document.createElement("div");
  controls.className = "agent-workbench-tool-controls";
  let confirmCheckbox = null;
  if (card.requires_confirmation) {
    const label = document.createElement("label");
    label.className = "agent-workbench-tool-confirm";
    confirmCheckbox = document.createElement("input");
    confirmCheckbox.type = "checkbox";
    const span = document.createElement("span");
    span.textContent = "确认允许高风险操作";
    label.append(confirmCheckbox, span);
    controls.append(label);
  }

  const allow = document.createElement("button");
  allow.type = "button";
  allow.className = "agent-workbench-tool-allow";
  allow.textContent = "允许执行";
  allow.disabled = message.tool_state?.status === "running" || message.tool_state?.status === "applied";
  if (confirmCheckbox) {
    allow.disabled = true;
    confirmCheckbox.addEventListener("change", () => {
      allow.disabled = !confirmCheckbox.checked || message.tool_state?.status === "running";
    });
  }
  allow.addEventListener("click", () => callbacks.onApplyTool?.(message, Boolean(confirmCheckbox?.checked)));

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "agent-workbench-tool-cancel";
  cancel.textContent = "取消";
  cancel.disabled = message.tool_state?.status === "running" || message.tool_state?.status === "applied";
  cancel.addEventListener("click", () => callbacks.onCancelTool?.(message));

  controls.append(allow, cancel);
  cardElement.append(controls);
  parent.append(cardElement);
}

function renderMessage(parent, message, callbacks) {
  const document = parent.ownerDocument;
  const row = document.createElement("article");
  row.className = `agent-workbench-message agent-workbench-message-${message.role}`;
  row.dataset.messageId = message.id || "";

  const title = message.role === "user" ? "你" : responseTitle(message.response);
  appendText(row, "agent-workbench-message-title", title);
  appendText(row, "agent-workbench-message-body", safeText(message.text) || responseText(message.response));
  renderAttachments(row, message.attachments);

  const cards = message.tool_state?.status === "cancelled"
    ? []
    : toolCardsFromResponse(message.response);
  for (const card of cards) {
    renderToolCard(row, message, card, callbacks);
  }

  parent.append(row);
}

export function renderChatTimeline(container, messages, callbacks = {}) {
  container.replaceChildren();
  for (const message of Array.isArray(messages) ? messages : []) {
    renderMessage(container, message, callbacks);
  }
  container.scrollTop = container.scrollHeight;
}

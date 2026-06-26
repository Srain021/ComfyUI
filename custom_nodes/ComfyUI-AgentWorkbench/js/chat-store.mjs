const DEFAULT_KEY = "ComfyUI.AgentWorkbench.chat.v1";
const DEFAULT_MAX_MESSAGES = 80;
const DEFAULT_HISTORY_LIMIT = 12;
const MAX_HISTORY_TEXT = 1800;

function defaultStorage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

function defaultId() {
  const random = Math.random().toString(36).slice(2, 10);
  return `msg-${Date.now().toString(36)}-${random}`;
}

function boundedText(value, maxLength = MAX_HISTORY_TEXT) {
  const text = typeof value === "string" ? value : "";
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
}

function safeAttachments(value) {
  return Array.isArray(value)
    ? value.filter((row) => row && typeof row === "object")
    : [];
}

export function normalizeMessage(message, options = {}) {
  const now = options.now || Date.now;
  const makeId = options.makeId || defaultId;
  return {
    id: typeof message.id === "string" && message.id ? message.id : makeId(),
    role: ["user", "assistant", "tool", "system"].includes(message.role) ? message.role : "assistant",
    text: boundedText(message.text, options.maxTextLength || 12000),
    created_at: typeof message.created_at === "string" && message.created_at
      ? message.created_at
      : new Date(now()).toISOString(),
    attachments: safeAttachments(message.attachments),
    response: message.response && typeof message.response === "object" ? message.response : undefined,
    plan: message.plan && typeof message.plan === "object" ? message.plan : undefined,
    tool_state: message.tool_state && typeof message.tool_state === "object" ? message.tool_state : undefined,
  };
}

export function boundedMessages(messages, maxMessages = DEFAULT_MAX_MESSAGES, options = {}) {
  const rows = Array.isArray(messages) ? messages : [];
  return rows
    .map((message) => normalizeMessage(message, options))
    .slice(-maxMessages);
}

function attachmentHistorySummary(attachment) {
  const row = {
    kind: attachment.kind,
    name: attachment.name,
    mime: attachment.mime,
    size: attachment.size,
  };
  if (attachment.kind === "text" && typeof attachment.text === "string") {
    row.text = boundedText(attachment.text, 1200);
    row.truncated = Boolean(attachment.truncated);
  }
  return Object.fromEntries(Object.entries(row).filter(([, value]) => value !== undefined));
}

export function historyForRequest(messages, limit = DEFAULT_HISTORY_LIMIT) {
  return boundedMessages(messages, limit)
    .filter((message) => ["user", "assistant", "tool"].includes(message.role))
    .map((message) => {
      const row = {
        role: message.role,
        text: boundedText(message.text),
      };
      const attachments = safeAttachments(message.attachments).map(attachmentHistorySummary);
      if (attachments.length) {
        row.attachments = attachments;
      }
      return row;
    });
}

export function createChatStore(options = {}) {
  const storage = options.storage || defaultStorage();
  const key = options.key || DEFAULT_KEY;
  const maxMessages = options.maxMessages || DEFAULT_MAX_MESSAGES;
  const normalizeOptions = {
    now: options.now,
    makeId: options.makeId,
    maxTextLength: options.maxTextLength,
  };

  function load() {
    if (!storage) {
      return [];
    }
    try {
      return boundedMessages(JSON.parse(storage.getItem(key) || "[]"), maxMessages, normalizeOptions);
    } catch {
      return [];
    }
  }

  function save(messages) {
    const rows = boundedMessages(messages, maxMessages, normalizeOptions);
    if (storage) {
      storage.setItem(key, JSON.stringify(rows));
    }
    return rows;
  }

  function append(message) {
    const rows = save([...load(), message]);
    return rows[rows.length - 1];
  }

  function update(id, updater) {
    const rows = load().map((message) => {
      if (message.id !== id) {
        return message;
      }
      const next = typeof updater === "function" ? updater(message) : updater;
      return normalizeMessage({ ...message, ...next }, normalizeOptions);
    });
    save(rows);
    return rows.find((message) => message.id === id) || null;
  }

  function clear() {
    if (storage) {
      storage.removeItem(key);
    }
    return [];
  }

  return { append, clear, load, save, update };
}

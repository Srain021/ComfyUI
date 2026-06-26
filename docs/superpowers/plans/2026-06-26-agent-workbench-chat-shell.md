# Agent Workbench Chat Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing ComfyUI Agent Workbench sidebar into a local-first Codex/Claude-style chat workspace with persistent message history, text/image attachments, and approval-based tool-call cards.

**Architecture:** Keep the existing `/agent/message`, deterministic planner, apply route, and Codex OAuth bridge. Add small frontend modules for chat storage, attachments, and timeline rendering; extend backend payload assembly to include history and attachment summaries; extend the bridge to pass uploaded images to `codex exec --image`. The first version stores history in `localStorage`; server-side history remains Phase 4.

**Tech Stack:** ComfyUI custom-node frontend extension, browser `localStorage`, browser FileReader/Clipboard/Drag APIs, vanilla ES modules, Python stdlib `json/base64/tempfile/subprocess`, aiohttp route tests, Node `node:test`, existing browser smoke CDP harness.

---

## Scope Check

This plan implements Phase 1, Phase 2, and the minimum Phase 3 tool-card flow from the approved spec:

- Phase 1: local chat shell and browser history.
- Phase 2: text/image attachments and Codex bridge image forwarding.
- Phase 3: replace single output replacement with timeline tool-call cards while preserving the existing apply path.

It does not implement Phase 4 server-side cross-device history.

## File Structure

- Create `custom_nodes/ComfyUI-AgentWorkbench/js/chat-store.mjs`
  - Owns message creation, localStorage persistence, history bounds, and backend history serialization.
- Create `tests-unit/agent_workbench/frontend/chat-store.test.mjs`
  - Tests local chat store behavior without ComfyUI.
- Create `custom_nodes/ComfyUI-AgentWorkbench/js/attachments.mjs`
  - Owns file validation, text truncation, data URL conversion, and pending attachment state helpers.
- Create `tests-unit/agent_workbench/frontend/attachments.test.mjs`
  - Tests attachment validation and payload shaping.
- Create `custom_nodes/ComfyUI-AgentWorkbench/js/chat-render.mjs`
  - Owns timeline rendering, user/assistant/tool/status rows, and tool-card button wiring.
- Create `tests-unit/agent_workbench/frontend/chat-render.test.mjs`
  - Tests DOM rendering using lightweight fake DOM objects.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`
  - Integrates store, attachments, renderer, backend requests, and apply handling.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`
  - Replaces single-output layout with timeline/composer/tool-card styles.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/js/workbench-response.mjs`
  - Keeps formatting helpers but allows assistant/tool summaries to feed timeline rows.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py`
  - Adds bounded `history` and `attachments` to OpenAI-compatible payloads.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`
  - Parses and forwards `history` and `attachments` to `build_assistant_reply()`.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py`
  - Extracts image attachments, writes safe temporary files, and appends `--image` args to `codex exec`.
- Modify `tests-unit/agent_workbench/test_llm.py`
  - Adds payload tests for history and attachments.
- Modify `tests-unit/agent_workbench/test_context.py`
  - Adds route tests for `/agent/message` rich chat payload.
- Modify `tests-unit/agent_workbench/test_codex_bridge.py`
  - Adds tests for data URL image decoding and `--image` command assembly.
- Modify `custom_nodes/ComfyUI-AgentWorkbench/tools/browser-smoke.mjs`
  - Adds smoke coverage for two-message history, refresh restore, and tool card apply.

## Commands

Focused frontend tests:

```bash
node --test tests-unit/agent_workbench/frontend/chat-store.test.mjs
node --test tests-unit/agent_workbench/frontend/attachments.test.mjs
node --test tests-unit/agent_workbench/frontend/chat-render.test.mjs
```

Focused Python tests:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_llm.py tests-unit/agent_workbench/test_context.py tests-unit/agent_workbench/test_codex_bridge.py
```

Full regression:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench
node --test tests-unit/agent_workbench/frontend/*.test.mjs
PYTHONPYCACHEPREFIX=/tmp/comfyui-agent-pycache python3 -m py_compile custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py
node --check custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js
git diff --check
node custom_nodes/ComfyUI-AgentWorkbench/tools/browser-smoke.mjs
```

Live reload after backend changes:

```bash
docker compose -f dgx_spark_ltx_setup/docker-compose.yml up -d
```

---

### Task 1: Local Chat Store

**Files:**
- Create: `custom_nodes/ComfyUI-AgentWorkbench/js/chat-store.mjs`
- Create: `tests-unit/agent_workbench/frontend/chat-store.test.mjs`

- [ ] **Step 1: Write the failing chat store test**

Create `tests-unit/agent_workbench/frontend/chat-store.test.mjs`:

```javascript
import assert from "node:assert/strict";
import test from "node:test";

import {
  CHAT_STORAGE_KEY,
  appendMessage,
  createChatStore,
  createMessage,
  historyForRequest,
  loadChatState,
  saveChatState,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/chat-store.mjs";

function memoryStorage(seed = {}) {
  const rows = new Map(Object.entries(seed));
  return {
    getItem: (key) => rows.has(key) ? rows.get(key) : null,
    setItem: (key, value) => rows.set(key, String(value)),
    removeItem: (key) => rows.delete(key),
  };
}

test("createMessage creates stable chat records with attachments", () => {
  const message = createMessage({
    id: "msg_1",
    role: "user",
    text: "看这张图",
    attachments: [{ id: "att_1", kind: "image", name: "shot.png" }],
    now: () => "2026-06-26T00:00:00.000Z",
  });

  assert.deepEqual(message, {
    id: "msg_1",
    role: "user",
    created_at: "2026-06-26T00:00:00.000Z",
    text: "看这张图",
    attachments: [{ id: "att_1", kind: "image", name: "shot.png" }],
    response: null,
    plan: null,
    tool_state: null,
  });
});

test("appendMessage keeps the newest 100 messages", () => {
  let state = createChatStore({ session_id: "local_test" });
  for (let index = 0; index < 105; index += 1) {
    state = appendMessage(state, createMessage({
      id: `msg_${index}`,
      role: "user",
      text: `message ${index}`,
      now: () => "2026-06-26T00:00:00.000Z",
    }));
  }

  assert.equal(state.messages.length, 100);
  assert.equal(state.messages[0].id, "msg_5");
  assert.equal(state.messages.at(-1).id, "msg_104");
});

test("saveChatState and loadChatState round trip through localStorage", () => {
  const storage = memoryStorage();
  const state = appendMessage(
    createChatStore({ session_id: "local_test" }),
    createMessage({
      id: "msg_1",
      role: "assistant",
      text: "你好",
      now: () => "2026-06-26T00:00:00.000Z",
    }),
  );

  saveChatState(storage, state);
  assert.match(storage.getItem(CHAT_STORAGE_KEY), /"session_id":"local_test"/);
  assert.deepEqual(loadChatState(storage), state);
});

test("loadChatState recovers from invalid saved data", () => {
  const storage = memoryStorage({ [CHAT_STORAGE_KEY]: "{bad json" });
  const state = loadChatState(storage, { idFactory: () => "local_recovered" });

  assert.equal(state.version, 1);
  assert.equal(state.session_id, "local_recovered");
  assert.deepEqual(state.messages, []);
});

test("historyForRequest sends only recent text summaries", () => {
  let state = createChatStore({ session_id: "local_test" });
  for (let index = 0; index < 25; index += 1) {
    state = appendMessage(state, createMessage({
      id: `msg_${index}`,
      role: index % 2 === 0 ? "user" : "assistant",
      text: `message ${index}`,
      attachments: [{ id: `att_${index}`, name: "large.png", kind: "image", data_url: "data:image/png;base64,AAAA" }],
      now: () => "2026-06-26T00:00:00.000Z",
    }));
  }

  const history = historyForRequest(state, 20);
  assert.equal(history.length, 20);
  assert.equal(history[0].text, "message 5");
  assert.equal(history.at(-1).text, "message 24");
  assert.equal(history[0].attachments[0].name, "large.png");
  assert.equal(history[0].attachments[0].data_url, undefined);
});
```

- [ ] **Step 2: Run the failing chat store test**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/chat-store.test.mjs
```

Expected: FAIL with `Cannot find module .../chat-store.mjs`.

- [ ] **Step 3: Implement `chat-store.mjs`**

Create `custom_nodes/ComfyUI-AgentWorkbench/js/chat-store.mjs`:

```javascript
export const CHAT_STORAGE_KEY = "comfyui.agentWorkbench.chat.v1";
export const CHAT_STATE_VERSION = 1;
export const MAX_STORED_MESSAGES = 100;
export const DEFAULT_HISTORY_LIMIT = 20;

function defaultId(prefix) {
  if (globalThis.crypto?.randomUUID) {
    return `${prefix}_${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function nowIso() {
  return new Date().toISOString();
}

export function createChatStore({ session_id = defaultId("local") } = {}) {
  return {
    version: CHAT_STATE_VERSION,
    session_id,
    messages: [],
  };
}

export function createMessage({
  id = defaultId("msg"),
  role,
  text = "",
  attachments = [],
  response = null,
  plan = null,
  tool_state = null,
  now = nowIso,
}) {
  return {
    id,
    role,
    created_at: now(),
    text,
    attachments: Array.isArray(attachments) ? attachments : [],
    response,
    plan,
    tool_state,
  };
}

export function appendMessage(state, message, maxMessages = MAX_STORED_MESSAGES) {
  const messages = [...(state?.messages || []), message].slice(-maxMessages);
  return {
    version: CHAT_STATE_VERSION,
    session_id: state?.session_id || defaultId("local"),
    messages,
  };
}

export function replaceMessage(state, messageId, updater) {
  return {
    ...state,
    messages: (state?.messages || []).map((message) => (
      message.id === messageId ? updater(message) : message
    )),
  };
}

export function saveChatState(storage, state) {
  storage.setItem(CHAT_STORAGE_KEY, JSON.stringify({
    version: CHAT_STATE_VERSION,
    session_id: state.session_id,
    messages: (state.messages || []).slice(-MAX_STORED_MESSAGES),
  }));
}

export function loadChatState(storage, { idFactory = () => defaultId("local") } = {}) {
  try {
    const raw = storage.getItem(CHAT_STORAGE_KEY);
    if (!raw) {
      return createChatStore({ session_id: idFactory() });
    }
    const parsed = JSON.parse(raw);
    if (parsed?.version !== CHAT_STATE_VERSION || !Array.isArray(parsed?.messages)) {
      return createChatStore({ session_id: idFactory() });
    }
    return {
      version: CHAT_STATE_VERSION,
      session_id: typeof parsed.session_id === "string" && parsed.session_id ? parsed.session_id : idFactory(),
      messages: parsed.messages.slice(-MAX_STORED_MESSAGES),
    };
  } catch {
    return createChatStore({ session_id: idFactory() });
  }
}

function attachmentSummary(attachment) {
  const summary = {
    id: attachment.id,
    kind: attachment.kind,
    name: attachment.name,
    mime: attachment.mime,
    size: attachment.size,
    truncated: Boolean(attachment.truncated),
  };
  if (attachment.kind === "text") {
    summary.text = attachment.text;
  }
  return summary;
}

export function historyForRequest(state, limit = DEFAULT_HISTORY_LIMIT) {
  return (state?.messages || [])
    .slice(-limit)
    .filter((message) => ["user", "assistant", "tool", "status"].includes(message.role))
    .map((message) => ({
      role: message.role,
      text: message.text || "",
      tool_state: message.tool_state || undefined,
      attachments: (message.attachments || []).map(attachmentSummary),
    }));
}

export function newChatState() {
  return createChatStore();
}
```

- [ ] **Step 4: Run the chat store test to verify it passes**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/chat-store.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add -f custom_nodes/ComfyUI-AgentWorkbench/js/chat-store.mjs tests-unit/agent_workbench/frontend/chat-store.test.mjs
git commit -m "feat: add agent workbench chat store"
```

### Task 2: Attachment Parsing and Validation

**Files:**
- Create: `custom_nodes/ComfyUI-AgentWorkbench/js/attachments.mjs`
- Create: `tests-unit/agent_workbench/frontend/attachments.test.mjs`

- [ ] **Step 1: Write the failing attachment tests**

Create `tests-unit/agent_workbench/frontend/attachments.test.mjs`:

```javascript
import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_ATTACHMENTS,
  MAX_TEXT_CHARS,
  attachmentFromText,
  dataUrlAttachment,
  validateAttachmentFile,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/attachments.mjs";

test("validateAttachmentFile accepts supported image and text files", () => {
  assert.equal(validateAttachmentFile({ name: "shot.png", type: "image/png", size: 12 }).ok, true);
  assert.equal(validateAttachmentFile({ name: "notes.md", type: "text/markdown", size: 12 }).ok, true);
  assert.equal(validateAttachmentFile({ name: "workflow.json", type: "application/json", size: 12 }).ok, true);
});

test("validateAttachmentFile rejects unsupported files and too many attachments", () => {
  assert.deepEqual(validateAttachmentFile({ name: "movie.mp4", type: "video/mp4", size: 12 }), {
    ok: false,
    error: "unsupported_file_type",
  });
  assert.deepEqual(
    validateAttachmentFile({ name: "extra.txt", type: "text/plain", size: 12 }, { currentCount: MAX_ATTACHMENTS }),
    { ok: false, error: "too_many_attachments" },
  );
});

test("attachmentFromText truncates long text deterministically", () => {
  const attachment = attachmentFromText({
    id: "att_1",
    name: "long.txt",
    mime: "text/plain",
    text: "x".repeat(MAX_TEXT_CHARS + 10),
  });

  assert.equal(attachment.kind, "text");
  assert.equal(attachment.text.length, MAX_TEXT_CHARS);
  assert.equal(attachment.truncated, true);
});

test("dataUrlAttachment stores image payload and metadata", () => {
  const attachment = dataUrlAttachment({
    id: "att_2",
    name: "shot.png",
    mime: "image/png",
    size: 22,
    dataUrl: "data:image/png;base64,AAAA",
  });

  assert.deepEqual(attachment, {
    id: "att_2",
    kind: "image",
    name: "shot.png",
    mime: "image/png",
    size: 22,
    data_url: "data:image/png;base64,AAAA",
  });
});
```

- [ ] **Step 2: Run the failing attachment tests**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/attachments.test.mjs
```

Expected: FAIL with `Cannot find module .../attachments.mjs`.

- [ ] **Step 3: Implement `attachments.mjs`**

Create `custom_nodes/ComfyUI-AgentWorkbench/js/attachments.mjs`:

```javascript
export const MAX_ATTACHMENTS = 4;
export const MAX_IMAGES = 4;
export const MAX_TEXT_CHARS = 40000;

const SUPPORTED_IMAGE_MIME = new Set(["image/png", "image/jpeg", "image/webp"]);
const SUPPORTED_TEXT_MIME = new Set([
  "text/plain",
  "text/markdown",
  "application/json",
]);
const SUPPORTED_TEXT_EXTENSIONS = new Set([".txt", ".md", ".json"]);

function extensionOf(name = "") {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function defaultAttachmentId() {
  if (globalThis.crypto?.randomUUID) {
    return `att_${globalThis.crypto.randomUUID()}`;
  }
  return `att_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function validateAttachmentFile(file, { currentCount = 0, currentImageCount = 0 } = {}) {
  if (currentCount >= MAX_ATTACHMENTS) {
    return { ok: false, error: "too_many_attachments" };
  }
  const type = file?.type || "";
  const name = file?.name || "";
  const isImage = SUPPORTED_IMAGE_MIME.has(type);
  const isText = SUPPORTED_TEXT_MIME.has(type) || SUPPORTED_TEXT_EXTENSIONS.has(extensionOf(name));
  if (isImage && currentImageCount >= MAX_IMAGES) {
    return { ok: false, error: "too_many_images" };
  }
  if (!isImage && !isText) {
    return { ok: false, error: "unsupported_file_type" };
  }
  return { ok: true, kind: isImage ? "image" : "text" };
}

export function attachmentFromText({ id = defaultAttachmentId(), name, mime, size = 0, text }) {
  const raw = String(text || "");
  const truncated = raw.length > MAX_TEXT_CHARS;
  return {
    id,
    kind: "text",
    name,
    mime,
    size,
    text: truncated ? raw.slice(0, MAX_TEXT_CHARS) : raw,
    truncated,
  };
}

export function dataUrlAttachment({ id = defaultAttachmentId(), name, mime, size = 0, dataUrl }) {
  return {
    id,
    kind: "image",
    name,
    mime,
    size,
    data_url: dataUrl,
  };
}

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")));
    reader.addEventListener("error", () => reject(reader.error || new Error("file_read_failed")));
    reader.readAsDataURL(file);
  });
}

export function fileToText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")));
    reader.addEventListener("error", () => reject(reader.error || new Error("file_read_failed")));
    reader.readAsText(file);
  });
}

export async function attachmentFromFile(file, existing = []) {
  const currentImageCount = existing.filter((row) => row.kind === "image").length;
  const validation = validateAttachmentFile(file, {
    currentCount: existing.length,
    currentImageCount,
  });
  if (!validation.ok) {
    return validation;
  }
  if (validation.kind === "image") {
    return {
      ok: true,
      attachment: dataUrlAttachment({
        name: file.name,
        mime: file.type,
        size: file.size,
        dataUrl: await fileToDataUrl(file),
      }),
    };
  }
  return {
    ok: true,
    attachment: attachmentFromText({
      name: file.name,
      mime: file.type || "text/plain",
      size: file.size,
      text: await fileToText(file),
    }),
  };
}
```

- [ ] **Step 4: Run the attachment tests**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/attachments.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add -f custom_nodes/ComfyUI-AgentWorkbench/js/attachments.mjs tests-unit/agent_workbench/frontend/attachments.test.mjs
git commit -m "feat: add agent workbench attachments"
```

### Task 3: Backend History and Attachment Payloads

**Files:**
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`
- Modify: `tests-unit/agent_workbench/test_llm.py`
- Modify: `tests-unit/agent_workbench/test_context.py`

- [ ] **Step 1: Write failing LLM payload tests**

Append to `tests-unit/agent_workbench/test_llm.py`:

```python
def test_openai_payload_includes_recent_history_and_text_attachments():
    payload = build_openai_responses_payload(
        "继续优化",
        history=[
            {"role": "user", "text": "第一轮"},
            {"role": "assistant", "text": "已分析"},
        ],
        attachments=[
            {
                "id": "att_1",
                "kind": "text",
                "name": "notes.md",
                "mime": "text/markdown",
                "size": 20,
                "text": "需要更电影感",
                "truncated": False,
            }
        ],
        context={"graph": {"node_count": 2}},
        dry_run=_context_only_dry_run(),
        model="gpt-test",
    )

    assert "recent_history" in payload["input"]
    assert "第一轮" in payload["input"]
    assert "已分析" in payload["input"]
    assert "notes.md" in payload["input"]
    assert "需要更电影感" in payload["input"]


def test_openai_payload_summarizes_images_without_inline_bytes():
    payload = build_openai_responses_payload(
        "看图",
        history=[],
        attachments=[
            {
                "id": "att_img",
                "kind": "image",
                "name": "shot.png",
                "mime": "image/png",
                "size": 30,
                "data_url": "data:image/png;base64,AAAA",
            }
        ],
        context={"graph": {"node_count": 1}},
        dry_run=_context_only_dry_run(),
        model="gpt-test",
    )

    assert "shot.png" in payload["input"]
    assert "image_attached" in payload["input"]
    assert "AAAA" not in payload["input"]
```

- [ ] **Step 2: Write failing route test for rich chat fields**

Append to `tests-unit/agent_workbench/test_context.py`:

```python
def test_agent_message_route_forwards_history_and_attachments_to_assistant(monkeypatch):
    calls = []

    def fake_reply(message, *, context, dry_run, history=None, attachments=None):
        calls.append(
            {
                "message": message,
                "history": history,
                "attachments": attachments,
                "dry_run": dry_run,
            }
        )
        return {
            "ok": True,
            "status": "assistant_reply",
            "assistant": {"title": "Agent", "message": "saw history and attachments"},
        }

    monkeypatch.setattr(agent_routes, "build_assistant_reply", fake_reply)
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())

    try:
        agent_routes.register_routes(fake_prompt_server)
        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        response = asyncio.run(
            routes_by_key[("POST", "/agent/message")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "看附件",
                        "history": [{"role": "user", "text": "上一轮"}],
                        "attachments": [{"kind": "text", "name": "notes.txt", "text": "hello"}],
                        "graph": {"nodes": [], "links": []},
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "assistant_reply"
        assert calls[0]["history"] == [{"role": "user", "text": "上一轮"}]
        assert calls[0]["attachments"] == [{"kind": "text", "name": "notes.txt", "text": "hello"}]
    finally:
        agent_routes._REGISTERED = False
```

- [ ] **Step 3: Run focused Python tests to verify failure**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_llm.py tests-unit/agent_workbench/test_context.py::test_agent_message_route_forwards_history_and_attachments_to_assistant
```

Expected: FAIL because `build_openai_responses_payload()` and `build_assistant_reply()` do not accept `history` or `attachments`.

- [ ] **Step 4: Extend `llm.py` with bounded history and attachment summaries**

Modify function signatures in `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py`:

```python
def _compact_history(history: object, *, limit: int = 20) -> list[dict]:
    if not isinstance(history, list):
        return []
    rows = []
    for item in history[-limit:]:
        if not isinstance(item, Mapping):
            continue
        role = item.get("role")
        text = item.get("text")
        if role not in {"user", "assistant", "tool", "status"}:
            continue
        if not isinstance(text, str):
            text = ""
        rows.append(
            {
                "role": role,
                "text": text[:2000],
                "tool_state": item.get("tool_state") if isinstance(item.get("tool_state"), str) else None,
            }
        )
    return rows


def _compact_attachments(attachments: object) -> list[dict]:
    if not isinstance(attachments, list):
        return []
    rows = []
    for item in attachments[:4]:
        if not isinstance(item, Mapping):
            continue
        kind = item.get("kind")
        name = item.get("name")
        if kind not in {"text", "image"} or not isinstance(name, str):
            continue
        row = {
            "kind": kind,
            "name": name[:200],
            "mime": item.get("mime") if isinstance(item.get("mime"), str) else None,
            "size": item.get("size") if isinstance(item.get("size"), int) else None,
        }
        if kind == "text":
            text = item.get("text")
            row["text"] = text[:40000] if isinstance(text, str) else ""
            row["truncated"] = bool(item.get("truncated"))
        if kind == "image":
            row["image_attached"] = True
        rows.append(row)
    return rows
```

Modify `build_openai_responses_payload()` signature and payload:

```python
def build_openai_responses_payload(
    message: str,
    *,
    history: object | None = None,
    attachments: object | None = None,
    context: Mapping[str, Any] | None,
    dry_run: Mapping[str, Any] | None,
    model: str,
) -> dict:
    input_payload = {
        "user_message": message,
        "recent_history": _compact_history(history),
        "attachments": _compact_attachments(attachments),
        "current_comfyui_context": _compact_context(context),
        "deterministic_planner_result": dry_run or {},
    }
    return {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": _bounded_json(input_payload),
    }
```

Modify `build_assistant_reply()` signature and call:

```python
def build_assistant_reply(
    message: str,
    *,
    context: Mapping[str, Any] | None,
    dry_run: Mapping[str, Any] | None,
    history: object | None = None,
    attachments: object | None = None,
    config: LLMConfig | None = None,
    transport: Transport = openai_responses_transport,
) -> dict:
    ...
    payload = build_openai_responses_payload(
        message,
        history=history,
        attachments=attachments,
        context=context,
        dry_run=dry_run,
        model=config.model,
    )
```

- [ ] **Step 5: Extend `routes.py` to pass through rich fields**

Add helper functions:

```python
def _history_from_body(body: dict) -> list:
    history = body.get("history")
    return history if isinstance(history, list) else []


def _attachments_from_body(body: dict) -> list:
    attachments = body.get("attachments")
    return attachments if isinstance(attachments, list) else []
```

In `agent_message`, read and forward them:

```python
history = _history_from_body(body)
attachments = _attachments_from_body(body)
...
reply = await asyncio.to_thread(
    build_assistant_reply,
    message,
    context=context,
    dry_run=dry_run,
    history=history,
    attachments=attachments,
)
```

- [ ] **Step 6: Run the focused Python tests to verify pass**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_llm.py tests-unit/agent_workbench/test_context.py::test_agent_message_route_forwards_history_and_attachments_to_assistant
```

Expected: PASS.

- [ ] **Step 7: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py tests-unit/agent_workbench/test_llm.py tests-unit/agent_workbench/test_context.py
git commit -m "feat: pass chat history and attachments to agent"
```

### Task 4: Codex Bridge Image Forwarding

**Files:**
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py`
- Modify: `tests-unit/agent_workbench/test_codex_bridge.py`

- [ ] **Step 1: Write failing bridge image tests**

Append to `tests-unit/agent_workbench/test_codex_bridge.py`:

```python
def test_extract_image_attachments_decodes_data_urls(tmp_path):
    from agent_workbench.codex_bridge import extract_image_attachments

    images = extract_image_attachments(
        {
            "input": json.dumps(
                {
                    "attachments": [
                        {
                            "kind": "image",
                            "name": "shot.png",
                            "mime": "image/png",
                            "data_url": "data:image/png;base64,iVBORw0KGgo=",
                        }
                    ]
                }
            )
        },
        tmp_path,
    )

    assert len(images) == 1
    assert images[0].name.endswith(".png")
    assert images[0].read_bytes() == b"\x89PNG\r\n\x1a\n"


def test_codex_exec_command_includes_image_arguments(tmp_path):
    output_file = tmp_path / "last.txt"
    image_file = tmp_path / "shot.png"
    image_file.write_bytes(b"image")

    command = codex_exec_command("gpt-5.5", output_file, image_files=[image_file])

    image_index = command.index("--image")
    assert command[image_index + 1] == str(image_file)
    assert command[-1] == "-"
```

- [ ] **Step 2: Run failing bridge image tests**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_codex_bridge.py
```

Expected: FAIL because `extract_image_attachments()` is missing and `codex_exec_command()` does not accept `image_files`.

- [ ] **Step 3: Implement image extraction and command assembly**

Modify `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py`.

Add imports:

```python
import base64
import binascii
import re
```

Add constants and helpers:

```python
IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

DATA_URL_RE = re.compile(r"^data:(?P<mime>[-\w.]+/[-\w.+]+);base64,(?P<data>.+)$", re.DOTALL)


def _input_json(request_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = request_payload.get("input")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, Mapping) else {}
    return raw if isinstance(raw, Mapping) else {}


def extract_image_attachments(request_payload: Mapping[str, Any], tmpdir: Path) -> list[Path]:
    input_payload = _input_json(request_payload)
    attachments = input_payload.get("attachments")
    if not isinstance(attachments, list):
        return []
    image_files = []
    for index, attachment in enumerate(attachments[:4]):
        if not isinstance(attachment, Mapping) or attachment.get("kind") != "image":
            continue
        data_url = attachment.get("data_url")
        if not isinstance(data_url, str):
            continue
        match = DATA_URL_RE.match(data_url)
        if not match:
            continue
        mime = match.group("mime")
        extension = IMAGE_MIME_EXTENSIONS.get(mime)
        if extension is None:
            continue
        try:
            image_bytes = base64.b64decode(match.group("data"), validate=True)
        except (binascii.Error, ValueError):
            continue
        path = tmpdir / f"attachment-{index}{extension}"
        path.write_bytes(image_bytes)
        image_files.append(path)
    return image_files
```

Modify `codex_exec_command()`:

```python
def codex_exec_command(model: str, output_file: Path, *, image_files: list[Path] | None = None) -> list[str]:
    command = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "-C",
        "/tmp",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "--output-last-message",
        str(output_file),
    ]
    for image_file in image_files or []:
        command.extend(["--image", str(image_file)])
    command.append("-")
    return command
```

Modify `run_codex_bridge_request()` inside the temporary directory block:

```python
tmp_path = Path(tmpdir)
output_file = tmp_path / "last-message.txt"
image_files = extract_image_attachments(request_payload, tmp_path)
completed = subprocess.run(
    codex_exec_command(model, output_file, image_files=image_files),
    input=prompt,
    text=True,
    capture_output=True,
    timeout=timeout,
    check=False,
)
```

- [ ] **Step 4: Run bridge image tests to verify pass**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_codex_bridge.py
```

Expected: PASS.

- [ ] **Step 5: Restart the Codex bridge service after implementation**

Run:

```bash
systemctl --user restart comfyui-codex-bridge.service
systemctl --user is-active comfyui-codex-bridge.service
curl -sf http://172.17.0.1:8797/health
```

Expected: `active` and `{"ok": true, "service": "comfyui-codex-bridge"}`.

- [ ] **Step 6: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add -f custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py tests-unit/agent_workbench/test_codex_bridge.py
git commit -m "feat: forward image attachments to codex"
```

### Task 5: Chat Timeline Renderer and Tool Cards

**Files:**
- Create: `custom_nodes/ComfyUI-AgentWorkbench/js/chat-render.mjs`
- Create: `tests-unit/agent_workbench/frontend/chat-render.test.mjs`

- [ ] **Step 1: Write failing renderer tests**

Create `tests-unit/agent_workbench/frontend/chat-render.test.mjs`:

```javascript
import assert from "node:assert/strict";
import test from "node:test";

import {
  renderMessage,
  renderTimeline,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/chat-render.mjs";

test("renderMessage renders user messages with attachment names", () => {
  const document = globalThis.document;
  const node = renderMessage(document, {
    role: "user",
    text: "看这个",
    attachments: [{ kind: "image", name: "shot.png" }],
  });

  assert.equal(node.classList.contains("agent-workbench-message-user"), true);
  assert.match(node.textContent, /看这个/);
  assert.match(node.textContent, /shot.png/);
});

test("renderMessage renders assistant messages with details", () => {
  const document = globalThis.document;
  const node = renderMessage(document, {
    role: "assistant",
    text: "我看到了",
    response: { provider: "openai", model: "gpt-test" },
  });

  assert.equal(node.classList.contains("agent-workbench-message-assistant"), true);
  assert.match(node.textContent, /我看到了/);
  assert.match(node.textContent, /AI 详情/);
});

test("renderMessage renders tool cards with allow and cancel buttons", () => {
  const document = globalThis.document;
  const events = [];
  const node = renderMessage(document, {
    id: "tool_1",
    role: "tool",
    text: "Set widget",
    plan: {
      risk_level: "canvas",
      actions: [{ type: "graph.set_widget", payload: { node_id: 9, widget: "steps", value: 30 } }],
    },
    tool_state: "pending",
  }, {
    onApprove: (message) => events.push(["approve", message.id]),
    onCancel: (message) => events.push(["cancel", message.id]),
  });

  assert.match(node.textContent, /canvas/);
  node.querySelector("[data-agent-workbench-action='approve']").click();
  node.querySelector("[data-agent-workbench-action='cancel']").click();
  assert.deepEqual(events, [["approve", "tool_1"], ["cancel", "tool_1"]]);
});

test("renderTimeline replaces children with all message rows", () => {
  const container = globalThis.document.createElement("section");
  renderTimeline(globalThis.document, container, [
    { role: "user", text: "one", attachments: [] },
    { role: "assistant", text: "two", response: {} },
  ]);

  assert.equal(container.children.length, 2);
  assert.match(container.textContent, /one/);
  assert.match(container.textContent, /two/);
});
```

If the current Node environment lacks a DOM, create a minimal DOM test helper in this test file before the tests:

```javascript
import { JSDOM } from "jsdom";
globalThis.document = new JSDOM("<!doctype html><body></body>").window.document;
```

Do not add `jsdom` if it is unavailable in the repo. If `jsdom` is unavailable, replace this task with a structural static test in `tests-unit/agent_workbench/test_health.py` that asserts `chat-render.mjs` exports `renderMessage` and contains the required class names. Keep the test failing before implementation.

- [ ] **Step 2: Run the failing renderer test**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/chat-render.test.mjs
```

Expected: FAIL because `chat-render.mjs` does not exist.

- [ ] **Step 3: Implement `chat-render.mjs`**

Create `custom_nodes/ComfyUI-AgentWorkbench/js/chat-render.mjs`:

```javascript
function textBlock(document, className, text) {
  const block = document.createElement("div");
  block.className = className;
  block.textContent = text || "";
  return block;
}

function renderAttachment(document, attachment) {
  const chip = document.createElement("span");
  chip.className = `agent-workbench-attachment-chip agent-workbench-attachment-${attachment.kind}`;
  chip.textContent = attachment.name || attachment.kind;
  if (attachment.kind === "image" && attachment.data_url) {
    const image = document.createElement("img");
    image.alt = attachment.name || "image attachment";
    image.src = attachment.data_url;
    chip.prepend(image);
  }
  return chip;
}

function renderAttachments(document, attachments = []) {
  const row = document.createElement("div");
  row.className = "agent-workbench-message-attachments";
  for (const attachment of attachments) {
    row.append(renderAttachment(document, attachment));
  }
  return row;
}

function renderDetails(document, label, value) {
  const details = document.createElement("details");
  details.className = "agent-workbench-response-details";
  const summary = document.createElement("summary");
  summary.textContent = label;
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(value || {}, null, 2);
  details.append(summary, pre);
  return details;
}

function renderToolCard(document, message, handlers = {}) {
  const card = document.createElement("article");
  card.className = `agent-workbench-tool-card agent-workbench-tool-${message.tool_state || "pending"}`;
  card.append(textBlock(document, "agent-workbench-tool-title", message.text || "Tool call"));
  const risk = document.createElement("span");
  risk.className = "agent-workbench-risk-badge";
  risk.textContent = message.plan?.risk_level || "read";
  card.append(risk);

  const list = document.createElement("ul");
  list.className = "agent-workbench-tool-actions";
  for (const action of message.plan?.actions || []) {
    const item = document.createElement("li");
    item.textContent = action.type;
    list.append(item);
  }
  card.append(list);
  card.append(renderDetails(document, "计划详情", message.plan || {}));

  if ((message.tool_state || "pending") === "pending") {
    const actions = document.createElement("div");
    actions.className = "agent-workbench-tool-controls";
    const approve = document.createElement("button");
    approve.dataset.agentWorkbenchAction = "approve";
    approve.textContent = "允许执行";
    approve.addEventListener("click", () => handlers.onApprove?.(message));
    const cancel = document.createElement("button");
    cancel.dataset.agentWorkbenchAction = "cancel";
    cancel.textContent = "取消";
    cancel.addEventListener("click", () => handlers.onCancel?.(message));
    actions.append(approve, cancel);
    card.append(actions);
  }
  return card;
}

export function renderMessage(document, message, handlers = {}) {
  const row = document.createElement("article");
  row.className = `agent-workbench-message agent-workbench-message-${message.role}`;
  if (message.role === "tool") {
    row.append(renderToolCard(document, message, handlers));
    return row;
  }
  row.append(textBlock(document, "agent-workbench-message-body", message.text || ""));
  if (message.attachments?.length) {
    row.append(renderAttachments(document, message.attachments));
  }
  if (message.response) {
    row.append(renderDetails(document, message.role === "assistant" ? "AI 详情" : "详情", message.response));
  }
  return row;
}

export function renderTimeline(document, container, messages, handlers = {}) {
  container.replaceChildren(...messages.map((message) => renderMessage(document, message, handlers)));
  container.scrollTop = container.scrollHeight;
}
```

- [ ] **Step 4: Run renderer tests**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/chat-render.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add -f custom_nodes/ComfyUI-AgentWorkbench/js/chat-render.mjs tests-unit/agent_workbench/frontend/chat-render.test.mjs
git commit -m "feat: render agent workbench chat timeline"
```

### Task 6: Integrate Chat Shell in Sidebar

**Files:**
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`
- Modify: `tests-unit/agent_workbench/test_health.py`

- [ ] **Step 1: Add failing static frontend integration test**

Append these assertions to `test_frontend_exposes_plan_first_operator_controls()` or add a new test in `tests-unit/agent_workbench/test_health.py`:

```python
def test_frontend_uses_local_first_chat_shell_modules():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()
    stylesheet = (AGENT_ROOT / "js" / "agent-workbench.css").read_text()

    assert 'from "./chat-store.mjs"' in script
    assert 'from "./attachments.mjs"' in script
    assert 'from "./chat-render.mjs"' in script
    assert 'id="agent-workbench-timeline"' in script
    assert 'id="agent-workbench-file-input"' in script
    assert 'agent-workbench-attachment-tray' in script
    assert 'historyForRequest(chatState)' in script
    assert 'attachments: pendingAttachments' in script
    assert ".agent-workbench-message-user" in stylesheet
    assert ".agent-workbench-tool-card" in stylesheet
    assert ".agent-workbench-composer" in stylesheet
```

- [ ] **Step 2: Run failing static integration test**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_health.py::test_frontend_uses_local_first_chat_shell_modules
```

Expected: FAIL because `agent-workbench.js` has not imported the new modules and markup is still the old single-output layout.

- [ ] **Step 3: Update `agent-workbench.js` imports**

Add imports near the top:

```javascript
import { attachmentFromFile } from "./attachments.mjs";
import {
  appendMessage,
  createMessage,
  historyForRequest,
  loadChatState,
  newChatState,
  replaceMessage,
  saveChatState,
} from "./chat-store.mjs";
import { renderTimeline } from "./chat-render.mjs";
```

- [ ] **Step 4: Replace panel markup with chat shell markup**

In `createWorkbenchPanel`, replace the existing `panel.innerHTML` with:

```javascript
panel.innerHTML = `
  <header>
    <strong>Agent Workbench</strong>
    <div class="agent-workbench-header-actions">
      <button id="agent-workbench-new-chat" title="Start a new local chat">新会话</button>
      <button id="agent-workbench-clear-chat" title="Clear local chat history">清空</button>
      <button id="agent-workbench-smoke" title="Show Windows browser smoke checklist">自检</button>
      <button id="agent-workbench-context" title="Refresh context">上下文</button>
    </div>
  </header>
  <section id="agent-workbench-timeline" aria-live="polite"></section>
  <section class="agent-workbench-composer">
    <div id="agent-workbench-attachment-tray" class="agent-workbench-attachment-tray"></div>
    <textarea id="agent-workbench-input" placeholder="告诉 Agent 你要怎么改节点、插件或服务"></textarea>
    <div class="agent-workbench-actions">
      <input id="agent-workbench-file-input" type="file" multiple accept=".txt,.md,.json,image/png,image/jpeg,image/webp" hidden />
      <button id="agent-workbench-upload" aria-label="Upload attachment">上传</button>
      <button id="agent-workbench-plan" aria-label="Send message to Agent">发送</button>
    </div>
  </section>
`;
```

Remove the fixed global `执行` and `取消` buttons from the first chat-shell integration. Tool-card approval will own apply/cancel. Keep any variables used only by the old fixed buttons out of the new flow.

- [ ] **Step 5: Add local chat state and render helper**

Inside `createWorkbenchPanel` after DOM lookup:

```javascript
const timeline = panel.querySelector("#agent-workbench-timeline");
const fileInput = panel.querySelector("#agent-workbench-file-input");
const attachmentTray = panel.querySelector("#agent-workbench-attachment-tray");
let chatState = loadChatState(globalThis.localStorage);
let pendingAttachments = [];
let lastDryRun = null;
let applyInFlight = false;

function persistAndRender() {
  try {
    saveChatState(globalThis.localStorage, chatState);
  } catch {
    chatState = appendMessage(chatState, createMessage({
      role: "status",
      text: "本地历史保存失败；当前会话会继续保留在内存中。",
    }));
  }
  renderTimeline(document, timeline, chatState.messages, {
    onApprove: approveToolMessage,
    onCancel: cancelToolMessage,
  });
}

function renderAttachmentTray() {
  attachmentTray.replaceChildren(...pendingAttachments.map((attachment) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `agent-workbench-pending-attachment agent-workbench-pending-${attachment.kind}`;
    chip.textContent = attachment.name;
    chip.title = "Remove attachment";
    chip.addEventListener("click", () => {
      pendingAttachments = pendingAttachments.filter((row) => row.id !== attachment.id);
      renderAttachmentTray();
    });
    return chip;
  }));
}
```

Define `approveToolMessage` and `cancelToolMessage` below `refreshApplyState` replacement:

```javascript
async function approveToolMessage(message) {
  if (applyInFlight || !message.plan) {
    return;
  }
  applyInFlight = true;
  chatState = replaceMessage(chatState, message.id, (row) => ({ ...row, tool_state: "running" }));
  persistAndRender();
  try {
    lastDryRun = { plan: message.plan };
    const applyRequest = buildApplyRequest({ plan: message.plan }, true, currentWorkflowSnapshot());
    const result = await postJson("/agent/apply", applyRequest);
    if (result.ok) {
      try {
        result.browser_applied = applyGraphActions(message.plan.actions);
        result.browser_runtime = await executeBrowserRuntimeActions(message.plan.actions);
      } catch (error) {
        result.ok = false;
        result.browser_error = error instanceof Error ? error.message : String(error);
      }
    }
    chatState = replaceMessage(chatState, message.id, (row) => ({
      ...row,
      tool_state: result.ok ? "done" : "failed",
    }));
    chatState = appendMessage(chatState, createMessage({
      role: "tool",
      text: result.ok ? "执行完成" : "执行失败",
      response: result,
      tool_state: result.ok ? "done" : "failed",
    }));
  } catch (error) {
    chatState = appendMessage(chatState, createMessage({
      role: "status",
      text: error instanceof Error ? error.message : String(error),
    }));
  } finally {
    applyInFlight = false;
    persistAndRender();
  }
}

function cancelToolMessage(message) {
  chatState = replaceMessage(chatState, message.id, (row) => ({ ...row, tool_state: "cancelled" }));
  chatState = appendMessage(chatState, createMessage({
    role: "status",
    text: "已取消计划，未执行任何操作。",
  }));
  persistAndRender();
}
```

- [ ] **Step 6: Update send flow to append user, assistant, and tool messages**

Replace the old `agent-workbench-plan` click handler with:

```javascript
panel.querySelector("#agent-workbench-plan").addEventListener("click", async () => {
  const message = input.value.trim();
  if (!message && pendingAttachments.length === 0) {
    return;
  }
  const userMessage = createMessage({
    role: "user",
    text: message,
    attachments: pendingAttachments,
  });
  chatState = appendMessage(chatState, userMessage);
  input.value = "";
  pendingAttachments = [];
  renderAttachmentTray();
  chatState = appendMessage(chatState, createMessage({
    role: "status",
    text: "Agent 正在思考...",
  }));
  persistAndRender();

  const response = await postJson("/agent/message", {
    message: message || "Inspect current ComfyUI context",
    mode: "chat",
    history: historyForRequest(chatState),
    attachments: userMessage.attachments,
    graph: currentGraphSnapshot(),
  });

  chatState = {
    ...chatState,
    messages: chatState.messages.filter((row) => row.text !== "Agent 正在思考..."),
  };
  const formatted = formatWorkbenchResponse(response);
  if (response?.status === "dry_run" && response?.plan) {
    chatState = appendMessage(chatState, createMessage({
      role: "tool",
      text: formatted.message,
      response,
      plan: response.plan,
      tool_state: "pending",
    }));
  } else {
    chatState = appendMessage(chatState, createMessage({
      role: response?.ok === false ? "status" : "assistant",
      text: formatted.message,
      response,
    }));
  }
  persistAndRender();
});
```

This initial integration intentionally does not cover deferred server actions from the old apply flow. After the new tool-card path is green, copy the existing `frontend_requests` and `deferred_server_actions` loops into `approveToolMessage()` without changing their semantics.

- [ ] **Step 7: Add upload, paste, and drag/drop integration**

Add helper:

```javascript
async function addFiles(files) {
  for (const file of Array.from(files || [])) {
    const result = await attachmentFromFile(file, pendingAttachments);
    if (!result.ok) {
      chatState = appendMessage(chatState, createMessage({
        role: "status",
        text: `附件未添加：${result.error}`,
      }));
      continue;
    }
    pendingAttachments = [...pendingAttachments, result.attachment];
  }
  renderAttachmentTray();
  persistAndRender();
}
```

Wire controls:

```javascript
panel.querySelector("#agent-workbench-upload").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
  await addFiles(fileInput.files);
  fileInput.value = "";
});
input.addEventListener("paste", async (event) => {
  if (event.clipboardData?.files?.length) {
    event.preventDefault();
    await addFiles(event.clipboardData.files);
  }
});
panel.addEventListener("dragover", (event) => {
  event.preventDefault();
});
panel.addEventListener("drop", async (event) => {
  event.preventDefault();
  await addFiles(event.dataTransfer?.files);
});
```

- [ ] **Step 8: Update CSS for timeline, composer, attachments, and tool cards**

Modify `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css` with these concrete sections:

```css
#agent-workbench-panel {
  grid-template-rows: auto minmax(0, 1fr) auto;
}

#agent-workbench-timeline {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px;
  border-radius: 6px;
  background: #0c0f14;
}

.agent-workbench-composer {
  display: grid;
  gap: 8px;
}

.agent-workbench-message {
  max-width: 96%;
  border: 1px solid rgba(180, 190, 205, 0.16);
  border-radius: 7px;
  padding: 8px;
  background: #111721;
}

.agent-workbench-message-user {
  align-self: flex-end;
  background: #1d2a3c;
}

.agent-workbench-message-assistant,
.agent-workbench-message-tool,
.agent-workbench-message-status {
  align-self: flex-start;
}

.agent-workbench-message-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-workbench-attachment-tray,
.agent-workbench-message-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-workbench-attachment-chip,
.agent-workbench-pending-attachment {
  min-height: 26px;
  border: 1px solid rgba(180, 190, 205, 0.28);
  border-radius: 6px;
  padding: 4px 6px;
  background: #17202c;
  color: #dbe6f4;
}

.agent-workbench-attachment-chip img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  display: block;
  margin-bottom: 4px;
  border-radius: 4px;
}

.agent-workbench-tool-card {
  display: grid;
  gap: 8px;
}

.agent-workbench-tool-title {
  font-weight: 700;
}

.agent-workbench-risk-badge {
  width: fit-content;
  border: 1px solid rgba(246, 200, 95, 0.72);
  border-radius: 999px;
  padding: 2px 7px;
  color: #f6c85f;
}

.agent-workbench-tool-controls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
```

- [ ] **Step 9: Run static integration test and frontend tests**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench/test_health.py::test_frontend_uses_local_first_chat_shell_modules
node --test tests-unit/agent_workbench/frontend/*.test.mjs
```

Expected: PASS.

- [ ] **Step 10: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add -f custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css tests-unit/agent_workbench/test_health.py
git commit -m "feat: integrate agent workbench chat shell"
```

### Task 7: Browser Smoke for Chat History and Tool Cards

**Files:**
- Modify: `custom_nodes/ComfyUI-AgentWorkbench/tools/browser-smoke.mjs`

- [ ] **Step 1: Add smoke helpers for visible timeline rows**

In `browser-smoke.mjs`, add:

```javascript
async function readTimeline(client) {
  return pageCall(client, () => {
    const rows = [...document.querySelectorAll("#agent-workbench-timeline .agent-workbench-message")];
    return rows.map((row) => ({
      text: row.textContent,
      classes: [...row.classList],
    }));
  });
}

async function waitForTimelineText(client, label, pattern) {
  return waitFor(
    label,
    () => readTimeline(client),
    (rows) => rows.some((row) => new RegExp(pattern).test(row.text)),
    60000,
  );
}
```

- [ ] **Step 2: Add a two-message chat history smoke flow**

Add:

```javascript
async function runChatHistoryFlow(client, summary) {
  await setInput(client, "你好，记住第一句话");
  await clickById(client, "agent-workbench-plan");
  await waitForTimelineText(client, "first chat response", "第一句话|ComfyUI|Agent");

  await setInput(client, "上一句话是什么");
  await clickById(client, "agent-workbench-plan");
  await waitForTimelineText(client, "second chat response", "第一句话|上一句话");

  const beforeReload = await readTimeline(client);
  await client.send("Page.reload", { ignoreCache: true });
  await waitFor(
    "timeline after reload",
    () => readTimeline(client),
    (rows) => rows.length >= beforeReload.length && rows.some((row) => /上一句话是什么/.test(row.text)),
    30000,
  );
  summary.chat_history = {
    before_reload: beforeReload.length,
    after_reload: (await readTimeline(client)).length,
  };
}
```

Call `await runChatHistoryFlow(client, summary);` after `runSmokeManifestFlow`.

- [ ] **Step 3: Add a tool-card smoke flow**

Add:

```javascript
async function runToolCardFlow(client, summary) {
  await setInput(client, "把 KSampler 步数改成 30");
  await clickById(client, "agent-workbench-plan");
  await waitForTimelineText(client, "tool card", "允许执行");
  const rows = await readTimeline(client);
  summary.tool_card = {
    visible: rows.some((row) => /允许执行/.test(row.text)),
    mentions_steps: rows.some((row) => /graph.set_widget|steps|步数/.test(row.text)),
  };
}
```

Call this flow before any smoke flow that mutates the prompt. Do not click allow in this first browser smoke task; graph edit apply is already covered by existing prompt apply smoke and should be migrated to card approval after Task 6 is stable.

- [ ] **Step 4: Run browser smoke**

Run:

```bash
node custom_nodes/ComfyUI-AgentWorkbench/tools/browser-smoke.mjs
```

Expected: JSON output with `"ok": true`, plus `chat_history` and `tool_card` sections.

- [ ] **Step 5: Commit this slice if requested**

Only commit if the user asks for commits. If committing:

```bash
git add -f custom_nodes/ComfyUI-AgentWorkbench/tools/browser-smoke.mjs
git commit -m "test: smoke agent workbench chat shell"
```

### Task 8: Full Verification and Live Check

**Files:**
- No new files.

- [ ] **Step 1: Run full Python regression**

Run:

```bash
uv run --with pytest --with aiohttp --with pyyaml python -m pytest -q -p no:cacheprovider tests-unit/agent_workbench
```

Expected: all tests pass.

- [ ] **Step 2: Run full frontend regression**

Run:

```bash
node --test tests-unit/agent_workbench/frontend/*.test.mjs
```

Expected: all tests pass.

- [ ] **Step 3: Run syntax and whitespace checks**

Run:

```bash
PYTHONPYCACHEPREFIX=/tmp/comfyui-agent-pycache python3 -m py_compile custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py
node --check custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Restart live services if backend files changed**

Run:

```bash
systemctl --user restart comfyui-codex-bridge.service
docker compose -f dgx_spark_ltx_setup/docker-compose.yml up -d
docker ps -a --filter name=comfyui-gb10 --format '{{.Names}} {{.Status}}'
curl -sf http://127.0.0.1:8188/agent/health
```

Expected:

- `comfyui-codex-bridge.service` remains active.
- `comfyui-gb10` is `healthy`.
- `/agent/health` reports `"configured": true` under `llm`.

- [ ] **Step 5: Run browser smoke**

Run:

```bash
node custom_nodes/ComfyUI-AgentWorkbench/tools/browser-smoke.mjs
```

Expected: `"ok": true`.

- [ ] **Step 6: Manual Windows browser acceptance check**

In the already-open browser at `http://localhost:52031/`:

1. Refresh the page.
2. Open the Agent Workbench sidebar.
3. Send `你好，记住这句话：蓝色玻璃瓶`.
4. Send `我刚才让你记住什么？`.
5. Confirm the Agent references `蓝色玻璃瓶`.
6. Drag or paste a PNG screenshot into the composer.
7. Send `描述这张图`.
8. Confirm a user message with attachment and an assistant reply both appear in the timeline.
9. Send `把 KSampler 步数改成 30`.
10. Confirm a tool-call card appears with `允许执行` and `取消`.

- [ ] **Step 7: Record final status**

Do not claim completion until all verification commands and the manual browser acceptance check are complete. Report any failures with the exact command and observed output.

## Self-Review Notes

- Spec coverage:
  - Local history: Task 1, Task 6, Task 7.
  - Text/image attachments: Task 2, Task 3, Task 4, Task 6.
  - Tool-call cards: Task 5, Task 6, Task 7.
  - Codex bridge image path: Task 4.
  - Approval boundary: Task 6 keeps apply behind explicit card approval and existing dry-run hash.
  - Browser smoke and live verification: Task 7 and Task 8.
- Type consistency:
  - Message rows use `role`, `text`, `attachments`, `response`, `plan`, and `tool_state` consistently.
  - Attachment rows use `kind`, `name`, `mime`, `size`, `text`, `truncated`, and `data_url` consistently.
  - Backend request uses `history` and `attachments`, matching frontend `historyForRequest()` and `attachmentFromFile()`.
- Commit note:
  - Several custom-node files are currently ignored by git. Use `git add -f` only if the user asks to stage or commit.

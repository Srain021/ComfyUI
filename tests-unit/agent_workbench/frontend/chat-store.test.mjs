import assert from "node:assert/strict";
import test from "node:test";

import {
  createChatStore,
  historyForRequest,
  normalizeMessage,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/chat-store.mjs";

function memoryStorage(seed = {}) {
  const rows = new Map(Object.entries(seed));
  return {
    getItem(key) {
      return rows.has(key) ? rows.get(key) : null;
    },
    setItem(key, value) {
      rows.set(key, String(value));
    },
    removeItem(key) {
      rows.delete(key);
    },
  };
}

test("normalizeMessage creates stable sidebar chat rows", () => {
  const message = normalizeMessage(
    {
      role: "user",
      text: "描述这张图",
      attachments: [{ kind: "image", name: "graph.png", data_url: "data:image/png;base64,abc" }],
    },
    { now: () => 1782470000000, makeId: () => "msg-test" },
  );

  assert.equal(message.id, "msg-test");
  assert.equal(message.role, "user");
  assert.equal(message.created_at, "2026-06-26T10:33:20.000Z");
  assert.deepEqual(message.attachments, [
    { kind: "image", name: "graph.png", data_url: "data:image/png;base64,abc" },
  ]);
});

test("createChatStore persists bounded local-first history", () => {
  const storage = memoryStorage();
  let nextId = 0;
  const store = createChatStore({
    storage,
    key: "agent-test",
    maxMessages: 2,
    now: () => 1782470000000,
    makeId: () => `msg-${nextId++}`,
  });

  store.append({ role: "user", text: "one" });
  store.append({ role: "assistant", text: "two" });
  store.append({ role: "user", text: "three" });

  assert.deepEqual(store.load().map((row) => row.text), ["two", "three"]);
  assert.deepEqual(
    JSON.parse(storage.getItem("agent-test")).map((row) => row.id),
    ["msg-1", "msg-2"],
  );
});

test("historyForRequest strips heavy data urls but keeps useful context", () => {
  const history = historyForRequest([
    {
      role: "user",
      text: "看图",
      attachments: [
        {
          kind: "image",
          name: "workflow.png",
          mime: "image/png",
          size: 12,
          data_url: "data:image/png;base64,abc",
        },
      ],
    },
    { role: "assistant", text: "这是一张工作流截图" },
  ]);

  assert.deepEqual(history, [
    {
      role: "user",
      text: "看图",
      attachments: [
        {
          kind: "image",
          name: "workflow.png",
          mime: "image/png",
          size: 12,
        },
      ],
    },
    { role: "assistant", text: "这是一张工作流截图" },
  ]);
});

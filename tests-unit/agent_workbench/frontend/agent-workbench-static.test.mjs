import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  "custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js",
  "utf8",
);

test("agent workbench sidebar is a chat shell with upload and timeline controls", () => {
  assert.match(source, /chat-store\.mjs/);
  assert.match(source, /attachments\.mjs/);
  assert.match(source, /chat-render\.mjs/);
  assert.match(source, /agent-workbench-thread/);
  assert.match(source, /agent-workbench-file/);
  assert.match(source, /agent-workbench-send/);
  assert.doesNotMatch(source, /id="agent-workbench-output"/);
});

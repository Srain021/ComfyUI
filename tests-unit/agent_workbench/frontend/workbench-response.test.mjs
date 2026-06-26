import assert from "node:assert/strict";
import test from "node:test";

import {
  formatWorkbenchResponse,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/workbench-response.mjs";

test("formatWorkbenchResponse turns ambiguous context dry-run into a readable reply", () => {
  const response = formatWorkbenchResponse({
    status: "dry_run",
    plan: {
      summary: "Inspect context for: test",
      actions: [{ type: "context.collect", payload: { message: "test" } }],
      requires_confirmation: false,
    },
    preview: [{ type: "context.collect", payload: { message: "test" } }],
  });

  assert.equal(response.title, "我收到了");
  assert.match(response.message, /test/);
  assert.match(response.message, /明确的 ComfyUI 操作/);
  assert.equal(response.detailsLabel, "计划详情");
  assert.match(response.detailsText, /context.collect/);
});

test("formatWorkbenchResponse explains actionable dry-runs before execution", () => {
  const response = formatWorkbenchResponse({
    status: "dry_run",
    plan: {
      summary: "Set widget(s) on node 9",
      actions: [
        { type: "graph.set_widget", payload: { node_id: 9, widget: "steps", value: 30 } },
      ],
      requires_confirmation: false,
    },
  });

  assert.equal(response.title, "计划已生成");
  assert.match(response.message, /Set widget/);
  assert.match(response.message, /执行/);
});

test("formatWorkbenchResponse calls out high-risk plans", () => {
  const response = formatWorkbenchResponse({
    status: "dry_run",
    plan: {
      summary: "Disable custom node and restart ComfyUI",
      actions: [{ type: "service.restart_container", payload: { container: "comfyui-gb10" } }],
      requires_confirmation: true,
    },
  });

  assert.equal(response.title, "需要确认");
  assert.match(response.message, /高风险/);
  assert.match(response.message, /执行/);
});

test("formatWorkbenchResponse renders assistant replies as conversation", () => {
  const response = formatWorkbenchResponse({
    ok: true,
    status: "assistant_reply",
    assistant: {
      title: "ComfyUI Codex Agent",
      message: "我是嵌在 ComfyUI 里的 Agent，可以读当前工作流、生成计划，再等你确认执行。",
    },
    provider: "openai",
    model: "gpt-test",
  });

  assert.equal(response.title, "ComfyUI Codex Agent");
  assert.match(response.message, /嵌在 ComfyUI/);
  assert.equal(response.detailsLabel, "AI 详情");
  assert.match(response.detailsText, /gpt-test/);
});

test("formatWorkbenchResponse is honest when AI is not connected", () => {
  const response = formatWorkbenchResponse({
    ok: false,
    status: "ai_unavailable",
    assistant: {
      title: "Codex CLI 未连接",
      message: "还没有配置 AGENT_WORKBENCH_LLM_ENDPOINT 指向宿主 Codex bridge。",
    },
  });

  assert.equal(response.title, "Codex CLI 未连接");
  assert.match(response.message, /AGENT_WORKBENCH_LLM_ENDPOINT/);
  assert.equal(response.detailsLabel, "连接详情");
});

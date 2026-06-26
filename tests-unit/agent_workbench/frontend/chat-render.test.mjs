import assert from "node:assert/strict";
import test from "node:test";

import {
  responseImages,
  responseText,
  toolCardsFromResponse,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/chat-render.mjs";

test("responseText renders assistant replies as chat copy", () => {
  assert.equal(
    responseText({
      ok: true,
      status: "assistant_reply",
      assistant: { title: "ComfyUI Codex Agent", message: "我可以看当前工作流。" },
    }),
    "我可以看当前工作流。",
  );
});

test("responseImages reads generated image attachments from assistant replies", () => {
  assert.deepEqual(
    responseImages({
      ok: true,
      status: "assistant_reply",
      images: [
        {
          kind: "image",
          name: "husky.png",
          mime: "image/png",
          url: "/agent/generated/husky.png",
        },
      ],
    }),
    [
      {
        kind: "image",
        name: "husky.png",
        mime: "image/png",
        url: "/agent/generated/husky.png",
      },
    ],
  );
});

test("toolCardsFromResponse creates approval cards for actionable dry runs", () => {
  const cards = toolCardsFromResponse({
    status: "dry_run",
    plan: {
      summary: "Set KSampler steps to 30",
      requires_confirmation: false,
      plan_hash: "abc",
      actions: [
        {
          type: "graph.set_widget",
          capability: "graph.edit",
          risk_level: "canvas",
          payload: { node_id: 9, widget: "steps", value: 30 },
        },
      ],
    },
  });

  assert.deepEqual(cards, [
    {
      title: "可执行计划",
      summary: "Set KSampler steps to 30",
      requires_confirmation: false,
      plan_hash: "abc",
      risk_level: "canvas",
      actions: [
        {
          type: "graph.set_widget",
          capability: "graph.edit",
          risk_level: "canvas",
          payload: { node_id: 9, widget: "steps", value: 30 },
        },
      ],
    },
  ]);
});

test("toolCardsFromResponse reads planner dry-runs attached to assistant replies", () => {
  const cards = toolCardsFromResponse({
    ok: true,
    status: "assistant_reply",
    assistant: {
      title: "ComfyUI Codex Agent",
      message: "我会先说明计划，再等你允许执行。",
    },
    dry_run: {
      status: "dry_run",
      plan: {
        summary: "Set KSampler steps to 30",
        requires_confirmation: false,
        plan_hash: "abc",
        actions: [
          {
            type: "graph.set_widget",
            capability: "graph.edit",
            risk_level: "canvas",
            payload: { node_id: 9, widget: "steps", value: 30 },
          },
        ],
      },
    },
  });

  assert.equal(cards.length, 1);
  assert.equal(cards[0].summary, "Set KSampler steps to 30");
  assert.equal(cards[0].actions[0].type, "graph.set_widget");
});

test("toolCardsFromResponse labels elevated plans", () => {
  const cards = toolCardsFromResponse({
    status: "dry_run",
    plan: {
      summary: "Restart ComfyUI",
      requires_confirmation: true,
      risk_level: "elevated",
      actions: [{ type: "service.restart_container", risk_level: "elevated" }],
    },
  });

  assert.equal(cards[0].title, "需要允许");
  assert.equal(cards[0].requires_confirmation, true);
  assert.equal(cards[0].risk_level, "elevated");
});

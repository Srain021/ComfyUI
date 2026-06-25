import assert from "node:assert/strict";
import test from "node:test";

import {
  buildApplyRequest,
  cancelDryRunState,
  controlStateForDryRun,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/workbench-state.mjs";

test("control state requires confirmation before elevated apply", () => {
  const dryRun = {
    plan: {
      summary: "Restart ComfyUI",
      actions: [{ type: "service.restart_container", payload: {} }],
      requires_confirmation: true,
      plan_hash: "abc123",
    },
  };

  assert.deepEqual(controlStateForDryRun(dryRun, false), {
    needsConfirmation: true,
    confirmHidden: false,
    cancelHidden: false,
    applyDisabled: true,
  });
  assert.deepEqual(controlStateForDryRun(dryRun, true), {
    needsConfirmation: true,
    confirmHidden: false,
    cancelHidden: false,
    applyDisabled: false,
  });
});

test("control state allows canvas apply without elevated confirmation", () => {
  const dryRun = {
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  };

  assert.deepEqual(controlStateForDryRun(dryRun, false), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: true,
    applyDisabled: false,
  });
});

test("buildApplyRequest carries confirmed only for elevated plans", () => {
  const elevated = {
    plan: {
      summary: "Restart ComfyUI",
      actions: [{ type: "service.restart_container", payload: {} }],
      requires_confirmation: true,
      plan_hash: "abc123",
    },
  };
  const canvas = {
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  };

  assert.deepEqual(buildApplyRequest(elevated, true), {
    approved_hash: "abc123",
    plan: {
      summary: "Restart ComfyUI",
      actions: [{ type: "service.restart_container", payload: {} }],
      requires_confirmation: true,
      plan_hash: "abc123",
      confirmed: true,
    },
  });
  assert.deepEqual(buildApplyRequest(canvas, true), {
    approved_hash: "canvas123",
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  });
});

test("cancel clears dry-run state and emits cancellation output", () => {
  assert.deepEqual(cancelDryRunState(), {
    lastDryRun: null,
    confirmChecked: false,
    output: { ok: false, error: "user_cancelled" },
  });
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  applyCompletionState,
  buildApplyRequest,
  cancelDryRunState,
  contextRefreshState,
  controlStateForDryRun,
  planCompletionState,
  planNeedsBrowserWorkflow,
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

test("control state disables apply while an apply request is in flight", () => {
  const dryRun = {
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  };

  assert.deepEqual(controlStateForDryRun(dryRun, false, true), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: false,
    applyDisabled: true,
  });
});

test("control state allows canvas apply and cancel without elevated confirmation", () => {
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
    cancelHidden: false,
    applyDisabled: false,
  });
});

test("control state hides cancel when there is no active plan", () => {
  assert.deepEqual(controlStateForDryRun(null, false), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: true,
    applyDisabled: true,
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

test("planNeedsBrowserWorkflow only matches browser-backed workflow saves", () => {
  assert.equal(
    planNeedsBrowserWorkflow({
      actions: [
        {
          type: "workflow.save",
          payload: { path: "agent/sample.json", workflow_from_browser: true },
        },
      ],
    }),
    true,
  );
  assert.equal(
    planNeedsBrowserWorkflow({
      actions: [
        {
          type: "workflow.save",
          payload: { path: "agent/sample.json", workflow: { nodes: [] } },
        },
      ],
    }),
    false,
  );
  assert.equal(
    planNeedsBrowserWorkflow({
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
    }),
    false,
  );
});

test("buildApplyRequest attaches browser workflow only when the plan needs it", () => {
  const dryRun = {
    plan: {
      summary: "Save workflow",
      actions: [
        {
          type: "workflow.save",
          payload: { path: "agent/sample.json", workflow_from_browser: true },
        },
      ],
      requires_confirmation: true,
      plan_hash: "save123",
    },
  };

  assert.deepEqual(buildApplyRequest(dryRun, true, { nodes: [{ id: 12 }] }), {
    approved_hash: "save123",
    browser_workflow: { nodes: [{ id: 12 }] },
    plan: {
      summary: "Save workflow",
      actions: [
        {
          type: "workflow.save",
          payload: { path: "agent/sample.json", workflow_from_browser: true },
        },
      ],
      requires_confirmation: true,
      plan_hash: "save123",
      confirmed: true,
    },
  });
});

test("buildApplyRequest omits browser workflow for ordinary graph edits", () => {
  const dryRun = {
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  };

  assert.deepEqual(buildApplyRequest(dryRun, false, { nodes: [{ id: 7 }] }), {
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

test("successful apply clears active plan and confirmation state", () => {
  const dryRun = {
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 7 } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  };

  const state = applyCompletionState({ ok: true }, dryRun, true);

  assert.deepEqual(state, {
    lastDryRun: null,
    confirmChecked: false,
  });
  assert.deepEqual(controlStateForDryRun(state.lastDryRun, state.confirmChecked), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: true,
    applyDisabled: true,
  });
});

test("failed apply preserves active plan for retry or cancellation", () => {
  const dryRun = {
    plan: {
      summary: "Restart ComfyUI",
      actions: [{ type: "service.restart_container", payload: {} }],
      requires_confirmation: true,
      plan_hash: "abc123",
    },
  };

  assert.deepEqual(applyCompletionState({ ok: false, error: "boom" }, dryRun, true), {
    lastDryRun: dryRun,
    confirmChecked: true,
  });
});

test("ui state smoke flow covers context plan confirm cancel and apply", () => {
  const elevated = {
    plan: {
      summary: "Restart ComfyUI",
      actions: [{ type: "service.restart_container", payload: { container: "comfyui-gb10" } }],
      requires_confirmation: true,
      plan_hash: "restart123",
    },
  };
  const canvas = {
    plan: {
      summary: "Edit prompt",
      actions: [{ type: "graph.set_widget", payload: { node_id: 12, widget: "text", value: "neon" } }],
      requires_confirmation: false,
      plan_hash: "canvas123",
    },
  };

  const contextState = contextRefreshState();
  assert.deepEqual(controlStateForDryRun(contextState.lastDryRun, contextState.confirmChecked), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: true,
    applyDisabled: true,
  });

  const plannedElevated = planCompletionState(elevated);
  assert.deepEqual(controlStateForDryRun(plannedElevated.lastDryRun, plannedElevated.confirmChecked), {
    needsConfirmation: true,
    confirmHidden: false,
    cancelHidden: false,
    applyDisabled: true,
  });
  assert.equal(controlStateForDryRun(plannedElevated.lastDryRun, true).applyDisabled, false);

  const cancelled = cancelDryRunState();
  assert.deepEqual(controlStateForDryRun(cancelled.lastDryRun, cancelled.confirmChecked), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: true,
    applyDisabled: true,
  });

  const plannedCanvas = planCompletionState(canvas);
  assert.equal(controlStateForDryRun(plannedCanvas.lastDryRun, plannedCanvas.confirmChecked).applyDisabled, false);

  const applied = applyCompletionState({ ok: true }, plannedCanvas.lastDryRun, plannedCanvas.confirmChecked);
  assert.deepEqual(controlStateForDryRun(applied.lastDryRun, applied.confirmChecked), {
    needsConfirmation: false,
    confirmHidden: true,
    cancelHidden: true,
    applyDisabled: true,
  });
});

export function controlStateForDryRun(lastDryRun, confirmChecked) {
  const needsConfirmation = Boolean(lastDryRun?.plan?.requires_confirmation);
  return {
    needsConfirmation,
    confirmHidden: !needsConfirmation,
    cancelHidden: !needsConfirmation,
    applyDisabled: !lastDryRun?.plan || (needsConfirmation && !confirmChecked),
  };
}

export function planNeedsBrowserWorkflow(plan) {
  return Boolean(
    plan?.actions?.some(
      (action) =>
        action?.type === "workflow.save" &&
        action?.payload?.workflow_from_browser === true &&
        action?.payload?.workflow === undefined,
    ),
  );
}

export function buildApplyRequest(lastDryRun, confirmChecked, browserWorkflow = null) {
  if (!lastDryRun?.plan) {
    return null;
  }
  const plan = { ...lastDryRun.plan };
  if (lastDryRun.plan.requires_confirmation) {
    plan.confirmed = confirmChecked;
  }
  const request = {
    plan,
    approved_hash: lastDryRun.plan.plan_hash,
  };
  if (browserWorkflow && planNeedsBrowserWorkflow(lastDryRun.plan)) {
    request.browser_workflow = browserWorkflow;
  }
  return request;
}

export function cancelDryRunState() {
  return {
    lastDryRun: null,
    confirmChecked: false,
    output: { ok: false, error: "user_cancelled" },
  };
}

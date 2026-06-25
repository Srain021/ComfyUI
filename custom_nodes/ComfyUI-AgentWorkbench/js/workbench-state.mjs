export function controlStateForDryRun(lastDryRun, confirmChecked) {
  const needsConfirmation = Boolean(lastDryRun?.plan?.requires_confirmation);
  return {
    needsConfirmation,
    confirmHidden: !needsConfirmation,
    cancelHidden: !needsConfirmation,
    applyDisabled: !lastDryRun?.plan || (needsConfirmation && !confirmChecked),
  };
}

export function buildApplyRequest(lastDryRun, confirmChecked) {
  if (!lastDryRun?.plan) {
    return null;
  }
  const plan = { ...lastDryRun.plan };
  if (lastDryRun.plan.requires_confirmation) {
    plan.confirmed = confirmChecked;
  }
  return {
    plan,
    approved_hash: lastDryRun.plan.plan_hash,
  };
}

export function cancelDryRunState() {
  return {
    lastDryRun: null,
    confirmChecked: false,
    output: { ok: false, error: "user_cancelled" },
  };
}

function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

function planActions(plan) {
  return Array.isArray(plan?.actions) ? plan.actions : [];
}

function isContextOnlyPlan(plan) {
  const actions = planActions(plan);
  return actions.length === 1 && actions[0]?.type === "context.collect";
}

function requestedMessage(plan) {
  const action = planActions(plan)[0];
  const message = action?.payload?.message;
  if (typeof message === "string" && message.trim()) {
    return message.trim();
  }
  return null;
}

function dryRunResponse(value) {
  const plan = value?.plan || {};
  const summary = typeof plan.summary === "string" && plan.summary
    ? plan.summary
    : "Inspect current ComfyUI context";

  if (isContextOnlyPlan(plan)) {
    const message = requestedMessage(plan);
    return {
      title: "我收到了",
      message: message
        ? `你发的是“${message}”。这还不是一个明确的 ComfyUI 操作；我可以查看当前工作流上下文，或者你可以直接说“把 KSampler 步数改成 30”“列出已安装插件”。`
        : "我可以先查看当前工作流上下文。你也可以直接告诉我要改哪个节点、插件或服务。",
      detailsLabel: "计划详情",
      detailsText: prettyJson(value),
    };
  }

  if (plan.requires_confirmation === true) {
    return {
      title: "需要确认",
      message: `我生成了一个高风险计划：${summary}。确认无误后勾选确认，再点“执行”。`,
      detailsLabel: "计划详情",
      detailsText: prettyJson(value),
    };
  }

  return {
    title: "计划已生成",
    message: `我生成了计划：${summary}。确认无误后点“执行”。`,
    detailsLabel: "计划详情",
    detailsText: prettyJson(value),
  };
}

function appliedResponse(value) {
  if (value?.ok === false) {
    return {
      title: "执行失败",
      message: typeof value.error === "string" ? value.error : "执行时遇到错误，请展开详情查看。",
      detailsLabel: "错误详情",
      detailsText: prettyJson(value),
    };
  }
  return {
    title: "已执行",
    message: "计划已经应用到当前 ComfyUI。执行结果在详情里。",
    detailsLabel: "执行详情",
    detailsText: prettyJson(value),
  };
}

function assistantResponse(value) {
  const title = typeof value?.assistant?.title === "string" && value.assistant.title
    ? value.assistant.title
    : "Agent";
  const message = typeof value?.assistant?.message === "string" && value.assistant.message
    ? value.assistant.message
    : "我拿到了 AI 返回，但内容为空。";
  const unavailable = value?.status === "ai_unavailable";
  const failed = value?.status === "ai_error";
  return {
    title,
    message,
    detailsLabel: unavailable ? "连接详情" : failed ? "错误详情" : "AI 详情",
    detailsText: prettyJson(value),
  };
}

export function formatWorkbenchResponse(value) {
  if (value?.status === "assistant_reply" || value?.status === "ai_unavailable" || value?.status === "ai_error") {
    return assistantResponse(value);
  }
  if (value?.status === "dry_run" && value?.plan) {
    return dryRunResponse(value);
  }
  if (value?.status === "applied" || Array.isArray(value?.applied)) {
    return appliedResponse(value);
  }
  if (value?.ok === false) {
    return {
      title: "出错了",
      message: typeof value.error === "string" ? value.error : "请求失败，请展开详情查看。",
      detailsLabel: "错误详情",
      detailsText: prettyJson(value),
    };
  }
  return {
    title: "结果",
    message: "我拿到了返回结果，详情如下。",
    detailsLabel: "详情",
    detailsText: prettyJson(value),
  };
}

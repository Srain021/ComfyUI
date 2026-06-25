import { app } from "../../scripts/app.js";

function currentGraph() {
  return app.canvas?.graph || app.graph;
}

function markGraphDirty(graph) {
  graph.afterChange?.();
  app.canvas?.setDirty?.(true, true);
  graph.setDirtyCanvas?.(true, true);
}

function requireNode(graph, nodeId) {
  const node = graph.getNodeById(nodeId) || app.graph.getNodeById?.(nodeId);
  if (!node) {
    throw new Error(`Node not found: ${nodeId}`);
  }
  return node;
}

function resolveSlot(slots, value, label) {
  if (value === undefined || value === null) {
    return 0;
  }
  if (Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "number" && Number.isInteger(Number(value))) {
    return Number(value);
  }
  if (typeof value === "string" && /^\d+$/.test(value)) {
    return Number(value);
  }
  const index = (slots || []).findIndex((slot) => slot?.name === value);
  if (index >= 0) {
    return index;
  }
  throw new Error(`${label} slot not found: ${value}`);
}

function setWidgetValue(node, name, value) {
  const widget = (node.widgets || []).find((item) => item.name === name);
  if (!widget) {
    throw new Error(`Widget not found: ${name}`);
  }
  widget.value = value;
  return widget;
}

function setWidgetValues(node, widgets) {
  if (!widgets || typeof widgets !== "object") {
    return [];
  }
  const entries = Array.isArray(widgets) ? widgets.map((item) => [item.name, item.value]) : Object.entries(widgets);
  return entries
    .filter(([name]) => typeof name === "string")
    .map(([name, value]) => setWidgetValue(node, name, value).name);
}

function resolveNodeMode(mode) {
  const liteGraph = globalThis.LiteGraph || {};
  if (Number.isInteger(mode)) {
    return mode;
  }
  if (typeof mode !== "string") {
    throw new Error("graph.set_mode requires a mode");
  }
  const globalAlways = globalThis.LiteGraph && globalThis.LiteGraph.ALWAYS;
  const globalNever = globalThis.LiteGraph && globalThis.LiteGraph.NEVER;
  const globalBypass = globalThis.LiteGraph && globalThis.LiteGraph.BYPASS;
  const modes = {
    always: globalAlways ?? liteGraph.ALWAYS ?? 0,
    enable: globalAlways ?? liteGraph.ALWAYS ?? 0,
    enabled: globalAlways ?? liteGraph.ALWAYS ?? 0,
    mute: globalNever ?? liteGraph.NEVER ?? 2,
    muted: globalNever ?? liteGraph.NEVER ?? 2,
    never: globalNever ?? liteGraph.NEVER ?? 2,
    bypass: globalBypass ?? liteGraph.BYPASS ?? 4,
  };
  const resolved = modes[mode.toLowerCase()];
  if (resolved === undefined) {
    throw new Error(`Unsupported node mode: ${mode}`);
  }
  return resolved;
}

function resolvePosition(pos) {
  if (!Array.isArray(pos) || pos.length < 2) {
    throw new Error("graph.set_position requires pos [x, y]");
  }
  const nextPos = [Number(pos[0]), Number(pos[1])];
  if (!Number.isFinite(nextPos[0]) || !Number.isFinite(nextPos[1])) {
    throw new Error("graph.set_position requires finite coordinates");
  }
  return nextPos;
}

export function applyGraphAction(action) {
  if (action.type === "graph.set_widget") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    const widget = setWidgetValue(node, action.payload.widget, action.payload.value);
    app.graph.setDirtyCanvas(true, true);
    return { type: action.type, node_id: node.id, widget: widget.name };
  }
  if (action.type === "graph.add_node") {
    const graph = currentGraph();
    const nodeType = action.payload.node_type;
    if (typeof nodeType !== "string" || !nodeType) {
      throw new Error("graph.add_node requires node_type");
    }
    if (!globalThis.LiteGraph?.createNode) {
      throw new Error("LiteGraph.createNode is unavailable");
    }
    const node = globalThis.LiteGraph.createNode(nodeType);
    if (!node) {
      throw new Error(`Could not create node: ${nodeType}`);
    }
    if (Array.isArray(action.payload.pos) && action.payload.pos.length >= 2) {
      node.pos = [Number(action.payload.pos[0]), Number(action.payload.pos[1])];
    }
    if (typeof action.payload.title === "string") {
      node.title = action.payload.title;
    }
    graph.add(node, false);
    const changedWidgets = setWidgetValues(node, action.payload.widgets);
    markGraphDirty(graph);
    return { type: action.type, node_id: node.id, node_type: nodeType, widgets: changedWidgets };
  }
  if (action.type === "graph.connect") {
    const graph = currentGraph();
    const origin = requireNode(graph, action.payload.origin_node_id);
    const target = requireNode(graph, action.payload.target_node_id);
    const originSlot = resolveSlot(origin.outputs, action.payload.origin_slot, "Origin");
    const targetSlot = resolveSlot(target.inputs, action.payload.target_slot, "Target");
    origin.connect(originSlot, target, targetSlot);
    markGraphDirty(graph);
    return {
      type: action.type,
      origin_node_id: origin.id,
      origin_slot: originSlot,
      target_node_id: target.id,
      target_slot: targetSlot,
    };
  }
  if (action.type === "graph.disconnect") {
    const graph = currentGraph();
    const target = requireNode(graph, action.payload.target_node_id);
    const targetSlot = resolveSlot(target.inputs, action.payload.target_slot, "Target");
    if (typeof target.disconnectInput !== "function") {
      throw new Error("Target node cannot disconnect inputs");
    }
    target.disconnectInput(targetSlot);
    markGraphDirty(graph);
    return { type: action.type, target_node_id: target.id, target_slot: targetSlot };
  }
  if (action.type === "graph.delete_node") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    graph.remove(node);
    markGraphDirty(graph);
    return { type: action.type, node_id: node.id };
  }
  if (action.type === "graph.set_mode") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    node.mode = resolveNodeMode(action.payload.mode);
    markGraphDirty(graph);
    return { type: action.type, node_id: node.id, mode: node.mode };
  }
  if (action.type === "graph.set_title") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    if (typeof action.payload.title !== "string" || !action.payload.title) {
      throw new Error("graph.set_title requires title");
    }
    node.title = action.payload.title;
    markGraphDirty(graph);
    return { type: action.type, node_id: node.id, title: node.title };
  }
  if (action.type === "graph.set_position") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    node.pos = resolvePosition(action.payload.pos);
    markGraphDirty(graph);
    return { type: action.type, node_id: node.id, pos: node.pos };
  }
  throw new Error(`Unsupported browser graph action: ${action.type}`);
}

export function applyGraphActions(actions) {
  return actions
    .filter((action) => action.type.startsWith("graph."))
    .map((action) => applyGraphAction(action));
}

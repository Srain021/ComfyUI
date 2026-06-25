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
  throw new Error(`Unsupported browser graph action: ${action.type}`);
}

export function applyGraphActions(actions) {
  return actions
    .filter((action) => action.type.startsWith("graph."))
    .map((action) => applyGraphAction(action));
}

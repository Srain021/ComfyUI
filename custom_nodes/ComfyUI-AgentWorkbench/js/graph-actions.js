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

function graphLinks(graph) {
  const links = graph.links || [];
  return Array.isArray(links) ? links.filter(Boolean) : Object.values(links).filter(Boolean);
}

function matchesOptional(value, expected) {
  return expected === undefined || expected === null || String(value) === String(expected);
}

function matchingLinks(graph, payload) {
  return graphLinks(graph).filter((link) => (
    matchesOptional(link.origin_id, payload.origin_node_id)
    && matchesOptional(link.origin_slot, payload.origin_slot)
    && matchesOptional(link.target_id, payload.target_node_id)
    && matchesOptional(link.target_slot, payload.target_slot)
  ));
}

function disconnectGraphLinks(graph, links) {
  if (!links.length) {
    throw new Error("No matching graph links to disconnect");
  }
  const rows = links.map((link) => {
    const target = requireNode(graph, link.target_id);
    if (typeof target.disconnectInput !== "function") {
      throw new Error("Target node cannot disconnect inputs");
    }
    target.disconnectInput(link.target_slot);
    return {
      origin_node_id: link.origin_id,
      origin_slot: link.origin_slot,
      target_node_id: target.id,
      target_slot: link.target_slot,
    };
  });
  markGraphDirty(graph);
  return rows;
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

function cloneWidgetValue(value) {
  if (value === null || typeof value !== "object") {
    return value;
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return value;
  }
}

function copyWidgetValues(source, target) {
  const sourceWidgets = source.widgets || [];
  const targetWidgets = target.widgets || [];
  for (const sourceWidget of sourceWidgets) {
    const targetWidget = targetWidgets.find((item) => item.name === sourceWidget.name);
    if (targetWidget) {
      targetWidget.value = cloneWidgetValue(sourceWidget.value);
    }
  }
}

function duplicateOffset(payload) {
  if (payload.offset === undefined || payload.offset === null) {
    return [40, 40];
  }
  return resolvePosition(payload.offset);
}

function cloneGraphNode(graph, source, payload) {
  let copy = null;
  if (typeof source.clone === "function") {
    copy = source.clone();
  } else if (globalThis.LiteGraph?.createNode) {
    copy = globalThis.LiteGraph.createNode(source.type);
  }
  if (!copy) {
    throw new Error(`Could not duplicate node: ${source.id}`);
  }
  delete copy.id;
  copy.id = undefined;
  if (typeof source.title === "string") {
    copy.title = source.title;
  }
  if (source.mode !== undefined) {
    copy.mode = source.mode;
  }
  const offset = duplicateOffset(payload);
  const sourcePos = resolvePosition(source.pos || [0, 0]);
  copy.pos = [sourcePos[0] + offset[0], sourcePos[1] + offset[1]];
  graph.add(copy, false);
  copyWidgetValues(source, copy);
  return copy;
}

function resolveGraphColor(value, label) {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`graph.set_color requires ${label} to be a string`);
  }
  return value.trim();
}

function repaintCanvas(graph) {
  app.canvas?.setDirty?.(true, true);
  graph.setDirtyCanvas?.(true, true);
}

function selectGraphNode(graph, node, focus) {
  for (const item of graph._nodes || graph.nodes || []) {
    item.selected = false;
  }
  node.selected = true;
  if (typeof app.canvas?.selectNode === "function") {
    app.canvas.selectNode(node, false);
  }
  if (focus && typeof app.canvas?.centerOnNode === "function") {
    app.canvas.centerOnNode(node);
  }
  repaintCanvas(graph);
}

function selectGraphNodes(graph, nodes, focus) {
  for (const item of graph._nodes || graph.nodes || []) {
    item.selected = false;
  }
  const selectedNodes = {};
  for (const node of nodes) {
    node.selected = true;
    selectedNodes[node.id] = node;
  }
  if (app.canvas && "selected_nodes" in app.canvas) {
    app.canvas.selected_nodes = selectedNodes;
  }
  if (focus && nodes[0] && typeof app.canvas?.centerOnNode === "function") {
    app.canvas.centerOnNode(nodes[0]);
  }
  repaintCanvas(graph);
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
    if (action.payload.node_id !== undefined) {
      const node = requireNode(graph, action.payload.node_id);
      const links = graphLinks(graph).filter((link) => (
        String(link.origin_id) === String(node.id) || String(link.target_id) === String(node.id)
      ));
      return { type: action.type, links: disconnectGraphLinks(graph, links) };
    }
    if (action.payload.origin_node_id !== undefined) {
      const links = matchingLinks(graph, action.payload);
      return { type: action.type, links: disconnectGraphLinks(graph, links) };
    }
    if (action.payload.target_node_id !== undefined && action.payload.target_slot === undefined) {
      const links = matchingLinks(graph, action.payload);
      return { type: action.type, links: disconnectGraphLinks(graph, links) };
    }
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
  if (action.type === "graph.duplicate_node") {
    const graph = currentGraph();
    const source = requireNode(graph, action.payload.node_id);
    const copy = cloneGraphNode(graph, source, action.payload || {});
    markGraphDirty(graph);
    if (action.payload.select !== false) {
      selectGraphNode(graph, copy, false);
    }
    return { type: action.type, source_node_id: source.id, node_id: copy.id, pos: copy.pos };
  }
  if (action.type === "graph.set_color") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    const color = resolveGraphColor(action.payload.color, "color");
    const bgcolor = resolveGraphColor(action.payload.bgcolor, "bgcolor");
    node.color = color;
    if (bgcolor !== null) {
      node.bgcolor = bgcolor;
    }
    markGraphDirty(graph);
    return { type: action.type, node_id: node.id, color: node.color, bgcolor: node.bgcolor };
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
  if (action.type === "graph.select_node") {
    const graph = currentGraph();
    const node = requireNode(graph, action.payload.node_id);
    const focus = action.payload.focus === true;
    selectGraphNode(graph, node, focus);
    return { type: action.type, node_id: node.id, focus };
  }
  if (action.type === "graph.select_nodes") {
    const graph = currentGraph();
    if (!Array.isArray(action.payload.node_ids) || !action.payload.node_ids.length) {
      throw new Error("graph.select_nodes requires node_ids");
    }
    const nodes = action.payload.node_ids.map((nodeId) => requireNode(graph, nodeId));
    const focus = action.payload.focus === true;
    selectGraphNodes(graph, nodes, focus);
    return { type: action.type, node_ids: nodes.map((node) => node.id), focus };
  }
  throw new Error(`Unsupported browser graph action: ${action.type}`);
}

export function applyGraphActions(actions) {
  return actions
    .filter((action) => action.type.startsWith("graph."))
    .map((action) => applyGraphAction(action));
}

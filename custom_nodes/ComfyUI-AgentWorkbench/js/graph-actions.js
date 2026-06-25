import { app } from "../../scripts/app.js";

export function applyGraphAction(action) {
  if (action.type === "graph.set_widget") {
    const node = app.graph.getNodeById(action.payload.node_id);
    if (!node) {
      throw new Error(`Node not found: ${action.payload.node_id}`);
    }
    const widget = (node.widgets || []).find((item) => item.name === action.payload.widget);
    if (!widget) {
      throw new Error(`Widget not found: ${action.payload.widget}`);
    }
    widget.value = action.payload.value;
    app.graph.setDirtyCanvas(true, true);
    return { type: action.type, node_id: node.id, widget: widget.name };
  }
  throw new Error(`Unsupported browser graph action: ${action.type}`);
}

export function applyGraphActions(actions) {
  return actions
    .filter((action) => action.type.startsWith("graph."))
    .map((action) => applyGraphAction(action));
}

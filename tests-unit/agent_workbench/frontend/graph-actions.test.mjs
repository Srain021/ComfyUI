import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function loadGraphActions(app) {
  const sourceUrl = new URL(
    "../../../custom_nodes/ComfyUI-AgentWorkbench/js/graph-actions.js",
    import.meta.url,
  );
  const source = await readFile(sourceUrl, "utf8");
  const patched = source.replace(
    'import { app } from "../../scripts/app.js";',
    "const app = globalThis.__agentWorkbenchTestApp;",
  );
  globalThis.__agentWorkbenchTestApp = app;
  const encoded = Buffer.from(patched).toString("base64");
  return import(`data:text/javascript;base64,${encoded}#${Date.now()}`);
}

function createGraph() {
  let nextNodeId = 100;
  let nextLinkId = 1;
  const graph = {
    _nodes: [],
    links: [],
    add(node) {
      if (node.id === undefined || node.id === null) {
        node.id = nextNodeId++;
      }
      node.graph = graph;
      graph._nodes.push(node);
    },
    getNodeById(nodeId) {
      return graph._nodes.find((node) => String(node.id) === String(nodeId));
    },
    setDirtyCanvas() {},
    afterChange() {},
    connect(origin, originSlot, target, targetSlot) {
      graph.links.push({
        id: nextLinkId++,
        origin_id: origin.id,
        origin_slot: originSlot,
        target_id: target.id,
        target_slot: targetSlot,
        type: origin.outputs?.[originSlot]?.type,
      });
    },
  };
  return graph;
}

function createNode(id, type, slots = {}) {
  return {
    id,
    type,
    title: type,
    pos: [0, 0],
    inputs: slots.inputs || [],
    outputs: slots.outputs || [],
    widgets: slots.widgets || [],
    connect(originSlot, target, targetSlot) {
      this.graph.connect(this, originSlot, target, targetSlot);
    },
  };
}

test("applyGraphActions accepts widget_name aliases from Codex action payloads", async () => {
  const graph = createGraph();
  graph.add(createNode(4, "CLIPTextEncode", {
    widgets: [{ name: "text", value: "old prompt" }],
  }));
  const app = {
    graph,
    canvas: {
      graph,
      setDirty() {},
    },
  };

  const { applyGraphActions } = await loadGraphActions(app);
  const rows = applyGraphActions([
    {
      type: "graph.set_widget",
      payload: {
        node_id: 4,
        widget_name: "text",
        value: "handsome husky",
      },
    },
  ]);

  assert.equal(graph.getNodeById(4).widgets[0].value, "handsome husky");
  assert.equal(rows[0].widget, "text");
});

test("applyGraphActions lets later graph actions reference newly added nodes", async () => {
  const graph = createGraph();
  graph.add(createNode(9, "KSampler", {
    outputs: [{ name: "LATENT", type: "LATENT" }],
  }));
  const app = {
    graph,
    canvas: {
      graph,
      setDirty() {},
    },
  };
  globalThis.LiteGraph = {
    createNode(nodeType) {
      if (nodeType !== "VAEDecode") {
        return null;
      }
      return createNode(null, nodeType, {
        inputs: [
          { name: "samples", type: "LATENT" },
          { name: "vae", type: "VAE" },
        ],
        outputs: [{ name: "IMAGE", type: "IMAGE" }],
      });
    },
  };

  const { applyGraphActions } = await loadGraphActions(app);
  const rows = applyGraphActions([
    {
      type: "graph.add_node",
      payload: { node_type: "VAEDecode", ref: "decode" },
    },
    {
      type: "graph.connect",
      payload: {
        origin_node_id: 9,
        origin_slot: "LATENT",
        target_node_ref: "decode",
        target_slot: "samples",
      },
    },
  ]);

  const added = graph._nodes.find((node) => node.type === "VAEDecode");
  assert.ok(added);
  assert.equal(rows[0].ref, "decode");
  assert.equal(rows[1].target_node_id, added.id);
  assert.deepEqual(graph.links, [
    {
      id: 1,
      origin_id: 9,
      origin_slot: 0,
      target_id: added.id,
      target_slot: 0,
      type: "LATENT",
    },
  ]);
});

test("applyGraphActions can connect a newly added node into an existing node", async () => {
  const graph = createGraph();
  graph.add(createNode(9, "KSampler", {
    inputs: [
      { name: "model", type: "MODEL" },
      { name: "positive", type: "CONDITIONING" },
      { name: "negative", type: "CONDITIONING" },
    ],
  }));
  const app = {
    graph,
    canvas: {
      graph,
      setDirty() {},
    },
  };
  globalThis.LiteGraph = {
    createNode(nodeType) {
      if (nodeType !== "CLIPTextEncode") {
        return null;
      }
      return createNode(null, nodeType, {
        outputs: [{ name: "CONDITIONING", type: "CONDITIONING" }],
        widgets: [{ name: "text", value: "" }],
      });
    },
  };

  const { applyGraphActions } = await loadGraphActions(app);
  const rows = applyGraphActions([
    {
      type: "graph.add_node",
      payload: {
        node_type: "CLIPTextEncode",
        ref: "prompt",
        widgets: { text: "neon skyline" },
      },
    },
    {
      type: "graph.connect",
      payload: {
        origin_node_ref: "prompt",
        origin_slot: "CONDITIONING",
        target_node_id: 9,
        target_slot: "positive",
      },
    },
  ]);

  const added = graph._nodes.find((node) => node.type === "CLIPTextEncode");
  assert.ok(added);
  assert.equal(added.widgets[0].value, "neon skyline");
  assert.equal(rows[0].ref, "prompt");
  assert.equal(rows[1].origin_node_id, added.id);
  assert.deepEqual(graph.links, [
    {
      id: 1,
      origin_id: added.id,
      origin_slot: 0,
      target_id: 9,
      target_slot: 1,
      type: "CONDITIONING",
    },
  ]);
});

test("applyGraphActions can collapse and expand an existing node", async () => {
  const graph = createGraph();
  graph.add(createNode(12, "CLIPTextEncode"));
  const app = {
    graph,
    canvas: {
      graph,
      setDirty() {},
    },
  };
  globalThis.LiteGraph = {};

  const { applyGraphActions } = await loadGraphActions(app);
  const collapsedRows = applyGraphActions([
    {
      type: "graph.set_collapsed",
      payload: { node_id: 12, collapsed: true },
    },
  ]);

  assert.equal(graph.getNodeById(12).collapsed, true);
  assert.deepEqual(collapsedRows, [{ type: "graph.set_collapsed", node_id: 12, collapsed: true }]);

  const expandedRows = applyGraphActions([
    {
      type: "graph.set_collapsed",
      payload: { node_id: 12, collapsed: false },
    },
  ]);

  assert.equal(graph.getNodeById(12).collapsed, false);
  assert.deepEqual(expandedRows, [{ type: "graph.set_collapsed", node_id: 12, collapsed: false }]);
});

test("applyGraphActions can resize an existing node box", async () => {
  const graph = createGraph();
  const node = createNode(12, "CLIPTextEncode");
  node.size = [200, 100];
  graph.add(node);
  const app = {
    graph,
    canvas: {
      graph,
      setDirty() {},
    },
  };
  globalThis.LiteGraph = {};

  const { applyGraphActions } = await loadGraphActions(app);
  const rows = applyGraphActions([
    {
      type: "graph.set_size",
      payload: { node_id: 12, size: [420, 260] },
    },
  ]);

  assert.deepEqual(graph.getNodeById(12).size, [420, 260]);
  assert.deepEqual(rows, [{ type: "graph.set_size", node_id: 12, size: [420, 260] }]);
});

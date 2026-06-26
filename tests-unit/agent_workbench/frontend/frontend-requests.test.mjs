import assert from "node:assert/strict";
import test from "node:test";

import {
  executeFrontendRequest,
  filterFrontendResponse,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/frontend-requests.mjs";

function jsonResponse(status, payload) {
  return {
    status,
    async json() {
      return payload;
    },
  };
}

test("executeFrontendRequest includes json body for read-only manager GET requests", async () => {
  const calls = [];
  const result = await executeFrontendRequest(
    {
      method: "GET",
      path: "/customnode/installed",
      response_filter: { type: "custom_node.list", scope: "installed", limit: 50 },
    },
    async (path, options) => {
      calls.push({ path, options });
      return jsonResponse(200, {
        "ComfyUI-Impact-Pack": { enabled: true, ver: "1.0.0" },
      });
    },
  );

  assert.deepEqual(calls, [
    { path: "/customnode/installed", options: { method: "GET", headers: {} } },
  ]);
  assert.equal(result.status, 200);
  assert.deepEqual(result.response_json, {
    "ComfyUI-Impact-Pack": { enabled: true, ver: "1.0.0" },
  });
  assert.deepEqual(result.filtered, {
    type: "custom_node.list",
    count: 1,
    items: [
      {
        id: "ComfyUI-Impact-Pack",
        enabled: true,
        ver: "1.0.0",
      },
    ],
  });
});

test("filterFrontendResponse searches manager node_packs by id title and description", () => {
  const filtered = filterFrontendResponse(
    {
      channel: "default",
      node_packs: {
        "ComfyUI-Impact-Pack": {
          title: "Impact Pack",
          description: "detectors and detailers",
          installed: "True",
        },
        "ComfyUI-VideoHelperSuite": {
          title: "Video Helper Suite",
          description: "video combine",
          installed: "False",
        },
      },
    },
    { type: "custom_node.search", query: "impact", limit: 5 },
  );

  assert.deepEqual(filtered, {
    type: "custom_node.search",
    query: "impact",
    count: 1,
    items: [
      {
        id: "ComfyUI-Impact-Pack",
        title: "Impact Pack",
        description: "detectors and detailers",
        installed: "True",
      },
    ],
  });
});

const DEFAULT_LIST_LIMIT = 50;
const DEFAULT_SEARCH_LIMIT = 20;

function clampLimit(value, fallback) {
  const number = Number.parseInt(value, 10);
  if (!Number.isFinite(number)) {
    return fallback;
  }
  return Math.max(1, Math.min(number, 200));
}

function itemRowsFromObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value).map(([id, row]) => {
    if (row && typeof row === "object" && !Array.isArray(row)) {
      return { id, ...row };
    }
    return { id, value: row };
  });
}

function customNodeRows(payload) {
  if (payload?.node_packs && typeof payload.node_packs === "object") {
    return itemRowsFromObject(payload.node_packs);
  }
  return itemRowsFromObject(payload);
}

function searchableText(row) {
  return [
    row.id,
    row.title,
    row.name,
    row.description,
    row.author,
    row.reference,
  ]
    .filter((value) => typeof value === "string")
    .join(" ")
    .toLowerCase();
}

export function filterFrontendResponse(payload, filter) {
  if (!filter || typeof filter !== "object") {
    return null;
  }
  const type = filter.type;
  if (type === "custom_node.list") {
    const limit = clampLimit(filter.limit, DEFAULT_LIST_LIMIT);
    const items = customNodeRows(payload).slice(0, limit);
    return { type, count: items.length, items };
  }
  if (type === "custom_node.search") {
    const query = typeof filter.query === "string" ? filter.query.trim() : "";
    const limit = clampLimit(filter.limit, DEFAULT_SEARCH_LIMIT);
    const needles = query.toLowerCase().split(/\s+/).filter(Boolean);
    const items = customNodeRows(payload)
      .filter((row) => {
        const haystack = searchableText(row);
        return needles.every((needle) => haystack.includes(needle));
      })
      .slice(0, limit);
    return { type, query, count: items.length, items };
  }
  return null;
}

export async function executeFrontendRequest(request, fetchApi) {
  const options = { method: request.method || "POST", headers: {} };
  if (request.json) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(request.json);
  }
  if (request.body) {
    options.body = request.body;
  }
  const response = await fetchApi(request.path, options);
  const result = { path: request.path, status: response.status };
  if (request.method === "GET" || request.response_filter) {
    const payload = await response.json().catch(() => null);
    if (payload !== null) {
      result.response_json = payload;
      const filtered = filterFrontendResponse(payload, request.response_filter);
      if (filtered !== null) {
        result.filtered = filtered;
      }
    }
  }
  if (request.start_queue === true && response.status === 200) {
    const queueResponse = await fetchApi("/manager/queue/start", { method: "POST" });
    result.queue_start_status = queueResponse.status;
  }
  return result;
}

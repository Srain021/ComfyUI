const DEFAULT_MAX_FILE_BYTES = 6 * 1024 * 1024;
const DEFAULT_MAX_TEXT_CHARS = 12000;

function defaultId() {
  const random = Math.random().toString(36).slice(2, 10);
  return `att-${Date.now().toString(36)}-${random}`;
}

function bytesToBase64(bytes) {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(bytes).toString("base64");
  }
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function looksTextual(file) {
  const mime = file.type || "";
  return (
    mime.startsWith("text/")
    || mime === "application/json"
    || mime === "application/javascript"
    || /\.(txt|json|md|csv|yaml|yml|log|py|js|ts|css|html)$/i.test(file.name || "")
  );
}

export async function attachmentFromFile(file, options = {}) {
  const maxBytes = options.maxBytes || DEFAULT_MAX_FILE_BYTES;
  const maxTextChars = options.maxTextChars || DEFAULT_MAX_TEXT_CHARS;
  const makeId = options.makeId || defaultId;
  const mime = file.type || "application/octet-stream";
  const base = {
    id: makeId(),
    name: file.name || "attachment",
    mime,
    size: Number(file.size) || 0,
  };

  if (base.size > maxBytes) {
    return {
      ...base,
      kind: "file",
      error: `文件超过 ${Math.round(maxBytes / 1024 / 1024)}MB，未发送内容`,
    };
  }

  if (mime.startsWith("image/")) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    return {
      ...base,
      kind: "image",
      data_url: `data:${mime};base64,${bytesToBase64(bytes)}`,
    };
  }

  if (looksTextual(file)) {
    const raw = await file.text();
    return {
      ...base,
      kind: "text",
      text: raw.slice(0, maxTextChars),
      truncated: raw.length > maxTextChars,
    };
  }

  return {
    ...base,
    kind: "file",
  };
}

export function attachmentsForRequest(attachments) {
  return (Array.isArray(attachments) ? attachments : []).map((attachment) => {
    const row = {
      kind: attachment.kind,
      name: attachment.name,
      mime: attachment.mime,
      size: attachment.size,
    };
    if (attachment.kind === "image" && typeof attachment.data_url === "string") {
      row.data_url = attachment.data_url;
    }
    if (attachment.kind === "text" && typeof attachment.text === "string") {
      row.text = attachment.text;
      row.truncated = Boolean(attachment.truncated);
    }
    if (attachment.error) {
      row.error = attachment.error;
    }
    return Object.fromEntries(Object.entries(row).filter(([, value]) => value !== undefined));
  });
}

export async function attachmentsFromFiles(files, options = {}) {
  const rows = [];
  for (const file of Array.from(files || [])) {
    rows.push(await attachmentFromFile(file, options));
  }
  return rows;
}

export function filesFromPasteEvent(event) {
  const items = Array.from(event.clipboardData?.items || []);
  return items
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter(Boolean);
}

export function filesFromDropEvent(event) {
  return Array.from(event.dataTransfer?.files || []);
}

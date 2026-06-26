import assert from "node:assert/strict";
import test from "node:test";

import {
  attachmentFromFile,
  attachmentsForRequest,
} from "../../../custom_nodes/ComfyUI-AgentWorkbench/js/attachments.mjs";

function fileLike({ name, type, body }) {
  const bytes = Buffer.from(body);
  return {
    name,
    type,
    size: bytes.byteLength,
    async arrayBuffer() {
      return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    },
    async text() {
      return bytes.toString("utf8");
    },
  };
}

test("attachmentFromFile encodes images as data urls for Codex vision", async () => {
  const attachment = await attachmentFromFile(
    fileLike({ name: "shot.png", type: "image/png", body: "png-bytes" }),
    { makeId: () => "att-1" },
  );

  assert.equal(attachment.id, "att-1");
  assert.equal(attachment.kind, "image");
  assert.equal(attachment.name, "shot.png");
  assert.equal(attachment.mime, "image/png");
  assert.match(attachment.data_url, /^data:image\/png;base64,/);
});

test("attachmentFromFile reads text attachments with truncation", async () => {
  const attachment = await attachmentFromFile(
    fileLike({ name: "notes.txt", type: "text/plain", body: "abcdef" }),
    { makeId: () => "att-2", maxTextChars: 3 },
  );

  assert.deepEqual(attachment, {
    id: "att-2",
    kind: "text",
    name: "notes.txt",
    mime: "text/plain",
    size: 6,
    text: "abc",
    truncated: true,
  });
});

test("attachmentsForRequest keeps content for current turn", () => {
  const rows = attachmentsForRequest([
    {
      id: "att-1",
      kind: "image",
      name: "shot.png",
      mime: "image/png",
      size: 9,
      data_url: "data:image/png;base64,abc",
    },
    {
      id: "att-2",
      kind: "text",
      name: "notes.txt",
      mime: "text/plain",
      size: 5,
      text: "hello",
    },
  ]);

  assert.deepEqual(rows, [
    {
      kind: "image",
      name: "shot.png",
      mime: "image/png",
      size: 9,
      data_url: "data:image/png;base64,abc",
    },
    {
      kind: "text",
      name: "notes.txt",
      mime: "text/plain",
      size: 5,
      text: "hello",
      truncated: false,
    },
  ]);
});

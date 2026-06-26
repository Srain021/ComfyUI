# Agent Workbench Chat Shell Design

Date: 2026-06-26
Status: Design spec for user review. Implementation has not started.

## Purpose

Turn the current ComfyUI Agent Workbench sidebar from a single-response operator panel into a Codex/Claude-style chat workspace embedded inside ComfyUI. The workspace must keep conversation history, accept text and image attachments, let the Agent inspect the current workflow and attached media, and present ComfyUI actions as explicit tool-call cards that require user approval before mutation.

The first implementation is local-first: chat history is stored in the browser and survives refreshes on that browser. Server-side cross-device history belongs to Phase 4.

## Approved Decisions

- Use approach A: Local-First Chat Shell.
- Store first-version history in browser `localStorage`.
- Preserve the existing Codex OAuth bridge and `/agent/message` route.
- Let the Agent automatically read context, analyze the graph, and inspect attachments.
- Require explicit approval for any action that edits nodes, runs the queue, installs or disables custom nodes, writes compose config, restarts services, or changes runtime state.
- Support text and image uploads in the first version.
- Do not give the model raw shell access or automatic mutation authority.

## Current System Facts

- Repository: `/home/srain/ComfyUI`.
- Extension package: `/home/srain/ComfyUI/custom_nodes/ComfyUI-AgentWorkbench`.
- Sidebar frontend: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.js`.
- Sidebar styles: `custom_nodes/ComfyUI-AgentWorkbench/js/agent-workbench.css`.
- Response formatting: `custom_nodes/ComfyUI-AgentWorkbench/js/workbench-response.mjs`.
- Backend routes: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/routes.py`.
- LLM adapter: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/llm.py`.
- Codex OAuth bridge: `custom_nodes/ComfyUI-AgentWorkbench/agent_workbench/codex_bridge.py`.
- Live Codex bridge service: `comfyui-codex-bridge.service`, bound to `172.17.0.1:8797`.
- Live ComfyUI container: `comfyui-gb10`.
- Live compose file: `dgx_spark_ltx_setup/docker-compose.yml`.
- `/agent/health` currently reports `llm.configured = true`.

The current sidebar still has the old interaction shape: a textarea, Send/Apply controls, and one output section. `renderWorkbenchResponse()` replaces the output contents each time, so it cannot behave like a chat history.

## Non-Goals

- Do not implement server-side conversation storage in the first version.
- Do not build a separate external LibTV-style app.
- Do not let the Agent perform write/package/service/runtime actions without an approval UI.
- Do not implement a full autonomous multi-step loop that repeatedly executes tools without user checkpoints.
- Do not support arbitrary file uploads in the first version.
- Do not add a new model provider; reuse the existing OpenAI-compatible LLM adapter and Codex OAuth bridge.

## Product Shape

The sidebar becomes a chat workspace with three fixed regions:

1. Header
   - Title: `Agent Workbench`.
   - Controls: `新会话`, `清空`, `上下文`, `自检`.
   - The header stays compact because the sidebar is narrow.

2. Message timeline
   - Scrollable message list.
   - User messages are visually distinct from Agent messages.
   - Tool-call cards appear inline in the timeline.
   - Tool execution results append as new timeline entries instead of replacing prior content.
   - Details such as raw JSON live inside collapsed `<details>` blocks.

3. Composer
   - Attachment tray above the textarea.
   - Multi-line textarea.
   - Upload button and Send button.
   - `Ctrl+Enter` / `Cmd+Enter` sends.
   - Paste and drag/drop can add supported attachments.

The visual result should read as an operator chat, not a report card. The main difference from the current UI is continuity: the user can see what they asked, what the Agent replied, what tool was proposed, what was approved, and what happened after execution.

## Message Types

The frontend stores and renders these message records:

```json
{
  "id": "msg_...",
  "role": "user|assistant|tool|status",
  "created_at": "2026-06-26T06:00:00.000Z",
  "text": "Message body",
  "attachments": [],
  "response": {},
  "plan": {},
  "tool_state": "pending|approved|cancelled|running|done|failed"
}
```

Rules:

- `user` messages contain typed text and attachment metadata.
- `assistant` messages contain the Agent's natural-language reply.
- `tool` messages contain executable plan cards and execution results.
- `status` messages contain local UI events such as cancelled plans or failed requests.
- The message schema is versioned through the localStorage key name rather than per-row migration in the first version.

## Local History

Use a single localStorage key:

```text
comfyui.agentWorkbench.chat.v1
```

Stored shape:

```json
{
  "version": 1,
  "session_id": "local_...",
  "messages": []
}
```

Limits:

- Keep at most 100 messages in localStorage.
- Send at most the last 20 messages to the backend.
- Keep attachment payloads only while they are still useful for the active local session.
- If localStorage write fails, continue in memory and append a visible status message.

Controls:

- `新会话` creates a new local session and clears the visible timeline.
- `清空` clears the current local timeline after browser confirmation.

## Attachments

First version supported files:

- Images: `png`, `jpg`, `jpeg`, `webp`.
- Text: `txt`, `md`, `json`.

Limits:

- Maximum 4 attachments per user message.
- Maximum 4 images per user message.
- Maximum text attachment payload of 40,000 characters per file before truncation.
- Images are sent as data URLs or base64 payloads with metadata. The bridge writes them to temporary files before invoking Codex.

Acquisition methods:

- Upload button.
- Drag and drop into the composer.
- Paste image or text from clipboard.

UI behavior:

- Images render as small thumbnails in the attachment tray and user message.
- Text files render as chips with filename, type, size, and truncation flag.
- Each pending attachment has a remove button.
- Unsupported files create a status message explaining the allowed file types.

## Request Payload

The frontend sends this request to `/agent/message`:

```json
{
  "message": "User text",
  "mode": "chat",
  "history": [
    {"role": "user", "text": "..."},
    {"role": "assistant", "text": "..."}
  ],
  "attachments": [
    {
      "id": "att_...",
      "kind": "image|text",
      "name": "screenshot.png",
      "mime": "image/png",
      "size": 12345,
      "data_url": "data:image/png;base64,..."
    }
  ],
  "graph": {
    "nodes": [],
    "links": [],
    "node_types": []
  }
}
```

History sent to the backend contains recent user, assistant, and tool summaries. It does not need to include raw details for every previous tool execution.

## Backend Message Handling

`/agent/message` keeps the existing deterministic planner path but accepts richer chat input.

Flow:

1. Parse `message`, `history`, `attachments`, and graph input.
2. Collect bounded ComfyUI context as today.
3. Run the deterministic planner.
4. If the planner produces a non-context plan, return a `dry_run` response for the frontend to render as a tool-call card.
5. If the planner produces a context-only plan, call `build_assistant_reply()` with message, history, attachments, context, and dry-run details.
6. Return `assistant_reply`, `ai_error`, or `ai_unavailable`.

The backend never trusts frontend-provided approval flags for execution. Existing dry-run hash validation remains the authority for apply.

## LLM Payload

`build_openai_responses_payload()` expands from `message + context + dry_run` to:

```json
{
  "user_message": "...",
  "recent_history": [],
  "attachments": [],
  "current_comfyui_context": {},
  "deterministic_planner_result": {}
}
```

Attachment treatment:

- Text attachments include truncated text and metadata.
- Image attachments include metadata and a short `image_attached` marker in the JSON payload.
- The actual image bytes are forwarded separately by the Codex bridge, because `codex exec` expects image file paths.

Prompt policy:

- The Agent should answer naturally for normal chat.
- The Agent should explain current workflow state when useful.
- The Agent should not claim a mutation has happened before an apply result exists.
- The Agent should direct actionable changes into the plan-and-approval flow.

## Codex Bridge Image Path

The bridge accepts OpenAI-compatible request payloads and detects image attachments from `input`.

Flow:

1. Decode image attachments from data URLs.
2. Write each image to a temporary file with a safe extension.
3. Invoke:

```bash
codex exec --ignore-user-config --ignore-rules -C /tmp --skip-git-repo-check --sandbox read-only --model <model> --image <image-file> --output-last-message <output-file> -
```

4. Pass the assembled prompt over stdin.
5. Return an OpenAI Responses-compatible `output_text` payload.
6. Delete temporary files after the request.

The bridge remains read-only during model reasoning. It does not get write permissions or shell execution authority beyond the controlled `codex exec` invocation.

## Tool-Call Cards

A deterministic plan or future Agent-proposed action renders as a tool-call card in the timeline.

Card content:

- Title: short action summary.
- Risk badge: `read`, `canvas`, `runtime`, `file`, `package`, `service`, or `human_sudo`.
- A compact list of planned actions.
- Collapsed JSON details.
- Buttons:
  - `允许执行`
  - `取消`

Execution behavior:

- `read` and chat-only messages do not require a tool card.
- `canvas` plans may be approved directly from the card.
- `runtime`, `file`, `package`, `service`, and `human_sudo` plans show risk wording before the allow button.
- `human_sudo` plans are print-only and never execute sudo.
- After approval, the card state becomes `running`.
- The result appends as a `tool` message with success or failure details.
- A failed apply leaves the original card visible and appends a failure result.

## Frontend Modules

To avoid turning `agent-workbench.js` into an unbounded file, split new responsibilities:

- `js/chat-store.mjs`
  - localStorage load/save.
  - message creation.
  - history bounding.

- `js/attachments.mjs`
  - file validation.
  - drag/drop and paste helpers.
  - data URL and text extraction.
  - attachment display metadata.

- `js/chat-render.mjs`
  - message timeline rendering.
  - assistant/user/tool/status bubbles.
  - tool-call cards.

- `js/agent-workbench.js`
  - ComfyUI integration.
  - current graph snapshot.
  - route calls.
  - orchestration between store, render, attachments, and apply logic.

Existing modules continue to own their current responsibilities:

- `graph-actions.js`: browser graph action application.
- `frontend-requests.mjs`: Manager/frontend request execution.
- `workbench-state.mjs`: plan/apply state helpers.
- `workbench-response.mjs`: conversion from backend response to display-friendly summary.

## Styling

The sidebar remains dense and work-focused:

- No landing-page or marketing layout.
- No nested cards inside cards.
- Message bubbles use restrained borders and background differences.
- Tool cards are compact, with clear action buttons.
- The composer stays at the bottom and does not resize the timeline unpredictably.
- Text must wrap inside sidebar width.
- Attachment thumbnails have stable dimensions.

## Testing

Python tests:

- `/agent/message` accepts `history` and `attachments`.
- LLM payload includes recent history and text attachment summaries.
- Image attachments are represented in the payload without dumping raw bytes into prompt JSON.
- Codex bridge converts image data URLs into temporary image files and appends `--image` arguments.
- Non-context planner responses still return dry-run tool-call data.
- Existing confirmation rules still apply to high-risk actions.

Frontend tests:

- Chat store appends messages without replacing history.
- Chat store persists and restores localStorage state.
- Chat store bounds messages to 100 saved rows.
- History payload sent to backend contains only recent messages.
- Attachment validation accepts supported image/text types and rejects unsupported files.
- Attachment parsing truncates text files at the configured limit.
- Renderer shows user, assistant, tool, and status messages.
- Tool-call card state changes through pending, cancelled, running, done, and failed.
- Apply request still carries approved hash and confirmation state.

Browser smoke tests:

- Sidebar opens as the ComfyUI tab.
- Two chat messages remain visible.
- Refresh restores local history.
- Uploading or pasting an image creates an attachment chip.
- A chat message with an image reaches the backend.
- A command such as `把 KSampler 步数改成 30` creates a tool-call card.
- Approving the card applies the graph edit and appends a result message.

## Rollout Plan

Phase 1: Chat shell and local history.

- Add chat store.
- Render timeline.
- Keep current text-only `/agent/message`.
- Preserve existing planner/apply behavior through tool-call cards.

Phase 2: Attachments.

- Add upload, paste, drag/drop.
- Add text attachment context.
- Add image attachment forwarding through Codex bridge.

Phase 3: Tool-card polish.

- Replace the fixed global Apply button with per-plan approval cards.
- Keep a compatibility path until browser smoke covers the new flow.

Phase 4: Service-side history.

- Add server-side session storage only after the local-first UI is stable.
- Keep localStorage as a cache for faster reload and offline resilience.

## Risks and Mitigations

- Large images or long text can bloat prompts.
  - Mitigation: strict attachment count and text limits, image metadata in JSON, image files passed separately to Codex.

- `codex exec` is slower than direct API calls.
  - Mitigation: show a visible `Agent 正在思考` status message and keep the UI interactive.

- LocalStorage history is browser-local.
  - Mitigation: make this explicit in the first version and design the message schema so server history can reuse it.

- Tool-call UX can accidentally hide important risk.
  - Mitigation: keep risk badge, action summary, details, and explicit approval visible in the card.

- Current code has many pending changes and ignored custom-node files.
  - Mitigation: keep implementation edits scoped, force-add ignored files only when the user asks for staging/commit.

## Acceptance Criteria

- A user can send at least two chat messages and see both in the timeline.
- Refreshing the browser restores local chat history.
- The Agent receives recent history when answering.
- The user can attach a supported text file and the Agent can use its contents.
- The user can attach an image and the Codex OAuth bridge can pass it to `codex exec --image`.
- A graph edit request appears as an approval card instead of immediately applying.
- Approving a graph edit card applies the change and appends a result message.
- Cancelling a tool card appends a cancellation status and does not apply anything.
- Existing `/agent/health`, `/agent/context`, `/agent/plan`, `/agent/apply`, and browser smoke coverage remain healthy.

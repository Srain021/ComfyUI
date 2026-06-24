import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const WORKBENCH_STYLESHEET_ID = "agent-workbench-stylesheet";
const WORKBENCH_STYLESHEET_HREF = "/extensions/ComfyUI-AgentWorkbench/agent-workbench.css";

function loadWorkbenchStylesheet() {
  if (document.getElementById(WORKBENCH_STYLESHEET_ID)) {
    return;
  }

  const link = document.createElement("link");
  link.id = WORKBENCH_STYLESHEET_ID;
  link.rel = "stylesheet";
  link.href = WORKBENCH_STYLESHEET_HREF;
  document.head.appendChild(link);
}

function createWorkbenchPanel() {
  if (document.getElementById("agent-workbench-panel")) {
    return;
  }

  const panel = document.createElement("section");
  panel.id = "agent-workbench-panel";
  panel.innerHTML = `
    <header>
      <strong>Agent</strong>
      <button id="agent-workbench-refresh" title="Refresh context">Refresh</button>
    </header>
    <textarea id="agent-workbench-input" placeholder="Tell the Agent what to inspect or change"></textarea>
    <button id="agent-workbench-plan">Plan</button>
    <pre id="agent-workbench-output">Agent Workbench ready.</pre>
  `;
  document.body.appendChild(panel);

  const output = panel.querySelector("#agent-workbench-output");
  panel.querySelector("#agent-workbench-refresh").addEventListener("click", async () => {
    const response = await api.fetchApi("/agent/health");
    output.textContent = JSON.stringify(await response.json(), null, 2);
  });
}

app.registerExtension({
  name: "ComfyUI.AgentWorkbench",
  setup() {
    loadWorkbenchStylesheet();
    createWorkbenchPanel();
  },
});

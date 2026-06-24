import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

import "./agent-workbench.css";

function createWorkbenchPanel() {
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
    createWorkbenchPanel();
  },
});

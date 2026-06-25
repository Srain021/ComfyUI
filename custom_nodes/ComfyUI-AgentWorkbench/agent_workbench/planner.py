import os
import re


class RuleBasedPlanner:
    def plan(self, message: str, context: dict) -> dict:
        text = message.strip() if isinstance(message, str) else ""
        lowered = text.lower()
        if "reserve-vram" in lowered or "reserve vram" in lowered:
            match = re.search(r"(\d+)", text)
            value = match.group(1) if match else "8"
            return {
                "summary": f"Set compose reserve-vram to {value}",
                "actions": [{"type": "compose.set_reserve_vram", "payload": {"value": value}}],
            }
        if "free" in lowered or "释放" in text or "腾内存" in text or "内存" in text:
            return {
                "summary": "Free ComfyUI memory",
                "actions": [
                    {
                        "type": "runtime.free_memory",
                        "payload": {"unload_models": True, "free_memory": True},
                    }
                ],
            }
        return {
            "summary": f"Inspect context for: {text}",
            "actions": [{"type": "context.collect", "payload": {"message": text}}],
        }


def default_planner() -> RuleBasedPlanner:
    provider = os.environ.get("AGENT_WORKBENCH_PROVIDER", "rules")
    if provider != "rules":
        return RuleBasedPlanner()
    return RuleBasedPlanner()

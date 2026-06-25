from pathlib import Path

import yaml

from ..snapshots import snapshot_file


DEFAULT_COMPOSE_PATH = Path("dgx_spark_ltx_setup/docker-compose.yml")


def validate_compose_text(text: str) -> dict:
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "services" not in data:
        raise ValueError("compose file must contain services")
    if not isinstance(data["services"], dict) or "comfyui-gb10" not in data["services"]:
        raise ValueError("compose file must define comfyui-gb10")
    return data


def _normalize_reserve_vram_value(value: str) -> str:
    normalized = str(value).strip()
    if not normalized.isdigit():
        raise ValueError("reserve-vram value must be a non-negative integer")
    return normalized


def patch_reserve_vram(text: str, value: str) -> str:
    validate_compose_text(text)
    value = _normalize_reserve_vram_value(value)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "- --reserve-vram":
            value_index = index + 1
            if value_index >= len(lines):
                raise ValueError("reserve-vram value line is missing")
            old_line = lines[value_index]
            prefix = old_line.split("-", 1)[0] + "- "
            suffix = ""
            if "#" in old_line:
                suffix = "  #" + old_line.split("#", 1)[1]
            lines[value_index] = f"{prefix}\"{value}\"{suffix}"
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    raise ValueError("reserve-vram flag not found")


def plan_reserve_vram(compose_path: Path, value: str) -> dict:
    value = _normalize_reserve_vram_value(value)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_reserve_vram(original, value)
    return {
        "path": str(compose_path),
        "changed": original != patched,
        "before": original,
        "after": patched,
    }


def apply_reserve_vram(compose_path: Path, value: str, backup_dir: Path) -> dict:
    value = _normalize_reserve_vram_value(value)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_reserve_vram(original, value)
    snapshot = snapshot_file(compose_path, backup_dir, reason="compose-reserve-vram")
    compose_path.write_text(patched, encoding="utf-8")
    return {"path": str(compose_path), "snapshot": str(snapshot), "value": value}

from pathlib import Path

import yaml

from ..snapshots import snapshot_file


DEFAULT_COMPOSE_PATH = Path("dgx_spark_ltx_setup/docker-compose.yml")
REQUIRED_COMMAND_FLAGS = {
    "--disable-cuda-malloc",
    "--disable-pinned-memory",
    "--use-pytorch-cross-attention",
    "--reserve-vram",
}


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


def _normalize_command_flag(flag: str) -> str:
    normalized = str(flag).strip()
    if not normalized.startswith("--"):
        raise ValueError("command flag must start with --")
    if not normalized[2:] or not all(char.isalnum() or char == "-" for char in normalized[2:]):
        raise ValueError("command flag must contain only letters, numbers, and dashes")
    return normalized


def _normalize_command_value(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("command value must not be empty")
    if "\n" in normalized or "\r" in normalized:
        raise ValueError("command value must be single-line")
    return normalized


def _quote_command_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _command_block_lines(lines: list[str]) -> tuple[int, int, str]:
    command_index = None
    service_indent = None
    for index, line in enumerate(lines):
        if line.strip() == "comfyui-gb10:":
            service_indent = len(line) - len(line.lstrip())
            continue
        if service_indent is None:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= service_indent:
            break
        if stripped == "command:":
            command_index = index
            break
    if command_index is None:
        raise ValueError("comfyui-gb10 command block not found")

    command_indent = len(lines[command_index]) - len(lines[command_index].lstrip())
    entry_indices = []
    end_index = len(lines)
    for index in range(command_index + 1, len(lines)):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= command_indent:
            end_index = index
            break
        if stripped.startswith("- "):
            entry_indices.append(index)
    if not entry_indices:
        raise ValueError("compose command list is empty")
    entry_prefix = lines[entry_indices[0]].split("-", 1)[0]
    return entry_indices[0], end_index, entry_prefix


def _command_entry_value(line: str) -> str:
    value = line.strip()[2:].strip()
    if "#" in value:
        value = value.split("#", 1)[0].strip()
    return value.strip("'\"")


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


def patch_command_flag(text: str, flag: str, enabled: bool) -> str:
    validate_compose_text(text)
    flag = _normalize_command_flag(flag)
    if not enabled and flag in REQUIRED_COMMAND_FLAGS:
        raise ValueError(f"cannot remove required GB10 flag: {flag}")
    lines = text.splitlines()
    start_index, end_index, entry_prefix = _command_block_lines(lines)
    existing_index = None
    for index in range(start_index, end_index):
        if lines[index].strip().startswith("- ") and _command_entry_value(lines[index]) == flag:
            existing_index = index
            break

    if enabled:
        if existing_index is None:
            lines.insert(end_index, f"{entry_prefix}- {flag}")
    elif existing_index is not None:
        del lines[existing_index]

    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def patch_command_value(text: str, flag: str, value: str) -> str:
    validate_compose_text(text)
    flag = _normalize_command_flag(flag)
    value = _normalize_command_value(value)
    lines = text.splitlines()
    start_index, end_index, _ = _command_block_lines(lines)
    flag_index = None
    for index in range(start_index, end_index):
        if lines[index].strip().startswith("- ") and _command_entry_value(lines[index]) == flag:
            flag_index = index
            break
    if flag_index is None:
        raise ValueError("flag value line is missing")

    value_index = flag_index + 1
    if value_index >= end_index or not lines[value_index].strip().startswith("- "):
        raise ValueError("flag value line is missing")
    if _command_entry_value(lines[value_index]).startswith("--"):
        raise ValueError("flag value line is missing")

    old_line = lines[value_index]
    prefix = old_line.split("-", 1)[0] + "- "
    suffix = ""
    if "#" in old_line:
        suffix = "  #" + old_line.split("#", 1)[1]
    lines[value_index] = f"{prefix}{_quote_command_value(value)}{suffix}"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


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


def plan_command_flag(compose_path: Path, flag: str, enabled: bool) -> dict:
    flag = _normalize_command_flag(flag)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_command_flag(original, flag, enabled)
    return {
        "path": str(compose_path),
        "changed": original != patched,
        "before": original,
        "after": patched,
        "flag": flag,
        "enabled": bool(enabled),
    }


def plan_command_value(compose_path: Path, flag: str, value: str) -> dict:
    flag = _normalize_command_flag(flag)
    value = _normalize_command_value(value)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_command_value(original, flag, value)
    return {
        "path": str(compose_path),
        "changed": original != patched,
        "before": original,
        "after": patched,
        "flag": flag,
        "value": value,
    }


def apply_reserve_vram(compose_path: Path, value: str, backup_dir: Path) -> dict:
    value = _normalize_reserve_vram_value(value)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_reserve_vram(original, value)
    snapshot = snapshot_file(compose_path, backup_dir, reason="compose-reserve-vram")
    compose_path.write_text(patched, encoding="utf-8")
    return {"path": str(compose_path), "snapshot": str(snapshot), "value": value}


def apply_command_flag(compose_path: Path, flag: str, enabled: bool, backup_dir: Path) -> dict:
    flag = _normalize_command_flag(flag)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_command_flag(original, flag, enabled)
    snapshot = snapshot_file(compose_path, backup_dir, reason="compose-command-flag")
    compose_path.write_text(patched, encoding="utf-8")
    return {
        "path": str(compose_path),
        "snapshot": str(snapshot),
        "flag": flag,
        "enabled": bool(enabled),
        "changed": original != patched,
    }


def apply_command_value(compose_path: Path, flag: str, value: str, backup_dir: Path) -> dict:
    flag = _normalize_command_flag(flag)
    value = _normalize_command_value(value)
    original = compose_path.read_text(encoding="utf-8")
    patched = patch_command_value(original, flag, value)
    snapshot = snapshot_file(compose_path, backup_dir, reason="compose-command-value")
    compose_path.write_text(patched, encoding="utf-8")
    return {
        "path": str(compose_path),
        "snapshot": str(snapshot),
        "flag": flag,
        "value": value,
        "changed": original != patched,
    }

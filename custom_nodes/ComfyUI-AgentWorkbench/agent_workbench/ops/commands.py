import subprocess


class CommandRejected(ValueError):
    pass


ALLOWED_BINARIES = {"docker", "ollama", "free", "curl"}
DENIED_BINARIES = {"sudo", "bash", "sh", "python", "python3"}
SHELL_TOKENS = {";", "&&", "||", "|", ">", "<", "$(", "`"}
LOCAL_COMFY_URLS = ("http://127.0.0.1:8188/", "http://localhost:8188/")


def _reject_shell_syntax(args: list[str]) -> None:
    joined = " ".join(args)
    if any(token in joined for token in SHELL_TOKENS):
        raise CommandRejected("shell syntax is not allowed")


def _validate_docker(args: list[str]) -> None:
    if len(args) >= 2 and args[1] == "ps":
        return
    if args == ["docker", "restart", "comfyui-gb10"]:
        return
    compose_prefix = ["docker", "compose", "-f", "dgx_spark_ltx_setup/docker-compose.yml"]
    if args[:4] == compose_prefix and args[4:] in (
        ["restart", "comfyui-gb10"],
        ["up", "-d"],
    ):
        return
    raise CommandRejected("unsupported docker command")


def _validate_ollama(args: list[str]) -> None:
    if args == ["ollama", "ps"]:
        return
    if len(args) == 3 and args[1] == "stop" and args[2]:
        return
    raise CommandRejected("unsupported ollama command")


def _validate_curl(args: list[str]) -> None:
    allowed_flags = {"-sS", "--fail", "-f", "-X", "POST"}
    urls = [arg for arg in args[1:] if arg.startswith(("http://", "https://"))]
    if len(urls) != 1 or not urls[0].startswith(LOCAL_COMFY_URLS):
        raise CommandRejected("curl is limited to local ComfyUI URLs")
    for arg in args[1:]:
        if arg == urls[0] or arg in allowed_flags:
            continue
        raise CommandRejected(f"unsupported curl argument: {arg}")


def validate_command(args: list[str]) -> list[str]:
    if not isinstance(args, list) or not args:
        raise CommandRejected("empty command")
    if not all(isinstance(arg, str) and arg for arg in args):
        raise CommandRejected("command arguments must be non-empty strings")
    binary = args[0]
    if binary in DENIED_BINARIES:
        raise CommandRejected(f"denied binary: {binary}")
    if binary not in ALLOWED_BINARIES:
        raise CommandRejected(f"unsupported binary: {binary}")
    _reject_shell_syntax(args)
    if binary == "docker":
        _validate_docker(args)
    elif binary == "ollama":
        _validate_ollama(args)
    elif binary == "free" and args != ["free", "-h"]:
        raise CommandRejected("unsupported free command")
    elif binary == "curl":
        _validate_curl(args)
    return list(args)


def run_command(args: list[str], timeout_seconds: int = 60) -> dict:
    safe_args = validate_command(args)
    try:
        completed = subprocess.run(
            safe_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "args": safe_args,
            "returncode": None,
            "timed_out": True,
            "stdout": (exc.stdout or "")[-8000:],
            "stderr": (exc.stderr or "")[-8000:],
        }
    return {
        "args": safe_args,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }

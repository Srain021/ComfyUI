def build_free_memory_request() -> dict:
    return {"unload_models": True, "free_memory": True}


def stop_ollama_model_command(model_name: str) -> list[str]:
    return ["ollama", "stop", model_name]


def docker_restart_command(container_name: str = "comfyui-gb10") -> list[str]:
    return ["docker", "restart", container_name]


def free_memory_command() -> list[str]:
    return ["free", "-h"]

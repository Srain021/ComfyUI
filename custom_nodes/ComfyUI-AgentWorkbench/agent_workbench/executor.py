from .ops.commands import run_command


class RecordingExecutor:
    def __init__(self):
        self.commands = []
        self.manager_requests = []

    def run_command(self, args: list[str]) -> dict:
        self.commands.append(args)
        return {"args": args, "returncode": 0, "stdout": "", "stderr": ""}

    def manager_request(self, request: dict) -> dict:
        self.manager_requests.append(request)
        return {"status": "frontend_required", "request": request}


class DefaultExecutor:
    def run_command(self, args: list[str]) -> dict:
        return run_command(args)

    def manager_request(self, request: dict) -> dict:
        return {"status": "frontend_required", "request": request}

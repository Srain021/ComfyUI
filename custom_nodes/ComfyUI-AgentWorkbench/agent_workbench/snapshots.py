import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def snapshot_file(target: Path, backup_dir: Path, reason: str) -> Path:
    if not target.is_file():
        if target.exists():
            raise IsADirectoryError(str(target))
        raise FileNotFoundError(str(target))
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_reason = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in reason)
    snapshot = backup_dir / f"{target.name}.{safe_reason}.{stamp}.{uuid4().hex[:8]}.bak"
    shutil.copy2(target, snapshot)
    return snapshot


def restore_snapshot(snapshot: Path, target: Path) -> None:
    if not snapshot.exists():
        raise FileNotFoundError(str(snapshot))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot, target)

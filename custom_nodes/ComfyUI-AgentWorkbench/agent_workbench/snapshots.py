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

    while True:
        snapshot = backup_dir / f"{target.name}.{safe_reason}.{stamp}.{uuid4().hex[:8]}.bak"
        try:
            with target.open("rb") as source, snapshot.open("xb") as handle:
                shutil.copyfileobj(source, handle)
            shutil.copystat(target, snapshot)
            return snapshot
        except FileExistsError:
            continue


def restore_snapshot(snapshot: Path, target: Path) -> None:
    if not snapshot.is_file():
        if snapshot.exists():
            raise IsADirectoryError(str(snapshot))
        raise FileNotFoundError(str(snapshot))
    if target.is_dir():
        raise IsADirectoryError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot, target)

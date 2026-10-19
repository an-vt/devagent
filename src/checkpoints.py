"""Session-scoped undo checkpoints for file mutations."""

import base64
import json
from pathlib import Path

CHECKPOINTS_FILE = Path.home() / ".corecoder" / "checkpoints.json"
_stack: list[tuple[str, bytes | None]] = []
_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        entries = json.loads(CHECKPOINTS_FILE.read_text(encoding="utf-8"))
        for entry in entries:
            prior = entry["prior"]
            _stack.append((entry["path"], base64.b64decode(prior) if prior is not None else None))
    except (OSError, ValueError, KeyError, TypeError):
        pass


def _save() -> None:
    entries = [
        {"path": path, "prior": base64.b64encode(prior).decode("ascii") if prior is not None else None}
        for path, prior in _stack
    ]
    try:
        CHECKPOINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINTS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries), encoding="utf-8")
        tmp.replace(CHECKPOINTS_FILE)
    except OSError:
        pass


def record(path: Path) -> None:
    """Capture a file's state immediately before a write."""
    _ensure_loaded()
    _stack.append((str(path), path.read_bytes() if path.exists() else None))
    _save()


def undo() -> str:
    """Restore the most recent checkpoint."""
    _ensure_loaded()
    if not _stack:
        return "Nothing to undo."

    path_str, prior = _stack.pop()
    path = Path(path_str)
    if prior is None:
        path.unlink(missing_ok=True)
        message = f"Removed {path_str} (created this session)."
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(prior)
        message = f"Restored {path_str}."
    _save()
    return message


def pending() -> int:
    """Return the number of stored checkpoints."""
    _ensure_loaded()
    return len(_stack)


def clear() -> None:
    """Drop all checkpoints."""
    global _loaded
    _stack.clear()
    _loaded = True
    try:
        CHECKPOINTS_FILE.unlink(missing_ok=True)
    except OSError:
        pass

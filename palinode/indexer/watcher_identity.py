"""Runtime-only, store-scoped watcher identity persistence.

The identity record below ``.palinode/`` lets diagnostics associate a watcher
with its configured store. It is process state, never memory content: the
directory is excluded from indexing and Git commits.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile

from palinode.core.config import config

logger = logging.getLogger("palinode.watcher")

_WATCHER_IDENTITY_RELATIVE_PATH = ".palinode/watcher.json"


def _watcher_identity_path() -> str:
    return os.path.join(config.palinode_dir, _WATCHER_IDENTITY_RELATIVE_PATH)


def _watcher_identity_path_is_safe(path: str) -> bool:
    parent = os.path.dirname(path)
    return not os.path.islink(parent) and not os.path.islink(path)


def _process_start_token(pid: int) -> str | None:
    """Return a stable process-start token, or ``None`` when unavailable."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    token = result.stdout.strip()
    return token or None


def write_identity() -> tuple[int, str] | None:
    """Publish this watcher instance without following identity-path symlinks."""
    start_token = _process_start_token(os.getpid())
    if start_token is None:
        logger.warning("Watcher identity unavailable: could not read process start time")
        return None
    path = _watcher_identity_path()
    payload = {
        "pid": os.getpid(),
        "process_start": start_token,
        "memory_dir": os.path.realpath(config.palinode_dir),
    }
    temp_path: str | None = None
    temp_stat: os.stat_result | None = None
    try:
        parent = os.path.dirname(path)
        if not _watcher_identity_path_is_safe(path):
            raise OSError("watcher identity path must not be a symlink")
        os.makedirs(parent, exist_ok=True)
        if not _watcher_identity_path_is_safe(path):
            raise OSError("watcher identity path must not be a symlink")
        fd, temp_path = tempfile.mkstemp(
            prefix="watcher-", suffix=".tmp", dir=parent, text=True
        )
        temp_stat = os.fstat(fd)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        if not _watcher_identity_path_is_safe(path):
            raise OSError("watcher identity path became a symlink")
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        logger.warning("Could not write watcher identity %s: %s", path, exc)
        return None
    finally:
        if temp_path is not None and temp_stat is not None:
            try:
                current = os.lstat(temp_path)
                if (
                    current.st_dev == temp_stat.st_dev
                    and current.st_ino == temp_stat.st_ino
                    and not os.path.islink(temp_path)
                ):
                    os.unlink(temp_path)
            except OSError:
                pass
    return payload["pid"], payload["process_start"]


def remove_identity(identity: tuple[int, str] | None) -> None:
    """Remove only the safe identity record belonging to this watcher instance."""
    if identity is None:
        return
    path = _watcher_identity_path()
    if not _watcher_identity_path_is_safe(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            current = json.load(handle)
        if (
            isinstance(current, dict)
            and _watcher_identity_path_is_safe(path)
            and current.get("pid") == identity[0]
            and current.get("process_start") == identity[1]
        ):
            os.unlink(path)
    except (AttributeError, OSError, ValueError, TypeError):
        pass

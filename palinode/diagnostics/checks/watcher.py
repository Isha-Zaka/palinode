"""
Checks: watcher_alive, watcher_indexes_correct_db

Verify the palinode-watcher process is running and is bound to the correct
PALINODE_DIR / db_path.

Platform notes
--------------
On Linux:
  - watcher_alive: validates the configured store's runtime identity first,
    then probes ``systemctl is-active`` on the system and ``--user`` managers
    for shipped unit names. The unit-name and manager probing lives in
    ``palinode.core.systemd_units`` so that ``palinode stop`` cannot disagree
    with this check about which unit the host runs.
  - watcher_indexes_correct_db: reads ``/proc/<pid>/environ`` for the watcher
    PID to compare its PALINODE_DIR against the configured value. This catches
    the case where the watcher is restarted after a directory rename but still
    has the old PALINODE_DIR in its environment.

On macOS:
  - watcher_alive: validates the configured store's runtime identity. No
    global ``ps`` process-name scan is accepted, because it cannot establish
    that the watcher belongs to this store and foreground children are spawn_main.
  - watcher_indexes_correct_db: /proc is not available on macOS, so this check
    returns severity=info with a "not supported on macOS" message.  Process
    env can be approximated via ``ps -Eww -p <pid>`` but that is not portable
    across macOS versions and requires SIP permissions. Proper support is
    planned when a launchd unit ships.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from palinode.core.systemd_units import (
    MANAGERS,
    active_unit,
    watcher_unit_candidates,
)
from palinode.diagnostics.registry import register
from palinode.diagnostics.types import CheckResult, DoctorContext

_WATCHER_MODULE = "palinode.indexer.watcher"
_WATCHER_IDENTITY_RELATIVE_PATH = ".palinode/watcher.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _watcher_identity_path(ctx: DoctorContext) -> Path:
    return Path(ctx.config.memory_dir).expanduser().resolve() / _WATCHER_IDENTITY_RELATIVE_PATH


def _watcher_identity_path_is_safe(ctx: DoctorContext) -> bool:
    """Return whether the configured store's identity path is not symlinked."""
    identity_path = _watcher_identity_path(ctx)
    return not identity_path.parent.is_symlink() and not identity_path.is_symlink()


def _find_watcher_identity_pid(ctx: DoctorContext) -> int | None:
    """Return the live PID recorded by a watcher for *ctx*'s exact store.

    ``palinode start`` uses a multiprocessing child, whose command line is a
    generic ``spawn_main`` invocation rather than the watcher module. The
    watcher therefore publishes an internal, store-scoped identity record.
    Validate the path, PID, and OS process start token before trusting it: a
    leftover file, PID reuse, or a record for another store is not health.
    """
    identity_path = _watcher_identity_path(ctx)
    if not _watcher_identity_path_is_safe(ctx):
        return None
    try:
        with identity_path.open(encoding="utf-8") as handle:
            identity = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(identity, dict):
        return None
    pid = identity.get("pid")
    start_token = identity.get("process_start")
    recorded_store = identity.get("memory_dir")
    configured_store = str(Path(ctx.config.memory_dir).expanduser().resolve())
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(start_token, str)
        or not start_token
        or not isinstance(recorded_store, str)
        or os.path.realpath(recorded_store) != configured_store
    ):
        return None
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
    if result.returncode != 0 or result.stdout.strip() != start_token:
        return None
    return pid


def _find_watcher_pid(ctx: DoctorContext | None = None) -> int | None:
    """Return the PID of the running watcher process, or None if not found.

    With *ctx*, only a store-scoped runtime identity is accepted. This
    recognizes the multiprocessing child used by ``palinode start`` and avoids
    accepting a watcher that belongs to another store. The legacy module scan
    is retained only for callers without a configured-store context.
    """
    if ctx is not None:
        return _find_watcher_identity_pid(ctx)
    try:
        result = subprocess.run(
            ["ps", "-ef"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    for line in result.stdout.splitlines():
        if _WATCHER_MODULE in line:
            # ps -ef columns: UID, PID, PPID, ...
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    continue
    return None


def _read_proc_environ(pid: int) -> dict[str, str]:
    """Parse /proc/<pid>/environ into a dict (Linux only).

    Returns an empty dict if the file is unreadable (permission denied,
    process gone, or non-Linux platform). Monkeypatching the path prefix in
    tests is handled by wrapping this call with a custom proc root — see
    process_env._proc_root() for the pattern. On macOS this always returns {}.
    """
    environ_path = Path(f"/proc/{pid}/environ")
    try:
        raw = environ_path.read_bytes()
    except (OSError, PermissionError):
        return {}
    env: dict[str, str] = {}
    for entry in raw.split(b"\x00"):
        if b"=" in entry:
            key, _, val = entry.partition(b"=")
            env[key.decode(errors="replace")] = val.decode(errors="replace")
    return env


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@register(tags=("deep",))
def watcher_alive(ctx: DoctorContext) -> CheckResult:
    """Verify the palinode-watcher process is currently running.

    On every platform, a current watcher runtime identity is the only
    process-level liveness proof accepted for the configured store. Linux also
    accepts an active shipped systemd unit as a lifecycle signal when no
    identity has been published yet. macOS has no launchd unit and does not
    use a global process-name scan, because that cannot prove store association.
    """
    identity_path = _watcher_identity_path(ctx)
    identity_pid = _find_watcher_identity_pid(ctx)
    if identity_pid is not None:
        return CheckResult(
            name="watcher_alive",
            severity="error",
            passed=True,
            message=f"Watcher process found for configured store (PID {identity_pid}).",
            remediation=None,
        )
    if identity_path.exists() or identity_path.is_symlink() or identity_path.parent.is_symlink():
        return CheckResult(
            name="watcher_alive",
            severity="error",
            passed=False,
            message=(
                f"Watcher identity at {identity_path} is stale, malformed, or belongs "
                "to a different store; no watcher was accepted."
            ),
            remediation=(
                "Stop the stale process if it is still running, then restart the watcher "
                "with the configured PALINODE_DIR."
            ),
        )

    is_linux = sys.platform.startswith("linux")

    # Linux: try systemctl first — system manager, then --user
    if is_linux:
        units = watcher_unit_candidates()
        for manager, user in MANAGERS:
            active = active_unit(units, user=user)
            if active is not None:
                return CheckResult(
                    name="watcher_alive",
                    severity="error",
                    passed=True,
                    message=f"systemctl reports {manager} unit {active} is active",
                    remediation=None,
                )
        # No unit is active. A process-name scan cannot establish that an old
        # standalone process belongs to this configured store, so do not accept it.
        unit_list = ", ".join(units)
        return CheckResult(
            name="watcher_alive",
            severity="error",
            passed=False,
            message=(
                f"Watcher is not running: no unit ({unit_list}) is active under "
                f"the system or user manager and no store-scoped watcher identity found."
            ),
            remediation=(
                "Start the watcher: 'systemctl --user start palinode-watcher' "
                "or run 'palinode-watcher' in the foreground to see errors. "
                "To install the unit: 'palinode deploy-systemd'."
            ),
        )

    # macOS / other: a global ps substring cannot associate a process with this
    # store, and foreground multiprocessing children do not carry a module name.
    return CheckResult(
        name="watcher_alive",
        severity="error",
        passed=False,
        message=(
            "No store-scoped watcher identity found. "
                "(macOS: a global ps scan cannot prove the watcher uses this store.)"
        ),
        remediation=(
            "Run 'palinode start' or 'palinode-watcher' with the configured "
            "PALINODE_DIR to start the watcher. "
            "On macOS, consider adding it to your login items or a launchd plist."
        ),
    )


@register(tags=("deep",))
def watcher_indexes_correct_db(ctx: DoctorContext) -> CheckResult:
    """Verify the running watcher's PALINODE_DIR matches the configured value.

    On Linux: reads ``/proc/<pid>/environ`` for the watcher PID to extract its
    PALINODE_DIR, then compares (after realpath resolution) against
    ``config.memory_dir``. This catches the case where the watcher was
    restarted after a rename but retained the old PALINODE_DIR in its environment,
    silently writing new embeddings to the stale database.

    On macOS: /proc is unavailable.  This check returns severity=info with a
    "not supported on macOS" skip message.  Proper support requires reading the
    process environment via ``sysctl KERN_PROCARGS2`` or a privileged helper,
    which is not yet implemented.
    """
    is_linux = sys.platform.startswith("linux")

    # macOS / other platforms: skip with info
    if not is_linux:
        return CheckResult(
            name="watcher_indexes_correct_db",
            severity="info",
            passed=True,
            message=(
                "watcher_indexes_correct_db is not supported on macOS "
                "(requires /proc/<pid>/environ)."
            ),
            remediation=None,
        )

    # A current identity proves both liveness and store association. For a
    # legacy Linux service without one, inspect its module process only so the
    # /proc environment comparison below can reject a wrong-store watcher.
    # Never override a known stale/malformed identity record with that global
    # fallback.
    pid = _find_watcher_pid(ctx)
    identity_path = _watcher_identity_path(ctx)
    if (
        pid is None
        and _watcher_identity_path_is_safe(ctx)
        and not identity_path.exists()
    ):
        pid = _find_watcher_pid()
    if pid is None:
        return CheckResult(
            name="watcher_indexes_correct_db",
            severity="warn",
            passed=False,
            message=(
                "Cannot verify watcher DB: no watcher process found. "
                "Run watcher_alive first."
            ),
            remediation=(
                "Start the watcher: 'systemctl --user start palinode-watcher'."
            ),
        )

    # Read /proc/<pid>/environ
    proc_env = _read_proc_environ(pid)
    if not proc_env:
        return CheckResult(
            name="watcher_indexes_correct_db",
            severity="warn",
            passed=False,
            message=(
                f"Cannot read /proc/{pid}/environ "
                f"(permission denied or process exited). "
                f"Run as the same user as the watcher to inspect its env."
            ),
            remediation=(
                "Run 'palinode doctor' as the user that owns the watcher process, "
                "or inspect manually: "
                f"'cat /proc/{pid}/environ | tr \"\\0\" \"\\n\" | grep PALINODE_DIR'."
            ),
        )

    watcher_palinode_dir = proc_env.get("PALINODE_DIR", "")
    configured_dir = str(Path(ctx.config.memory_dir).expanduser().resolve())

    if not watcher_palinode_dir:
        return CheckResult(
            name="watcher_indexes_correct_db",
            severity="warn",
            passed=False,
            message=(
                f"Watcher PID {pid} has no PALINODE_DIR in its environment. "
                f"It will fall back to the default (~/palinode), "
                f"which may not match configured memory_dir={configured_dir}."
            ),
            remediation=(
                "Restart the watcher after setting PALINODE_DIR: "
                "'systemctl --user restart palinode-watcher'. "
                "Verify the unit's Environment= block: "
                "'systemctl --user cat palinode-watcher'."
            ),
        )

    watcher_resolved = str(Path(watcher_palinode_dir).expanduser().resolve())

    if watcher_resolved != configured_dir:
        return CheckResult(
            name="watcher_indexes_correct_db",
            severity="error",
            passed=False,
            message=(
                f"Watcher PID {pid} has PALINODE_DIR={watcher_palinode_dir!r} "
                f"(resolved: {watcher_resolved}) "
                f"but configured memory_dir is {configured_dir}. "
                f"The watcher is indexing the wrong directory."
            ),
            remediation=(
                f"Restart the watcher with the correct env: "
                f"'systemctl --user restart palinode-watcher'. "
                f"Verify the unit's Environment= block includes "
                f"PALINODE_DIR={configured_dir}: "
                f"'systemctl --user show palinode-watcher | grep PALINODE_DIR'. "
                f"If the unit is stale, re-deploy it: 'palinode deploy-systemd'. "
                f"Review the related diagnostics above."
            ),
        )

    return CheckResult(
        name="watcher_indexes_correct_db",
        severity="error",
        passed=True,
        message=(
            f"Watcher PID {pid} PALINODE_DIR={watcher_palinode_dir!r} "
            f"matches configured memory_dir."
        ),
        remediation=None,
    )

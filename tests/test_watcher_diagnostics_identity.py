"""Regression coverage for store-scoped watcher lifecycle diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from palinode.core.config import Config
from palinode.diagnostics.checks import watcher as diagnostics_watcher
from palinode.diagnostics.types import DoctorContext
from palinode.indexer import watcher_identity


def _ctx(memory_dir: Path) -> DoctorContext:
    return DoctorContext(
        config=Config(
            memory_dir=str(memory_dir), db_path=str(memory_dir / ".palinode.db")
        )
    )


def _identity(memory_dir: Path, *, pid: int = 4815, start: str = "Mon Sep 15 18:30:00 2026") -> None:
    path = memory_dir / ".palinode" / "watcher.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {"pid": pid, "process_start": start, "memory_dir": str(memory_dir.resolve())}
        ),
        encoding="utf-8",
    )


def _ps_start(start: str) -> mock.Mock:
    return mock.Mock(returncode=0, stdout=f"  {start}\n", stderr="")


def test_macos_accepts_foreground_spawn_watcher_for_its_store(
    tmp_path: Path, monkeypatch
) -> None:
    """``palinode start`` children are spawn_main, not module-named processes."""
    memory_dir = tmp_path / "store"
    memory_dir.mkdir()
    start = "Mon Sep 15 18:30:00 2026"
    _identity(memory_dir, start=start)
    monkeypatch.setattr(diagnostics_watcher.sys, "platform", "darwin")

    with mock.patch("subprocess.run", return_value=_ps_start(start)) as run:
        result = diagnostics_watcher.watcher_alive(_ctx(memory_dir))

    assert result.passed is True
    assert "PID 4815" in result.message
    assert run.call_args.args[0] == ["ps", "-p", "4815", "-o", "lstart="]


def test_stale_identity_does_not_accept_reused_pid(tmp_path: Path, monkeypatch) -> None:
    memory_dir = tmp_path / "store"
    memory_dir.mkdir()
    _identity(memory_dir, start="Mon Sep 15 18:30:00 2026")
    monkeypatch.setattr(diagnostics_watcher.sys, "platform", "darwin")

    with mock.patch("subprocess.run", return_value=_ps_start("Mon Sep 15 19:00:00 2026")):
        result = diagnostics_watcher.watcher_alive(_ctx(memory_dir))

    assert result.passed is False


def test_wrong_store_identity_does_not_fall_back_to_unrelated_module_process(
    tmp_path: Path, monkeypatch
) -> None:
    memory_dir = tmp_path / "store"
    other_store = tmp_path / "other-store"
    memory_dir.mkdir()
    other_store.mkdir()
    _identity(memory_dir)
    identity_path = memory_dir / ".palinode" / "watcher.json"
    payload = json.loads(identity_path.read_text(encoding="utf-8"))
    payload["memory_dir"] = str(other_store)
    identity_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(diagnostics_watcher.sys, "platform", "darwin")

    module_process = (
        "UID PID PPID C STIME TTY TIME CMD\n"
        "alice 4815 1 0 10:00 ? 00:00:01 python -m palinode.indexer.watcher\n"
    )
    with mock.patch("subprocess.run", return_value=mock.Mock(stdout=module_process)) as run:
        result = diagnostics_watcher.watcher_alive(_ctx(memory_dir))

    assert result.passed is False
    assert run.call_count == 0


def test_watcher_identity_cleanup_leaves_a_replacement_record(tmp_path: Path, monkeypatch) -> None:
    """A stopping watcher must not erase a newer watcher's identity record."""
    monkeypatch.setattr(watcher_identity.config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(watcher_identity, "_process_start_token", lambda _pid: "first")
    identity = watcher_identity.write_identity()
    assert identity is not None

    path = tmp_path / ".palinode" / "watcher.json"
    path.write_text(
        json.dumps({"pid": 9999, "process_start": "second", "memory_dir": str(tmp_path)}),
        encoding="utf-8",
    )
    watcher_identity.remove_identity(identity)

    assert json.loads(path.read_text(encoding="utf-8"))["process_start"] == "second"


def test_identity_write_does_not_follow_prepared_predictable_temp_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    """An old predictable temp name must not let a symlink overwrite another file."""
    monkeypatch.setattr(watcher_identity.config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(watcher_identity, "_process_start_token", lambda _pid: "first")
    internal_dir = tmp_path / ".palinode"
    internal_dir.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("preserve me", encoding="utf-8")
    predictable_temp = internal_dir / f"watcher.json.{os.getpid()}.tmp"
    predictable_temp.symlink_to(external)

    identity = watcher_identity.write_identity()

    assert identity is not None
    assert external.read_text(encoding="utf-8") == "preserve me"
    assert predictable_temp.is_symlink()
    assert (internal_dir / "watcher.json").is_file()


def test_identity_write_rejects_symlinked_internal_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(watcher_identity.config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(watcher_identity, "_process_start_token", lambda _pid: "first")
    external_dir = tmp_path / "external-internal"
    external_dir.mkdir()
    (tmp_path / ".palinode").symlink_to(external_dir, target_is_directory=True)

    assert watcher_identity.write_identity() is None
    assert not (external_dir / "watcher.json").exists()


def test_identity_write_rejects_symlinked_final_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(watcher_identity.config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(watcher_identity, "_process_start_token", lambda _pid: "first")
    internal_dir = tmp_path / ".palinode"
    internal_dir.mkdir()
    external = tmp_path / "external-identity.json"
    external.write_text("preserve me", encoding="utf-8")
    (internal_dir / "watcher.json").symlink_to(external)

    assert watcher_identity.write_identity() is None
    assert external.read_text(encoding="utf-8") == "preserve me"


def test_diagnostics_reject_symlinked_identity_record(tmp_path: Path, monkeypatch) -> None:
    memory_dir = tmp_path / "store"
    memory_dir.mkdir()
    external = tmp_path / "external-identity.json"
    external.write_text("{}", encoding="utf-8")
    identity_path = memory_dir / ".palinode" / "watcher.json"
    identity_path.parent.mkdir()
    identity_path.symlink_to(external)
    monkeypatch.setattr(diagnostics_watcher.sys, "platform", "darwin")

    with mock.patch("subprocess.run") as run:
        result = diagnostics_watcher.watcher_alive(_ctx(memory_dir))

    assert result.passed is False
    assert run.call_count == 0


def test_diagnostics_reject_symlinked_internal_directory(tmp_path: Path, monkeypatch) -> None:
    memory_dir = tmp_path / "store"
    memory_dir.mkdir()
    external_dir = tmp_path / "external-internal"
    external_dir.mkdir()
    (memory_dir / ".palinode").symlink_to(external_dir, target_is_directory=True)
    monkeypatch.setattr(diagnostics_watcher.sys, "platform", "darwin")

    with mock.patch("subprocess.run") as run:
        result = diagnostics_watcher.watcher_alive(_ctx(memory_dir))

    assert result.passed is False
    assert run.call_count == 0


def test_cleanup_rejects_symlinked_internal_directory_and_final_record(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(watcher_identity.config, "memory_dir", str(tmp_path))
    external_dir = tmp_path / "external-internal"
    external_dir.mkdir()
    external_record = external_dir / "watcher.json"
    external_record.write_text(
        json.dumps({"pid": 4815, "process_start": "first"}), encoding="utf-8"
    )
    (tmp_path / ".palinode").symlink_to(external_dir, target_is_directory=True)

    watcher_identity.remove_identity((4815, "first"))

    assert external_record.exists()

    (tmp_path / ".palinode").unlink()
    internal_dir = tmp_path / ".palinode"
    internal_dir.mkdir()
    final_record = internal_dir / "watcher.json"
    final_record.symlink_to(external_record)
    watcher_identity.remove_identity((4815, "first"))

    assert final_record.is_symlink()
    assert external_record.exists()


def test_process_start_token_rejects_unsuccessful_ps() -> None:
    with mock.patch(
        "subprocess.run", return_value=mock.Mock(returncode=1, stdout="stale", stderr="")
    ):
        assert watcher_identity._process_start_token(4815) is None

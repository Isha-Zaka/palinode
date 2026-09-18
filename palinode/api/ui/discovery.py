"""Visible-store adapters for inspector discovery; maintenance stays full-store."""
from __future__ import annotations

import os
from typing import Any

from palinode.core import git_tools, store
from palinode.core.config import config
from palinode.core.lint import run_lint_pass
from palinode.core.revalidation import normalize_ref


def discovery_lint(memories: list[dict[str, Any]]) -> dict[str, Any]:
    """Lint only the live visible set, including all cross-file computations."""
    paths = {r["path"] for r in memories}
    lint = run_lint_pass(file_paths=paths)
    refs = {normalize_ref(p) for p in paths}
    # Persisted backing entries can still name a source outside discovery.
    # Do not reveal its ref, retirement state, or even a finding count.
    backing = []
    for finding in lint.get("stale_backing", []):
        entries = [
            e for e in finding.get("stale_backing", [])
            if normalize_ref(str(e.get("ref", ""))) in refs
        ]
        if entries:
            backing.append({"file": finding["file"], "stale_backing": entries})
    lint["stale_backing"] = backing
    lint["no_extraction_meta"] = [{"file": p} for p in sorted(paths)]
    return lint


def indexed_discovery(memories: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    """Count visible chunks and choose recent files before applying a limit.

    Read only aggregate index data; live file rows supply the displayed type.
    Hidden or deleted rows cannot consume the recent list's twelve slots.
    """
    visible = {os.path.join(config.memory_dir, r["path"]): r for r in memories}
    if not visible:
        return 0, []
    try:
        db = store.get_db()
        try:
            rows = db.execute(
                "SELECT file_path, COUNT(*) AS chunks, MAX(created_at) AS recent "
                "FROM chunks GROUP BY file_path ORDER BY recent DESC, file_path"
            ).fetchall()
        finally:
            db.close()
    except Exception:
        return 0, []
    total = 0
    recent = []
    for row in rows:
        memory = visible.get(row["file_path"])
        if memory is None:
            continue
        total += row["chunks"]
        if len(recent) < 12:
            recent.append({"path": memory["path"], "type": memory["type"]})
    return total, recent


def visible_commit_count(memories: list[dict[str, Any]], days: int = 7) -> int:
    """Count commits touching currently visible files, with literal pathspecs.

    Batch paths to keep argv bounded; deduplicate commits touching multiple
    batches. No global limit can let hidden-only commits displace visible ones.
    """
    paths = sorted({r["path"] for r in memories})
    commits: set[str] = set()
    try:
        for start in range(0, len(paths), 200):
            result = git_tools._run_git(
                "--literal-pathspecs", "log", "--format=%H", f"--since={days}.days",
                "HEAD", "--", *paths[start:start + 200],
            )
            if result.returncode == 0:
                commits.update(result.stdout.splitlines())
    except OSError:
        return 0
    return len(commits)

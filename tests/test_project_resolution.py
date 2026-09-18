"""Project identity across real checkouts, worktrees and exposed consumers."""
from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from fastapi.testclient import TestClient

from palinode.api.server import app
from palinode.core.config import config
from palinode.core.context_prime import build_context_digest, format_context_digest, resolve_context


@pytest.fixture(autouse=True)
def clean_context(monkeypatch):
    monkeypatch.delenv("PALINODE_PROJECT", raising=False)
    monkeypatch.delenv("CWD", raising=False)
    monkeypatch.setattr(config.context, "enabled", True)
    monkeypatch.setattr(config.context, "auto_detect", True)
    monkeypatch.setattr(config.context, "project_map", {})


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    main = tmp_path / "renamed-checkout"
    main.mkdir()
    git(main, "init", "-q")
    git(main, "-c", "user.name=Tests", "-c", "user.email=tests@example.com",
        "commit", "--allow-empty", "-qm", "fixture")
    git(main, "remote", "add", "origin", "git@example.com:team/alpha.git")
    worktree = tmp_path / "ephemeral-task"
    git(main, "worktree", "add", "-qb", "task", str(worktree))
    nested = worktree / "src" / "deep"
    nested.mkdir(parents=True)
    return main, worktree, nested


def seed(path: Path, **metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(metadata)}---\nMemory body\n", encoding="utf-8")


def test_git_identity_survives_task_names_and_renames(repository):
    for cwd in repository:
        resolution = resolve_context(cwd=str(cwd))
        assert resolution.project == "project/alpha"
        assert resolution.context == ["project/alpha"]
        assert resolution.basis == "git_origin"
    main, worktree, _ = repository
    git(main, "remote", "remove", "origin")
    assert resolve_context(cwd=str(worktree)).project == "project/renamed-checkout"
    assert resolve_context(cwd=str(worktree)).basis == "git_common_dir"


@pytest.mark.parametrize("remote", [
    "https://user:password@example.com/team/alpha.git",
    "ssh://git@example.com/team/alpha.git", "/repositories/alpha.git",
])
def test_remote_forms_never_expose_url_or_credentials(repository, remote):
    git(repository[0], "remote", "set-url", "origin", remote)
    resolution = resolve_context(cwd=str(repository[1]))
    assert resolution.project == "project/alpha"
    assert "password" not in repr(resolution)


def test_override_precedence_and_config_gate(repository, monkeypatch):
    cwd = str(repository[1])
    monkeypatch.setattr(config.context, "project_map", {"alpha": "mapped"})
    assert resolve_context(cwd=cwd).project == "project/mapped"
    monkeypatch.setitem(config.context.project_map, "ephemeral-task", "task-override")
    assert resolve_context(cwd=cwd).project == "project/task-override"
    monkeypatch.setenv("PALINODE_PROJECT", "environment")
    assert resolve_context(cwd=cwd).project == "project/environment"
    assert resolve_context(cwd=cwd, project="explicit").project == "project/explicit"
    monkeypatch.setattr(config.context, "enabled", False)
    assert resolve_context(cwd=cwd).project is None
    assert resolve_context(cwd=cwd).basis == "disabled"
    assert resolve_context(cwd=cwd, project="explicit").project == "project/explicit"


def test_auto_detect_off_still_allows_repository_mapping(repository, monkeypatch):
    monkeypatch.setattr(config.context, "auto_detect", False)
    assert resolve_context(cwd=str(repository[1])).project is None
    monkeypatch.setitem(config.context.project_map, "alpha", "mapped")
    assert resolve_context(cwd=str(repository[1])).project == "project/mapped"


def test_git_unavailable_is_an_unrecognized_directory_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    candidate = tmp_path / "New Project"
    candidate.mkdir()
    digest = build_context_digest(cwd=str(candidate))
    assert digest["project"] == "project/new-project"
    assert digest["project_resolved_by"] == "cwd_basename"
    assert digest["project_known"] is False
    assert "unrecognized" in format_context_digest(digest)


def test_git_timeout_degrades_without_hanging(tmp_path, monkeypatch):
    from palinode.core import context_prime

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 1
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(context_prime.subprocess, "run", timeout)
    assert resolve_context(cwd=str(tmp_path / "alpha")).basis == "cwd_basename"


def test_inherited_git_environment_cannot_redirect_identity(repository, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/nonexistent/repository")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "remote.origin.url")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://example.com/wrong.git")
    assert resolve_context(cwd=str(repository[1])).project == "project/alpha"


def test_unknown_state_does_not_disclose_hidden_or_retired_projects(tmp_path):
    seed(tmp_path / "decisions" / "private.md", type="Decision",
         entities=["project/alpha"], visibility="private", scope="agent/other")
    seed(tmp_path / "decisions" / "retired.md", type="Decision",
         entities=["project/alpha"], status="archived")
    digest = build_context_digest(project="alpha")
    assert digest["project_known"] is False
    assert digest["recent_decisions"] == []
    seed(tmp_path / "decisions" / "visible.md", type="Decision", entities=["project/alpha"])
    assert build_context_digest(project="alpha")["project_known"] is True


def test_cli_mcp_search_and_prime_share_client_cwd(repository, tmp_path, monkeypatch):
    import palinode.mcp as mcp
    from palinode.cli.search import _cli_resolve_context

    monkeypatch.setenv("CWD", str(repository[2]))
    monkeypatch.chdir(tmp_path)
    assert _cli_resolve_context() == mcp._resolve_context() == ["project/alpha"]
    prime = importlib.import_module("palinode.cli.prime")
    from palinode.cli._api import PalinodeAPI

    api = PalinodeAPI.__new__(PalinodeAPI)
    api.client = TestClient(app)
    monkeypatch.setattr(prime, "api_client", api)
    result = CliRunner().invoke(prime.prime, ["--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["project"] == "project/alpha"
    assert data["project_resolved_by"] == "git_origin"
    monkeypatch.setattr(config.context, "enabled", False)
    assert _cli_resolve_context() is mcp._resolve_context() is None


@pytest.mark.asyncio
async def test_mcp_and_api_prime_isolation_and_disabled_context(repository, tmp_path, monkeypatch):
    import palinode.mcp as mcp

    seed(tmp_path / "decisions" / "alpha.md", type="Decision", entities=["project/alpha"], title="Alpha choice")
    seed(tmp_path / "decisions" / "beta.md", type="Decision", entities=["project/beta"], title="Beta choice")
    client = TestClient(app)

    async def post(path, json=None, **kwargs):
        return client.post(path, json=json)

    monkeypatch.setattr(mcp, "_post", post)
    monkeypatch.setattr(config.auto_inject, "enabled", True)
    monkeypatch.setattr(mcp, "_session_init_client_name", lambda: "test-client")
    monkeypatch.setenv("CWD", str(repository[1]))
    result = await mcp._dispatch_tool("palinode_session_init", {})
    assert "git_origin; known" in result[0].text
    assert "Alpha choice" in result[0].text
    assert "Beta choice" not in result[0].text
    monkeypatch.setattr(config.context, "enabled", False)
    result = await mcp._dispatch_tool("palinode_session_init", {})
    assert "Alpha choice" not in result[0].text
    assert "no project resolved" in result[0].text
    result = await mcp._dispatch_tool("palinode_session_init", {"project": "beta"})
    assert "Beta choice" in result[0].text
    assert "Alpha choice" not in result[0].text


@pytest.mark.asyncio
async def test_mcp_session_init_forwards_each_stdio_environment_scope(repository, tmp_path, monkeypatch):
    """A stdio client's project env survives an API process without that env."""
    import palinode.mcp as mcp

    for project in ("harbor-notes", "field-journal"):
        seed(tmp_path / "decisions" / f"{project}.md", type="Decision",
             entities=[f"project/{project}"], title=f"{project} decision")
    client = TestClient(app)
    bodies = []

    async def post_in_api_process(path, json=None, **kwargs):
        bodies.append(json)
        # The real API is a separately-launched process, so it does not inherit
        # a generated stdio client's client-specific PALINODE_PROJECT.
        with monkeypatch.context() as api_env:
            api_env.delenv("PALINODE_PROJECT", raising=False)
            response = client.post(path, json=json)
        assert response.status_code == 200, response.text
        return response

    monkeypatch.setattr(mcp, "_post", post_in_api_process)
    monkeypatch.setattr(mcp, "_session_init_client_name", lambda: "test-client")
    monkeypatch.setattr(config.auto_inject, "enabled", True)
    for project in ("harbor-notes", "field-journal"):
        # Each context represents an independently launched stdio client.  A
        # module-level client cache would make the second assertion fail.
        with monkeypatch.context() as client_env:
            client_env.setenv("CWD", str(repository[1]))
            client_env.setenv("PALINODE_PROJECT", project)
            result = await mcp._dispatch_tool("palinode_session_init", {})
        assert f"Session context: project/{project}" in result[0].text
        assert f"{project} decision" in result[0].text

    assert bodies == [
        {"cwd": str(repository[1]), "project": "project/harbor-notes"},
        {"cwd": str(repository[1]), "project": "project/field-journal"},
    ]


@pytest.mark.asyncio
async def test_mcp_session_init_explicit_project_beats_stdio_environment(repository, tmp_path, monkeypatch):
    """A caller's project argument remains the highest-precedence scope."""
    import palinode.mcp as mcp

    seed(tmp_path / "decisions" / "override.md", type="Decision",
         entities=["project/call-override"], title="Call override decision")
    client = TestClient(app)
    captured = {}

    async def post_in_api_process(path, json=None, **kwargs):
        captured["body"] = json
        with monkeypatch.context() as api_env:
            api_env.delenv("PALINODE_PROJECT", raising=False)
            response = client.post(path, json=json)
        return response

    monkeypatch.setattr(mcp, "_post", post_in_api_process)
    monkeypatch.setattr(mcp, "_session_init_client_name", lambda: "test-client")
    monkeypatch.setattr(config.auto_inject, "enabled", True)
    monkeypatch.setenv("CWD", str(repository[1]))
    monkeypatch.setenv("PALINODE_PROJECT", "harbor-notes")
    result = await mcp._dispatch_tool(
        "palinode_session_init", {"project": "call-override", "cwd": str(repository[1])},
    )

    assert captured["body"] == {"project": "call-override", "cwd": str(repository[1])}
    assert "Session context: project/call-override" in result[0].text
    assert "Call override decision" in result[0].text


@pytest.mark.asyncio
async def test_mcp_session_init_without_stdio_project_keeps_cwd_request(repository, tmp_path, monkeypatch):
    """Blank or unset client project settings retain the legacy cwd handoff."""
    import palinode.mcp as mcp

    seed(tmp_path / "decisions" / "alpha.md", type="Decision",
         entities=["project/alpha"], title="Git resolved decision")
    client = TestClient(app)
    captured = {}

    async def post_in_api_process(path, json=None, **kwargs):
        captured["body"] = json
        with monkeypatch.context() as api_env:
            api_env.delenv("PALINODE_PROJECT", raising=False)
            response = client.post(path, json=json)
        return response

    monkeypatch.setattr(mcp, "_post", post_in_api_process)
    monkeypatch.setattr(mcp, "_session_init_client_name", lambda: "test-client")
    monkeypatch.setattr(config.auto_inject, "enabled", True)
    monkeypatch.setenv("CWD", str(repository[1]))
    monkeypatch.setenv("PALINODE_PROJECT", "")
    result = await mcp._dispatch_tool("palinode_session_init", {})

    assert captured["body"] == {"cwd": str(repository[1])}
    assert "Session context: project/alpha" in result[0].text
    assert "Git resolved decision" in result[0].text


@pytest.mark.asyncio
async def test_direct_prime_remains_available_when_automatic_mcp_prime_is_suppressed(tmp_path, monkeypatch):
    import palinode.mcp as mcp

    seed(tmp_path / "decisions" / "alpha.md", type="Decision", entities=["project/alpha"])
    monkeypatch.setattr(config.auto_inject, "enabled", False)
    response = TestClient(app).post("/context/prime", json={"project": "alpha"})
    assert response.status_code == 200
    assert response.json()["recent_decisions"]
    result = await mcp._dispatch_tool("palinode_session_init", {"project": "alpha"})
    assert "disabled" in result[0].text
    monkeypatch.setattr(config.auto_inject, "enabled", True)
    monkeypatch.setattr(config.auto_inject, "harnesses_disabled", ["test-client"])
    monkeypatch.setattr(mcp, "_session_init_client_name", lambda: "test-client")
    result = await mcp._dispatch_tool("palinode_session_init", {"project": "alpha"})
    assert "suppressed" in result[0].text
    assert TestClient(app).post("/context/prime", json={"project": "alpha"}).json()["recent_decisions"]


def test_save_session_end_and_fresh_prime_agree(repository, tmp_path, monkeypatch):
    from palinode.core import embedder, store
    from palinode.core.parser import parse_frontmatter

    monkeypatch.setattr(config.git, "auto_commit", False)
    monkeypatch.setattr(config.git, "auto_push", False)
    monkeypatch.setattr(embedder, "embed", lambda text: ([0.0, 1.0] if "Verified" in text else [1.0, 0.0]) + [0.0] * 1022)
    store.init_db()
    client = TestClient(app)
    # Save is deliberately explicit; unrelated captures never acquire an
    # ambient project tag just because a server happens to run inside a repo.
    response = client.post("/save", json={"content": "Use atomic updates", "type": "Decision", "project": "alpha"})
    assert response.status_code == 200, response.text
    seed(tmp_path / "projects" / "alpha-status.md", type="ProjectSnapshot", entities=["project/alpha"])
    response = client.post("/session-end", json={
        "summary": "Verified atomic updates", "decisions": [], "blockers": [],
        "cwd": str(repository[2]), "push": False,
    })
    assert response.status_code == 200, response.text
    assert response.json()["status_file"] == "projects/alpha-status.md"
    metadata, _ = parse_frontmatter(Path(response.json()["individual_file"]).read_text())
    assert "project/alpha" in metadata["entities"]
    for cwd in repository:
        digest = TestClient(app).post("/context/prime", json={"cwd": str(cwd)}).json()
        assert digest["project"] == "project/alpha"
        assert digest["project_known"] is True
        assert digest["recent_decisions"]
        assert digest["recent_snapshots"]
    monkeypatch.setattr(config.context, "enabled", False)
    disabled = client.post("/session-end", json={
        "summary": "No ambient scope", "decisions": [], "blockers": [],
        "cwd": str(repository[1]), "dry_run": True,
    })
    assert disabled.json()["status_file"] is None
    explicit = client.post("/session-end", json={
        "summary": "Explicit scope", "decisions": [], "blockers": [],
        "cwd": str(repository[1]), "project": "project/alpha", "dry_run": True,
    })
    assert explicit.json()["status_file"] == "projects/alpha-status.md"


@pytest.mark.parametrize("project", ["../escape", "project/../../escape", "org/alpha", "project/alpha/beta", "alpha\\beta"])
def test_session_end_rejects_unsafe_resolved_project_before_writes(tmp_path, monkeypatch, project):
    monkeypatch.setenv("PALINODE_PROJECT", project)
    response = TestClient(app).post("/session-end", json={
        "summary": "Must not write", "decisions": [], "blockers": [],
    })
    assert response.status_code == 400
    assert not list(tmp_path.rglob("*.md"))


def test_malformed_cwd_does_not_crash_git_probe():
    resolution = resolve_context(cwd="/missing/alpha\x00")
    assert resolution.basis == "cwd_basename"
    assert resolution.project == "project/alpha"


@pytest.mark.asyncio
async def test_cli_mcp_session_end_use_the_same_worktree(repository, tmp_path, monkeypatch):
    import palinode.mcp as mcp
    from palinode.cli._api import PalinodeAPI

    seed(tmp_path / "projects" / "alpha-status.md", entities=["project/alpha"])
    api = PalinodeAPI.__new__(PalinodeAPI)
    api.client = TestClient(app)
    session = importlib.import_module("palinode.cli.session_end")
    monkeypatch.setattr(session, "api_client", api)
    result = CliRunner().invoke(session.session_end, [
        "Scope check", "--cwd", str(repository[1]), "--dry-run", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["project_status"] == "projects/alpha-status.md"

    async def post(path, json=None, **kwargs):
        return api.client.post(path, json=json)

    monkeypatch.setattr(mcp, "_post", post)
    result = await mcp._dispatch_tool("palinode_session_end", {
        "summary": "Scope check", "decisions": [], "blockers": [],
        "cwd": str(repository[2]), "dry_run": True,
    })
    assert "projects/alpha-status.md" in result[0].text
    assert not list((tmp_path / "daily").glob("*.md"))


@pytest.mark.asyncio
async def test_search_wire_context_agrees_across_cli_and_mcp(repository, monkeypatch):
    import palinode.mcp as mcp
    from palinode.cli._api import PalinodeAPI

    captured = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return []

    class Transport:
        def post(self, path, json=None, **kwargs):
            captured.append(json)
            return Response()

    api = PalinodeAPI.__new__(PalinodeAPI)
    api.client = Transport()
    search = importlib.import_module("palinode.cli.search")
    monkeypatch.setattr(search, "api_client", api)
    monkeypatch.setenv("CWD", str(repository[2]))

    async def post(path, json=None, **kwargs):
        return api.client.post(path, json=json)

    monkeypatch.setattr(mcp, "_post", post)
    result = CliRunner().invoke(search.search, ["atomic updates", "--format", "json"])
    assert result.exit_code == 0, result.output
    await mcp._dispatch_tool("palinode_search", {"query": "atomic updates"})
    assert [request["context"] for request in captured] == [["project/alpha"], ["project/alpha"]]
    captured.clear()
    monkeypatch.setattr(config.context, "enabled", False)
    result = CliRunner().invoke(search.search, ["atomic updates", "--format", "json"])
    assert result.exit_code == 0, result.output
    await mcp._dispatch_tool("palinode_search", {"query": "atomic updates"})
    assert all(not request.get("context") for request in captured)

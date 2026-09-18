"""Optional wheel-install acceptance: PALINODE_TEST_INSTALL names an isolated venv.

Install this checkout's wheel there first; dependencies must be present. Neither
server uses the developer's live memory or credentials. No model calls are made.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tomllib

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.integration.test_mcp_stdio import _free_port, _wait_for_health, _drain

CLAUDE_CLI = os.environ.get("PALINODE_TEST_CLAUDE")


@pytest.fixture
def installed_api(tmp_path, monkeypatch):
    import threading

    install = os.environ.get("PALINODE_TEST_INSTALL")
    if not install:
        pytest.skip("Set PALINODE_TEST_INSTALL to an isolated installation of this checkout")
    install = Path(install).absolute()
    home = tmp_path / "home"
    home.mkdir()
    store = tmp_path / "disposable memory"
    store.mkdir()
    token_file = tmp_path / "test token"
    token_file.write_text("fixture-only-token")
    port = _free_port()
    (store / "palinode.config.yaml").write_text(
        f"services:\n  api:\n    host: 127.0.0.1\n    port: {port}\n"
        "auto_summary:\n  enabled: false\nauto_inject:\n  enabled: true\n"
        "context:\n  enabled: true\n  auto_detect: true\n"
    )
    minimal = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8",
               "TMPDIR": str(tmp_path), "GIT_CEILING_DIRECTORIES": str(tmp_path)}
    connection = {"PALINODE_DIR": str(store), "PALINODE_API_TOKEN_FILE": str(token_file)}
    # Package identity is measured outside the checkout with PYTHONPATH absent.
    identity = subprocess.run(
        [str(install / "bin/python"), "-c",
         "import palinode; print(palinode.__file__); print(palinode.__version__)"],
        cwd=tmp_path, env=minimal, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    assert str(install) in identity[0]
    proc = subprocess.Popen([str(install / "bin/palinode-api")], cwd=tmp_path,
                            env={**minimal, **connection}, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    out, err = bytearray(), bytearray()
    for stream, buf in ((proc.stdout, out), (proc.stderr, err)):
        threading.Thread(target=_drain, args=(stream, buf), daemon=True).start()
    try:
        _wait_for_health(port, proc, out, err)
        # Prove the disposable API requires auth before using the generated config.
        assert httpx.post(f"http://127.0.0.1:{port}/context/prime", json={}).status_code == 401
        monkeypatch.setattr(os, "environ", minimal.copy())
        yield install, tmp_path, minimal, connection, identity[1]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("editor", ["claude-code", "codex"])
async def test_generated_wheel_config_launches_and_reaches_project_api(installed_api, editor):
    install, tmp_path, minimal, connection, version = installed_api
    preview = subprocess.run(
        [str(install / "bin/palinode"), "mcp-config", "--stdio", "--editor", editor],
        cwd=tmp_path, env={**minimal, **connection}, capture_output=True, text=True, check=True,
    ).stdout
    entry = (tomllib.loads(preview)["mcp_servers"]["palinode"] if editor == "codex"
             else json.loads(preview)["mcpServers"]["palinode"])
    assert entry["command"] == str(install / "bin/palinode-mcp")
    assert "fixture-only-token" not in preview
    assert "VIRTUAL_ENV" not in entry["env"]
    assert "PYTHONPATH" not in entry["env"]
    params = StdioServerParameters(command=entry["command"], args=[],
                                   env={**minimal, **entry["env"]}, cwd=str(tmp_path))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.server_info.version == version
            tools = await session.list_tools()
            assert "palinode_session_init" in {t.name for t in tools.tools}
            result = await session.call_tool("palinode_session_init", {"project": "isolated-config-proof"})
            assert not result.is_error
            assert "project/isolated-config-proof" in result.content[0].text


def test_codex_reads_generated_toml(installed_api):
    import shutil

    install, tmp_path, minimal, connection, _version = installed_api
    client = shutil.which("codex", path="/opt/homebrew/bin:/usr/local/bin:/usr/bin")
    if not client:
        pytest.skip("Codex CLI not installed")
    preview = subprocess.run(
        [str(install / "bin/palinode"), "mcp-config", "--stdio", "--editor", "codex"],
        cwd=tmp_path, env={**minimal, **connection}, capture_output=True, text=True, check=True,
    ).stdout
    codex_home = tmp_path / "codex config"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(preview)
    result = subprocess.run([client, "mcp", "get", "palinode", "--json"], cwd=tmp_path,
                            env={**minimal, "CODEX_HOME": str(codex_home)},
                            capture_output=True, text=True, timeout=30, check=True)
    payload = json.loads(result.stdout)
    assert payload["transport"]["command"] == str(install / "bin/palinode-mcp")


def test_claude_code_connects_with_generated_project_config(installed_api):
    if not CLAUDE_CLI:
        pytest.skip("Set PALINODE_TEST_CLAUDE to an installed Claude Code executable")
    install, tmp_path, minimal, connection, _version = installed_api
    preview = subprocess.run(
        [str(install / "bin/palinode"), "mcp-config", "--stdio", "--editor", "claude-code"],
        cwd=tmp_path, env={**minimal, **connection}, capture_output=True, text=True, check=True,
    ).stdout
    (tmp_path / ".mcp.json").write_text(preview)
    result = subprocess.run([CLAUDE_CLI, "mcp", "list"], cwd=tmp_path,
                            env={**minimal, "CLAUDE_CONFIG_DIR": str(tmp_path / "claude config"),
                                 "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1"},
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    assert "palinode:" in result.stdout
    assert "Pending approval" in result.stdout, result.stdout
    # Project approval is an interactive client step. Separately exercise its
    # supported local registration command in this disposable profile.
    (tmp_path / ".mcp.json").unlink()
    client_env = {**minimal, "CLAUDE_CONFIG_DIR": str(tmp_path / "claude config"),
                  "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1"}
    entry = json.loads(preview)["mcpServers"]["palinode"]
    subprocess.run([CLAUDE_CLI, "mcp", "add-json", "--scope", "local", "palinode", json.dumps(entry)],
                   cwd=tmp_path, env=client_env, capture_output=True, text=True, timeout=30, check=True)
    connected = subprocess.run([CLAUDE_CLI, "mcp", "list"], cwd=tmp_path,
                               env=client_env, capture_output=True, text=True, timeout=40, check=True)
    assert "Connected" in connected.stdout, connected.stdout

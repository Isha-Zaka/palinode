"""Safe, server-owned destination disclosure for first-use status surfaces."""
from __future__ import annotations

import subprocess  # nosec B404 - fixed local Git observation for the configured store
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from palinode.core.config import config


# CLI and MCP must make the same bounded claim about these controls.
PAUSE_SCOPE = (
    "future API-routed capture and recall requests only; pauses do not delete "
    "stored history, block direct-file legacy clients or client-native traffic, "
    "stop background indexing, enrichment, or consolidation, cancel in-flight "
    "requests, remove already delivered context, or provide access control"
)
EXCLUSION_SCOPE = (
    "project/path exclusions apply automatic capture and recall, not explicit "
    "user/API writes or recall"
)
PAUSED_READ_AVAILABILITY = (
    "This status tool and history reads remain available while capture and "
    "recall are paused."
)


def redact_destination(value: object) -> str:
    """Return a useful destination without userinfo, query values, or fragments."""
    text = str(value or "")
    if not text:
        return "unknown"
    try:
        parsed = urlsplit(text)
    except ValueError:
        # urlsplit rejects malformed bracketed IPv6 hosts.  Such a value may
        # still contain credentials, so preserve only its useful destination
        # shape after removing userinfo and query/fragment values.
        base = text.split("?", 1)[0].split("#", 1)[0]
        suffix = "?***" if "?" in text else ""
        if "@" not in base:
            return "invalid destination"
        prefix, rest = base.rsplit("@", 1)
        if "://" in prefix:
            scheme = prefix.split("://", 1)[0]
            return f"{scheme}://***@{rest}" + suffix
        return f"***@{rest}" + suffix
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname
        if not host:
            return f"{parsed.scheme}://***"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is not None:
            host = f"{host}:{port}"
        userinfo = "***@" if "@" in parsed.netloc else ""
        return urlunsplit((parsed.scheme, f"{userinfo}{host}", parsed.path, "***" if parsed.query else "", ""))
    # SCP-like remotes have no URL parser. A colon before @ can carry a
    # password; redact the whole userinfo segment in that non-standard form.
    if "@" in text:
        prefix, rest = text.split("@", 1)
        if ":" in prefix:
            return f"***@{rest.split('?', 1)[0]}" + ("?***" if "?" in rest else "")
    return text.split("?", 1)[0].split("#", 1)[0] + ("?***" if "?" in text else "")


def _redact_remote_line(line: str) -> str:
    fields = line.split()
    if len(fields) < 2:
        return redact_destination(line)
    return " ".join([fields[0], redact_destination(fields[1]), *fields[2:]])


def _configured_git_remotes() -> list[str]:
    """Observe remotes at the API server's configured store, never a caller path."""
    try:
        result = subprocess.run(  # nosec B603 - configured store passed as one argv value
            ["git", "-C", config.memory_dir, "remote", "-v"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [_redact_remote_line(line) for line in result.stdout.splitlines() if line.strip()]


def _fallback_destinations(fallbacks: object) -> list[str]:
    """Return redacted URLs from the configured ``list[dict]`` fallback shape."""
    if not isinstance(fallbacks, list):
        return []
    return [
        redact_destination(fallback["url"])
        for fallback in fallbacks
        if isinstance(fallback, dict) and isinstance(fallback.get("url"), str)
    ]


def runtime_disclosure() -> dict[str, Any]:
    """Return configured server destinations for ``GET /status``.

    Values describe configuration, not observed network traffic or a successful
    connection. URL credentials and query values are redacted before crossing
    the API boundary.
    """
    return {
        "memory_dir": config.memory_dir,
        "api_url": redact_destination(f"http://{config.services.api.host}:{config.services.api.port}"),
        "embedding_url": redact_destination(config.embeddings.primary.url),
        "auto_summary_enabled": config.auto_summary.enabled,
        "auto_summary_primary_url": redact_destination(
            config.auto_summary.ollama_url or config.embeddings.primary.url
        ),
        "auto_summary_llm_fallbacks": _fallback_destinations(
            config.auto_summary.llm_fallbacks
        ),
        "consolidation_enabled": config.consolidation.enabled,
        "consolidation_url": redact_destination(config.consolidation.llm_url),
        "consolidation_llm_fallbacks": _fallback_destinations(
            config.consolidation.llm_fallbacks
        ),
        # TranscriptorConfig has a configured endpoint but no enabled flag.
        "transcriptor_url": redact_destination(config.ingestion.transcriptor.url),
        "git_remotes": _configured_git_remotes(),
        "git_push_policy": (
            "automatic after committed writes (git.auto_push=true)"
            if config.git.auto_push
            else "manual only (git.auto_push=false)"
        ),
    }

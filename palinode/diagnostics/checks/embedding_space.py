from __future__ import annotations

import sqlite3
from pathlib import Path

from palinode.diagnostics.registry import register
from palinode.diagnostics.types import CheckResult, DoctorContext


@register(tags=("fast",))
def embedding_space_consistency(ctx: DoctorContext) -> CheckResult:
    """Compare recorded embedding provenance with the active configuration."""

    db_path = Path(ctx.config.db_path).expanduser().resolve()

    if not db_path.exists():
        return CheckResult(
            name="embedding_space_consistency",
            severity="info",
            passed=True,
            message="Database does not exist yet; no embedding space is recorded.",
            remediation=None,
        )

    try:
        uri = f"file:{db_path}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=2.0)

        try:
            table_exists = con.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'embedding_space'
                """
            ).fetchone()

            if table_exists is None:
                return CheckResult(
                    name="embedding_space_consistency",
                    severity="warn",
                    passed=False,
                    message=(
                        "Database has no recorded embedding space; "
                        "its existing vectors cannot be independently verified."
                    ),
                    remediation=(
                        "Start Palinode once with the intended embedding configuration "
                        "to adopt the active model and dimensions for this legacy store."
                    ),
                )

            row = con.execute(
                """
                SELECT model, dimensions
                FROM embedding_space
                WHERE id = 1
                """
            ).fetchone()

        finally:
            con.close()

    except sqlite3.Error as exc:
        return CheckResult(
            name="embedding_space_consistency",
            severity="error",
            passed=False,
            message=f"Could not inspect embedding space metadata: {exc}",
            remediation="Verify that db_path points to a valid Palinode database.",
        )

    if row is None:
        return CheckResult(
            name="embedding_space_consistency",
            severity="warn",
            passed=False,
            message="Embedding space metadata table exists but contains no recorded space.",
            remediation=(
                "Start Palinode once with the intended embedding configuration "
                "to initialize the embedding-space metadata."
            ),
        )

    recorded_model = row[0]
    recorded_dimensions = int(row[1])

    configured_model = ctx.config.embeddings.primary.model
    configured_dimensions = int(ctx.config.embeddings.primary.dimensions)

    if (
        recorded_model == configured_model
        and recorded_dimensions == configured_dimensions
    ):
        return CheckResult(
            name="embedding_space_consistency",
            severity="error",
            passed=True,
            message=(
                "Recorded embedding space matches configuration: "
                f"model={configured_model!r}, "
                f"dimensions={configured_dimensions}."
            ),
            remediation=None,
        )

    return CheckResult(
        name="embedding_space_consistency",
        severity="error",
        passed=False,
        message=(
            "Embedding space mismatch: "
            f"database uses model={recorded_model!r}, "
            f"dimensions={recorded_dimensions}; "
            f"configuration uses model={configured_model!r}, "
            f"dimensions={configured_dimensions}."
        ),
        remediation=(
            "Delete .palinode.db, then run `palinode reindex`. "
            "Warning: deleting the database also removes DB-only state, "
            "including registered triggers and recall reinforcement state "
            "(importance, last_recalled, recall_count)."
        ),
    )

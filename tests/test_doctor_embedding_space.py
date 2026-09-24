import sqlite3
from pathlib import Path

from palinode.core.config import Config
from palinode.diagnostics.checks.embedding_space import embedding_space_consistency
from palinode.diagnostics.types import DoctorContext


def _ctx(
    tmp_path: Path,
    *,
    model: str = "model-a",
    dimensions: int = 1024,
) -> DoctorContext:
    db_path = tmp_path / ".palinode.db"

    cfg = Config(
        memory_dir=str(tmp_path),
        db_path=str(db_path),
    )
    cfg.embeddings.primary.model = model
    cfg.embeddings.primary.dimensions = dimensions

    return DoctorContext(config=cfg)


def _write_embedding_space(
    db_path: Path,
    *,
    model: str,
    dimensions: int,
) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE embedding_space (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL
            )
            """
        )
        db.execute(
            """
            INSERT INTO embedding_space (id, model, dimensions)
            VALUES (1, ?, ?)
            """,
            (model, dimensions),
        )


def test_doctor_passes_when_embedding_space_matches(tmp_path):
    ctx = _ctx(tmp_path, model="model-a", dimensions=1024)

    _write_embedding_space(
        Path(ctx.config.db_path),
        model="model-a",
        dimensions=1024,
    )

    result = embedding_space_consistency(ctx)

    assert result.passed is True
    assert "matches" in result.message.lower()
    assert result.remediation is None


def test_doctor_fails_when_embedding_space_mismatches(tmp_path):
    ctx = _ctx(tmp_path, model="model-b", dimensions=1024)

    _write_embedding_space(
        Path(ctx.config.db_path),
        model="model-a",
        dimensions=1024,
    )

    result = embedding_space_consistency(ctx)

    assert result.passed is False
    assert result.severity == "error"
    assert "mismatch" in result.message.lower()
    assert "model-a" in result.message
    assert "model-b" in result.message
    assert ".palinode.db" in result.remediation
    assert "palinode reindex" in result.remediation


def test_doctor_warns_for_legacy_database_without_provenance(tmp_path):
    ctx = _ctx(tmp_path)

    # Valid existing SQLite DB, but no embedding_space table.
    with sqlite3.connect(ctx.config.db_path) as db:
        db.execute("CREATE TABLE chunks (id TEXT PRIMARY KEY)")

    result = embedding_space_consistency(ctx)

    assert result.passed is False
    assert result.severity == "warn"
    assert "no recorded embedding space" in result.message.lower()
    assert "cannot be independently verified" in result.message.lower()

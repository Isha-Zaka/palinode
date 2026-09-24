import pytest
import sqlite3
import logging
import json

from palinode.core import store
from palinode.core.config import config


def test_rejects_same_dimensions_with_different_model(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / ".palinode.db"

    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(config, "db_path", str(db_path))
    monkeypatch.setattr(store, "_db_checked", False)

    monkeypatch.setattr(config.embeddings.primary, "model", "model-a")
    monkeypatch.setattr(config.embeddings.primary, "dimensions", 1024)

    # First startup creates the database with model-a / 1024.
    store.init_db()

    # Same dimensions, but a different embedding model.
    monkeypatch.setattr(config.embeddings.primary, "model", "model-b")

    with pytest.raises(RuntimeError, match="Embedding space"):
        store.init_db()


def test_rejects_different_embedding_dimensions(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / ".palinode.db"

    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(config, "db_path", str(db_path))
    monkeypatch.setattr(store, "_db_checked", False)

    monkeypatch.setattr(config.embeddings.primary, "model", "model-a")
    monkeypatch.setattr(config.embeddings.primary, "dimensions", 1024)

    store.init_db()

    monkeypatch.setattr(config.embeddings.primary, "dimensions", 768)

    with pytest.raises(RuntimeError, match="Embedding space"):
        store.init_db()


def test_records_embedding_space_on_first_init(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / ".palinode.db"

    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(config, "db_path", str(db_path))
    monkeypatch.setattr(store, "_db_checked", False)

    monkeypatch.setattr(config.embeddings.primary, "model", "model-a")
    monkeypatch.setattr(config.embeddings.primary, "dimensions", 1024)

    store.init_db()

    with sqlite3.connect(db_path) as db:
        row = db.execute(
            """
            SELECT model, dimensions
            FROM embedding_space
            WHERE id = 1
            """
        ).fetchone()

    assert row == ("model-a", 1024)


def test_legacy_database_adopts_embedding_space_with_warning(
    tmp_path,
    monkeypatch,
    caplog,
):
    db_path = tmp_path / ".palinode.db"

    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(config, "db_path", str(db_path))
    monkeypatch.setattr(store, "_db_checked", False)

    monkeypatch.setattr(config.embeddings.primary, "model", "model-a")
    monkeypatch.setattr(config.embeddings.primary, "dimensions", 1024)

    # Create a normal database first so chunks_vec/triggers_vec exist.
    store.init_db()

    # Simulate a legacy database: vector indexes exist, but provenance does not.
    with sqlite3.connect(db_path) as db:
        db.execute("DROP TABLE embedding_space")

    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="palinode.store"):
        store.init_db()

    with sqlite3.connect(db_path) as db:
        row = db.execute(
            """
            SELECT model, dimensions
            FROM embedding_space
            WHERE id = 1
            """
        ).fetchone()

    assert row == ("model-a", 1024)

    log_text = caplog.text.lower()
    assert "adopt" in log_text
    assert "cannot be independently verified" in log_text


@pytest.mark.parametrize("vector_table", ["chunks_vec", "triggers_vec"])
@pytest.mark.parametrize(
    ("new_model", "new_dimensions"),
    [
        ("model-b", 1024),  # same dimensions, different model
        ("model-b", 768),   # different dimensions
    ],
)
def test_rejects_embedding_space_mismatch_for_each_vector_table(
    tmp_path,
    monkeypatch,
    vector_table,
    new_model,
    new_dimensions,
):
    db_path = tmp_path / ".palinode.db"

    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(config, "db_path", str(db_path))
    monkeypatch.setattr(store, "_db_checked", False)

    monkeypatch.setattr(config.embeddings.primary, "model", "model-a")
    monkeypatch.setattr(config.embeddings.primary, "dimensions", 1024)

    store.init_db()

    # Put a real 1024-dimensional vector into the table so this represents
    # an index that was actually built in the original embedding space.
    with store.get_db() as db:
        db.execute(
            f"INSERT INTO {vector_table} (id, embedding) VALUES (?, ?)",
            ("existing-vector", json.dumps([0.0] * 1024)),
        )
        db.commit()

    monkeypatch.setattr(config.embeddings.primary, "model", new_model)
    monkeypatch.setattr(
        config.embeddings.primary,
        "dimensions",
        new_dimensions,
    )

    with pytest.raises(RuntimeError, match="Embedding space mismatch"):
        store.init_db()


def test_embedding_space_mismatch_error_explains_recovery(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / ".palinode.db"

    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    monkeypatch.setattr(config, "db_path", str(db_path))
    monkeypatch.setattr(store, "_db_checked", False)

    monkeypatch.setattr(config.embeddings.primary, "model", "model-a")
    monkeypatch.setattr(config.embeddings.primary, "dimensions", 1024)

    store.init_db()

    monkeypatch.setattr(config.embeddings.primary, "model", "model-b")

    with pytest.raises(RuntimeError) as exc_info:
        store.init_db()

    message = str(exc_info.value)

    assert "model-a" in message
    assert "model-b" in message
    assert "delete" in message.lower()
    assert ".palinode.db" in message
    assert "palinode reindex" in message
    assert "triggers" in message
    assert "importance" in message
    assert "last_recalled" in message
    assert "recall_count" in message

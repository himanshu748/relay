from pathlib import Path
from shutil import copyfile
import sqlite3
from types import SimpleNamespace

from sibyl_memory_client import MemoryClient
from vercel.blob import BlobNotFoundError

from backend.app.main import create_app
from backend.app.services import memory as memory_module
from backend.app.schemas import EventCreate
from backend.app.services.memory import IncidentMemory


class FileSnapshotStore:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path

    def restore(self, database_path: Path) -> bool:
        if not self.snapshot_path.exists():
            return False
        copyfile(self.snapshot_path, database_path)
        return True

    def persist(self, database_path: Path) -> None:
        copyfile(database_path, self.snapshot_path)


def test_observation_survives_a_new_memory_process(tmp_path: Path) -> None:
    snapshots = FileSnapshotStore(tmp_path / "durable-memory.db")
    first = IncidentMemory(tmp_path / "first-process.db", snapshot_store=snapshots)
    first.state()
    first.add_event(
        "INC-204",
        EventCreate(
            kind="observation",
            summary="Durable probe survived a cold start",
        ),
    )

    second = IncidentMemory(tmp_path / "second-process.db", snapshot_store=snapshots)
    state = second.state()

    assert "Durable probe survived a cold start" in state.incident.observations


def test_blob_snapshot_restores_private_database_bytes(tmp_path: Path) -> None:
    class FakeBlobClient:
        def get(self, path: str, **options: object) -> SimpleNamespace:
            assert path == "relay/sibyl-memory.db"
            assert options == {"access": "private", "use_cache": False}
            return SimpleNamespace(content=b"sqlite snapshot")

    snapshot_store = memory_module.BlobSnapshotStore(
        token="test-token",
        client=FakeBlobClient(),
    )
    database_path = tmp_path / "restored.db"

    restored = snapshot_store.restore(database_path)

    assert restored is True
    assert database_path.read_bytes() == b"sqlite snapshot"


def test_blob_snapshot_allows_first_run_without_a_snapshot(tmp_path: Path) -> None:
    class EmptyBlobClient:
        def get(self, path: str, **options: object) -> SimpleNamespace:
            raise BlobNotFoundError()

    snapshot_store = memory_module.BlobSnapshotStore(
        token="test-token",
        client=EmptyBlobClient(),
    )
    database_path = tmp_path / "first-run.db"

    restored = snapshot_store.restore(database_path)

    assert restored is False
    assert database_path.exists() is False


def test_blob_snapshot_persists_private_database_bytes(tmp_path: Path) -> None:
    writes: list[tuple[str, bytes, dict[str, object]]] = []

    class FakeBlobClient:
        def put(self, path: str, body: bytes, **options: object) -> None:
            writes.append((path, body, options))

    snapshot_store = memory_module.BlobSnapshotStore(
        token="test-token",
        client=FakeBlobClient(),
    )
    database_path = tmp_path / "memory.db"
    database_path.write_bytes(b"checkpointed sqlite")

    snapshot_store.persist(database_path)

    assert writes == [
        (
            "relay/sibyl-memory.db",
            b"checkpointed sqlite",
            {
                "access": "private",
                "content_type": "application/vnd.sqlite3",
                "overwrite": True,
            },
        )
    ]


def test_api_uses_private_blob_snapshots_when_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RELAY_READ_WRITE_TOKEN", "test-token")
    monkeypatch.setattr(
        memory_module.BlobSnapshotStore,
        "restore",
        lambda self, database_path: False,
    )

    app = create_app(tmp_path / "memory.db")

    assert isinstance(app.state.memory.snapshot_store, memory_module.BlobSnapshotStore)


def test_restored_database_repairs_an_incompatible_shadow_tokenizer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "portable.db"
    client = MemoryClient.local(database_path)
    client.set_entity("incident", "INC-204", {"status": "investigating"})
    client.storage.close()

    with sqlite3.connect(database_path) as connection:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'search_shadow'"
        ).fetchone()[0]
        schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
        connection.execute("PRAGMA writable_schema = ON")
        connection.execute(
            "UPDATE sqlite_master SET sql = ? WHERE name = 'search_shadow'",
            (table_sql.replace("trigram remove_diacritics 1", "missing_tokenizer"),),
        )
        connection.execute(f"PRAGMA schema_version = {schema_version + 1}")
        connection.execute("PRAGMA writable_schema = OFF")

    repaired = memory_module.repair_portable_shadow(database_path)
    restored = MemoryClient.local(database_path)

    assert repaired is True
    assert restored.get_entity("incident", "INC-204")["body"] == {
        "status": "investigating"
    }


def test_incident_memory_repairs_the_restored_shadow_before_writes(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "incompatible-snapshot.db"
    client = MemoryClient.local(snapshot_path)
    client.storage.close()

    with sqlite3.connect(snapshot_path) as connection:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'search_shadow'"
        ).fetchone()[0]
        schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
        connection.execute("PRAGMA writable_schema = ON")
        connection.execute(
            "UPDATE sqlite_master SET sql = ? WHERE name = 'search_shadow'",
            (table_sql.replace("trigram remove_diacritics 1", "missing_tokenizer"),),
        )
        connection.execute(f"PRAGMA schema_version = {schema_version + 1}")
        connection.execute("PRAGMA writable_schema = OFF")

    memory = IncidentMemory(
        tmp_path / "host-runtime.db",
        snapshot_store=FileSnapshotStore(snapshot_path),
    )
    memory.client.set_entity("probe", "host", {"portable": True})

    assert memory.client.get_entity("probe", "host")["body"] == {"portable": True}

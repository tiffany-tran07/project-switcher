import json
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Callable, Generator
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import restore
from app.config import settings
from app.library import get_session
from app.main import app

pytest_plugins = ("test_library", "test_exports")


@pytest.fixture
def backup_archive(export_client: TestClient, snapshot: dict[str, Any], tmp_path: Path) -> Path:
    client = export_client
    version = snapshot["approved"]
    client.post(f"/api/v1/resume-versions/{version['id']}/export", json={})
    resume = client.get(f"/api/v1/resumes/{version['resume_id']}").json()
    client.post(
        "/api/v1/applications",
        json={
            "job_id": resume["job_id"],
            "resume_version_id": version["id"],
            "notes": "Keep application history",
        },
    )
    attachment = settings.resolved_data_dir / "attachments" / "source.txt"
    attachment.write_text("Verified source attachment")
    response = client.post("/api/v1/backup/export", json={"acknowledge_personal_data": True})
    assert response.status_code == 200
    archive = tmp_path / "backup.zip"
    archive.write_bytes(response.content)
    return archive


def rewritten(
    archive: Path,
    files: dict[str, bytes | None],
    *,
    refresh_checksums: bool = False,
) -> Path:
    with ZipFile(archive) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    entries.update({name: value for name, value in files.items() if value is not None})
    for name, value in files.items():
        if value is None:
            entries.pop(name, None)
    if refresh_checksums:
        manifest = json.loads(entries["manifest.json"])
        manifest["files"] = [
            {"path": name, "size": len(content), "sha256": sha256(content).hexdigest()}
            for name, content in entries.items()
            if name != "manifest.json"
        ]
        entries["manifest.json"] = json.dumps(manifest).encode()
    target = archive.with_name("modified.zip")
    with ZipFile(target, "w", ZIP_DEFLATED) as output:
        for name, content in entries.items():
            output.writestr(name, content)
    return target


def modified_database(archive: Path, update: Callable[[sqlite3.Connection], None]) -> Path:
    path = archive.with_name("modified.sqlite3")
    with ZipFile(archive) as source:
        path.write_bytes(source.read("database.sqlite3"))
    with closing(sqlite3.connect(path)) as database:
        update(database)
        database.commit()
    return rewritten(archive, {"database.sqlite3": path.read_bytes()}, refresh_checksums=True)


def test_restore_round_trip_into_clean_installation(
    backup_archive: Path,
    export_client: TestClient,
    snapshot: dict[str, Any],
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path_factory.mktemp("restored") / "data"
    original = export_client.get("/api/v1/applications").json()
    manifest = restore.restore_backup(backup_archive, destination)
    assert manifest.database_revision == restore.trusted_schema()[0]
    assert (destination / "attachments" / "source.txt").read_text() == "Verified source attachment"
    assert (destination / "resume.db").is_file()
    assert not (destination / "database.sqlite3").exists()
    assert export_client.get("/api/v1/applications").json() == original
    assert (
        export_client.get(f"/api/v1/resume-versions/{snapshot['approved']['id']}").json()
        == snapshot["approved"]
    )
    engine = create_engine(
        f"sqlite:///{destination / 'resume.db'}", connect_args={"check_same_thread": False}
    )
    sessions = sessionmaker(bind=engine)

    def restored_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, restored_session)
    monkeypatch.setattr(settings, "data_dir", destination)
    try:
        assert export_client.get("/api/v1/applications").json() == original
        assert export_client.get("/api/v1/profile").json()["name"] == "Saved Name"
        assert export_client.get("/api/v1/library/search?q=Python").json()
        version_id = snapshot["approved"]["id"]
        exports = export_client.get(f"/api/v1/resume-versions/{version_id}/exports").json()
        assert len(exports) == 1
        assert export_client.get(f"/api/v1/exports/{exports[0]['id']}/download").status_code == 200
        assert (
            export_client.get(f"/api/v1/resume-versions/{version_id}").json()
            == snapshot["approved"]
        )
        assert (
            export_client.patch(
                f"/api/v1/applications/{original[0]['id']}", json={"status": "applied"}
            ).status_code
            == 200
        )
    finally:
        engine.dispose()


def test_check_only_and_existing_destinations_are_non_destructive(
    backup_archive: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    parent = tmp_path_factory.mktemp("restore-safe")
    existing = parent / "existing"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("Keep me")
    before = backup_archive.read_bytes()
    assert restore.restore_backup(backup_archive).files
    with pytest.raises(restore.RestoreError, match="new directory"):
        restore.restore_backup(backup_archive, existing)
    with pytest.raises(restore.RestoreError, match="active data directory"):
        restore.restore_backup(backup_archive, settings.resolved_data_dir / "new-child")
    link = parent / "linked"
    link.symlink_to(existing, target_is_directory=True)
    with pytest.raises(restore.RestoreError):
        restore.restore_backup(backup_archive, link / "child")
    assert marker.read_text() == "Keep me"
    assert backup_archive.read_bytes() == before


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/tmp/escape",
        "attachments/../escape",
        "attachments\\escape",
        "exports/C:escape",
        ".env",
    ],
)
def test_restore_rejects_unsafe_archive_paths(backup_archive: Path, name: str) -> None:
    corrupted = rewritten(backup_archive, {name: b"unsafe"}, refresh_checksums=True)
    with pytest.raises(restore.RestoreError, match="path"):
        restore.restore_backup(corrupted)


def test_restore_rejects_checksum_missing_extra_and_case_collisions(backup_archive: Path) -> None:
    for changes, refresh in [
        ({"attachments/source.txt": b"changed"}, False),
        ({"attachments/source.txt": None}, False),
        ({"attachments/extra.txt": b"extra"}, False),
        ({"attachments/SOURCE.txt": b"collision"}, True),
    ]:
        with pytest.raises(restore.RestoreError):
            restore.restore_backup(rewritten(backup_archive, changes, refresh_checksums=refresh))


def test_restore_rejects_symlinks_and_duplicate_zip_members(backup_archive: Path) -> None:
    for symlink in (True, False):
        target = backup_archive.with_name("unsafe.zip")
        with ZipFile(backup_archive) as source, ZipFile(target, "w") as output:
            for item in source.infolist():
                output.writestr(item, source.read(item))
            info = ZipInfo("attachments/link" if symlink else "attachments/source.txt")
            if symlink:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                output.writestr(info, "/private/file")
            else:
                with pytest.warns(UserWarning, match="Duplicate name"):
                    output.writestr(info, "duplicate")
        with pytest.raises(restore.RestoreError, match="duplicate, encrypted, or non-regular"):
            restore.restore_backup(target)


def test_restore_rejects_incompatible_revision_and_modified_integrity_triggers(
    backup_archive: Path,
) -> None:
    with ZipFile(backup_archive) as source:
        manifest = json.loads(source.read("manifest.json"))
    manifest["database_revision"] = "unsupported"
    with pytest.raises(restore.RestoreError, match="incompatible"):
        restore.restore_backup(
            rewritten(backup_archive, {"manifest.json": json.dumps(manifest).encode()})
        )
    for sql in (
        "DROP TRIGGER resume_versions_immutable_update",
        "CREATE TABLE unexpected (value TEXT)",
        "CREATE TABLE sqliteevil (value TEXT)",
    ):
        modified = modified_database(backup_archive, lambda db: db.execute(sql))
        with pytest.raises(restore.RestoreError, match="trusted migrations"):
            restore.restore_backup(modified)


def test_restore_rejects_invalid_references(backup_archive: Path) -> None:
    modified = modified_database(
        backup_archive, lambda db: db.execute("UPDATE export_files SET version_id = 'missing'")
    )
    with pytest.raises(restore.RestoreError, match="foreign-key"):
        restore.restore_backup(modified)
    modified = modified_database(
        backup_archive,
        lambda db: db.execute(
            "UPDATE export_files SET checksum = ?",
            ("0" * 64,),
        ),
    )
    with pytest.raises(restore.RestoreError, match="checksum"):
        restore.restore_backup(modified)


def test_invalid_restore_never_creates_destination(
    backup_archive: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path_factory.mktemp("restore-invalid") / "data"
    bad = rewritten(backup_archive, {"attachments/source.txt": b"changed"})
    with pytest.raises(restore.RestoreError):
        restore.restore_backup(bad, destination)
    assert not destination.exists()
    monkeypatch.setattr(restore, "MAX_BACKUP_BYTES", 10)
    with pytest.raises(restore.RestoreError, match="size limit"):
        restore.restore_backup(backup_archive, destination)
    assert not destination.exists()


def test_restore_rejects_forged_snapshot_wording(backup_archive: Path) -> None:
    def forge(database: sqlite3.Connection) -> None:
        trigger = database.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'resume_bullets_immutable_update'"
        ).fetchone()[0]
        database.execute("DROP TRIGGER resume_bullets_immutable_update")
        database.execute("UPDATE resume_bullets SET text = 'Invented Kubernetes achievement'")
        database.execute(trigger)

    modified = modified_database(backup_archive, forge)
    with pytest.raises(restore.RestoreError, match="verified snapshot source"):
        restore.restore_backup(modified)


def test_restore_rejects_invalid_manifest_and_file_directory_conflicts(
    backup_archive: Path,
) -> None:
    with ZipFile(backup_archive) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    broken = {**manifest, "files": [*manifest["files"], manifest["files"][0]]}
    with pytest.raises(restore.RestoreError):
        restore.restore_backup(
            rewritten(backup_archive, {"manifest.json": json.dumps(broken).encode()})
        )
    with pytest.raises(restore.RestoreError, match="duplicate JSON keys"):
        restore.restore_backup(
            rewritten(backup_archive, {"manifest.json": b'{"format": "a", "format": "b"}'})
        )
    with pytest.raises(restore.RestoreError):
        restore.restore_backup(rewritten(backup_archive, {"manifest.json": None}))
    with pytest.raises(restore.RestoreError, match="conflict"):
        restore.restore_backup(
            rewritten(
                backup_archive,
                {"attachments/source.txt/child": b"child"},
                refresh_checksums=True,
            )
        )
    with pytest.raises(restore.RestoreError):
        restore.restore_backup(
            rewritten(
                backup_archive,
                {"database.sqlite3": b"Not a database"},
                refresh_checksums=True,
            )
        )


def test_failed_copy_removes_only_new_destination(
    backup_archive: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path_factory.mktemp("restore-copy-failure") / "new-data"

    def fail(*_: object, **__: object) -> None:
        raise OSError("Disk full")

    monkeypatch.setattr(restore.shutil, "copyfile", fail)
    with pytest.raises(restore.RestoreError):
        restore.restore_backup(backup_archive, destination)
    assert not destination.exists()
    assert backup_archive.is_file()


def test_restore_cli_check_only(backup_archive: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.restore", str(backup_archive), "--check-only"],
        cwd=restore.BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "validated"
    assert json.loads(result.stdout)["destination"] is None

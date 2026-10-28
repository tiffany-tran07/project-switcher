import json
import sqlite3
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app import backups
from app.config import settings

pytest_plugins = ("test_library", "test_exports")

ACK = {"acknowledge_personal_data": True}


def test_backup_contains_consistent_database_files_and_manifest(
    export_client: TestClient,
    snapshot: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = export_client
    version = snapshot["approved"]
    artifact = client.post(f"/api/v1/resume-versions/{version['id']}/export", json={}).json()
    resume = client.get(f"/api/v1/resumes/{version['resume_id']}").json()
    application = client.post(
        "/api/v1/applications",
        json={
            "job_id": resume["job_id"],
            "resume_version_id": version["id"],
            "notes": "Private application notes",
        },
    ).json()
    attachment = settings.resolved_data_dir / "attachments" / "notes" / "source.txt"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"Private evidence attachment")
    (settings.resolved_data_dir / ".env").write_text("SECRET=must-not-be-exported")
    (settings.resolved_data_dir / "exports" / "unregistered.docx").write_bytes(b"orphan")
    created_directories: list[Path] = []

    def temporary(prefix: str) -> TemporaryDirectory[str]:
        folder = TemporaryDirectory(prefix=prefix, dir=tmp_path)
        created_directories.append(Path(folder.name))
        return folder

    monkeypatch.setattr(backups, "TemporaryDirectory", temporary)
    response = client.post("/api/v1/backup/export", json=ACK)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "resume-backup.zip" in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "resume-tailor-backup"
        assert manifest["format_version"] == 1
        assert manifest["database_revision"]
        assert "not encrypted" in manifest["privacy"]
        files = {entry["path"]: entry for entry in manifest["files"]}
        assert set(archive.namelist()) == {"manifest.json", *files}
        assert set(files) == {
            "database.sqlite3",
            "attachments/notes/source.txt",
            f"exports/{artifact['id']}.docx",
        }
        for name, entry in files.items():
            content = archive.read(name)
            assert entry["size"] == len(content)
            assert entry["sha256"] == sha256(content).hexdigest()
        restored = tmp_path / "inspect-snapshot.sqlite3"
        restored.write_bytes(archive.read("database.sqlite3"))
    with sqlite3.connect(restored) as database:
        assert database.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            database.execute(
                "SELECT resume_version_id FROM applications WHERE id = ?", (application["id"],)
            ).fetchone()[0]
            == version["id"]
        )
        assert database.execute("SELECT COUNT(*) FROM application_events").fetchone()[0] == 1
        assert database.execute("SELECT name FROM profile").fetchone()[0] == "Saved Name"
        assert (
            database.execute(
                "SELECT COUNT(*) FROM library_fts WHERE library_fts MATCH 'Python'"
            ).fetchone()[0]
            > 0
        )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute("UPDATE resume_versions SET template = 'unsafe'")
    assert all(not folder.exists() for folder in created_directories)
    assert client.get(f"/api/v1/resume-versions/{version['id']}").json() == version


def test_backup_requires_explicit_privacy_acknowledgement(export_client: TestClient) -> None:
    assert export_client.post("/api/v1/backup/export", json={}).status_code == 422
    assert (
        export_client.post(
            "/api/v1/backup/export", json={"acknowledge_personal_data": False}
        ).status_code
        == 422
    )


def test_backup_rejects_missing_or_corrupt_registered_export(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    artifact = export_client.post(
        f"/api/v1/resume-versions/{snapshot['approved']['id']}/export", json={}
    ).json()
    path = settings.resolved_data_dir / "exports" / f"{artifact['id']}.docx"
    original = path.read_bytes()
    path.write_bytes(b"corrupted")
    assert export_client.post("/api/v1/backup/export", json=ACK).status_code == 409
    path.unlink()
    assert export_client.post("/api/v1/backup/export", json=ACK).status_code == 409
    path.write_bytes(original)
    assert export_client.post("/api/v1/backup/export", json=ACK).status_code == 200


def test_backup_rejects_symlinks_and_invalid_paths(
    export_client: TestClient, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("Do not include")
    link = settings.resolved_data_dir / "attachments" / "link.txt"
    link.symlink_to(outside)
    assert export_client.post("/api/v1/backup/export", json=ACK).status_code == 409
    from fastapi import HTTPException

    for value in (
        "../outside.txt",
        "/tmp/outside.txt",
        "exports/../outside.txt",
        "exports\\outside.txt",
    ):
        with pytest.raises(HTTPException):
            backups.safe_asset_path(value, "exports")


def test_backup_limits_and_failure_cleanup(
    export_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backups,
        "TemporaryDirectory",
        lambda prefix: TemporaryDirectory(prefix=prefix, dir=tmp_path),
    )
    monkeypatch.setattr(backups, "MAX_BACKUP_BYTES", 10)
    assert export_client.post("/api/v1/backup/export", json=ACK).status_code == 413
    assert list(tmp_path.glob("resume-backup-*")) == []
    monkeypatch.setattr(backups, "MAX_BACKUP_BYTES", 256 * 1024 * 1024)
    monkeypatch.setattr(backups, "MAX_BACKUP_FILES", 1)
    (settings.resolved_data_dir / "attachments" / "one.txt").write_text("one")
    assert export_client.post("/api/v1/backup/export", json=ACK).status_code == 413
    assert list(tmp_path.glob("resume-backup-*")) == []

import os
import sqlite3
from contextlib import closing
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_restore import modified_database, rewritten

from app import attachments, restore
from app.config import settings

pytest_plugins = ("test_library", "test_exports")
CONTENT = b"Benchmark: 30% faster Python reports.\nReviewed locally.\n"


def upload(
    client: TestClient,
    snapshot: dict[str, Any],
    content: bytes = CONTENT,
    filename: str = "benchmark.txt",
) -> Any:
    return client.post(
        f"/api/v1/evidence/{snapshot['evidence']['id']}/attachments",
        params={"filename": filename},
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    )


def test_upload_demotes_evidence_clears_approvals_and_preserves_versions(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    path = f"/api/v1/evidence/{snapshot['evidence']['id']}"
    bullet = client.post(
        f"{path}/bullets", json={"text": snapshot["evidence"]["claim"], "approved": True}
    ).json()
    response = upload(client, snapshot)
    assert response.status_code == 201
    source = response.json()
    assert "relative_path" not in source
    assert source["checksum"] == sha256(CONTENT).hexdigest()
    assert source["size"] == len(CONTENT)
    assert (
        settings.resolved_data_dir / "attachments" / f"{source['id']}.txt"
    ).stat().st_mode & 0o777 == 0o600
    current = client.get(path).json()
    assert current["state"] == "draft"
    assert current["verified_at"] is None
    assert current["bullet_variants"][0]["id"] == bullet["id"]
    assert current["bullet_variants"][0]["approved_at"] is None
    assert (
        client.get(f"/api/v1/resume-versions/{snapshot['approved']['id']}").json()
        == snapshot["approved"]
    )
    assert client.get(f"{path}/attachments").json()[0]["id"] == source["id"]
    assert client.get("/api/v1/library/export").json()["attachments"][0]["id"] == source["id"]
    download = client.get(f"/api/v1/attachments/{source['id']}/download")
    assert download.content == CONTENT
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "no-store"
    assert upload(client, snapshot, filename="renamed.txt").status_code == 409
    assert len(client.get(f"{path}/attachments").json()) == 1


@pytest.mark.parametrize(
    "content,status",
    [
        (b"", 422),
        (b" \n\t", 422),
        (b"\xff", 422),
        (b"nul\0byte", 422),
        (b"x" * (1024 * 1024 + 1), 413),
    ],
)
def test_invalid_text_does_not_change_evidence_or_write_files(
    export_client: TestClient, snapshot: dict[str, Any], content: bytes, status: int
) -> None:
    assert upload(export_client, snapshot, content).status_code == status
    assert (
        export_client.get(f"/api/v1/evidence/{snapshot['evidence']['id']}").json()["state"]
        == "verified"
    )
    assert list((settings.resolved_data_dir / "attachments").iterdir()) == []


@pytest.mark.parametrize(
    "filename",
    ["../source.txt", "/source.txt", "a\\source.txt", "source.txt\n", "source.pdf", "source.docx"],
)
def test_invalid_names_are_rejected(
    export_client: TestClient, snapshot: dict[str, Any], filename: str
) -> None:
    assert upload(export_client, snapshot, filename=filename).status_code == 422
    assert list((settings.resolved_data_dir / "attachments").iterdir()) == []


def test_utf8_bom_plain_delivery_and_exact_size_limit(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    for content in (
        b"\xef\xbb\xbf" + "Reviewed café\n".encode(),
        b"<script>not executed</script>",
        b"x" * (1024 * 1024),
    ):
        response = upload(export_client, snapshot, content, filename="測定 log.TXT")
        assert response.status_code == 201
        source = response.json()
        assert source["original_name"] == "測定 log.TXT"
        download = export_client.get(f"/api/v1/attachments/{source['id']}/download")
        assert download.content == content
        assert download.headers["content-type"].startswith("text/plain")
        assert source["checksum"] == sha256(content).hexdigest()


def test_simple_content_types_and_archived_sources_cannot_upload(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    path = f"/api/v1/evidence/{snapshot['evidence']['id']}"
    assert (
        client.post(
            f"{path}/attachments?filename=source.txt",
            content=CONTENT,
            headers={"Content-Type": "text/plain"},
        ).status_code
        == 415
    )
    client.patch(path, json={"archived": True})
    assert upload(client, snapshot).status_code == 422
    assert client.get(f"{path}/attachments").json() == []
    client.patch(path, json={"archived": False})
    client.patch(
        f"/api/v1/experiences/{snapshot['evidence']['experience_id']}", json={"archived": True}
    )
    assert upload(client, snapshot).status_code == 422


def test_storage_and_commit_failures_do_not_remove_existing_files_or_demote_evidence(
    export_client: TestClient, snapshot: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = export_client
    source = upload(client, snapshot).json()
    path = settings.resolved_data_dir / "attachments" / f"{source['id']}.txt"
    client.patch(f"/api/v1/evidence/{snapshot['evidence']['id']}", json={"state": "verified"})
    client.post(
        f"/api/v1/evidence/{snapshot['evidence']['id']}/bullets",
        json={"text": snapshot["evidence"]["claim"], "approved": True},
    )
    with monkeypatch.context() as patch:
        patch.setattr(attachments, "new_id", lambda: source["id"])
        assert upload(client, snapshot, b"Different source").status_code == 409
    assert path.read_bytes() == CONTENT
    with monkeypatch.context() as patch:

        def fail(_: Session) -> None:
            raise SQLAlchemyError("simulated commit failure")

        patch.setattr(Session, "commit", fail)
        assert upload(client, snapshot, b"Another source").status_code == 409
    assert list(path.parent.iterdir()) == [path]
    current = client.get(f"/api/v1/evidence/{snapshot['evidence']['id']}").json()
    assert current["state"] == "verified"
    assert current["bullet_variants"][0]["approved_at"] is not None


def test_download_refuses_damaged_missing_symlink_and_special_files(
    export_client: TestClient, snapshot: dict[str, Any], tmp_path: Path
) -> None:
    client = export_client
    source = upload(client, snapshot).json()
    path = settings.resolved_data_dir / "attachments" / f"{source['id']}.txt"
    url = f"/api/v1/attachments/{source['id']}/download"
    path.write_bytes(b"Changed proof")
    assert client.get(url).status_code == 409
    path.unlink()
    assert client.get(url).status_code == 404
    outside = tmp_path / "outside.txt"
    outside.write_bytes(CONTENT)
    path.symlink_to(outside)
    assert client.get(url).status_code == 409
    path.unlink()
    os.mkfifo(path)
    assert client.get(url).status_code == 409
    assert outside.read_bytes() == CONTENT


def test_upload_refuses_symlink_directory(
    export_client: TestClient, snapshot: dict[str, Any], tmp_path: Path
) -> None:
    root = settings.resolved_data_dir / "attachments"
    root.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)
    assert upload(export_client, snapshot).status_code == 409
    assert list(outside.iterdir()) == []


def test_new_snapshots_capture_sources_and_check_actual_files(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    source = upload(client, snapshot).json()
    evidence_id = snapshot["evidence"]["id"]
    url = f"/api/v1/resumes/{snapshot['approved']['resume_id']}/draft"
    body = {"evidence_ids": [evidence_id], "approve": True}
    assert client.post(url, json=body).status_code == 422
    client.patch(f"/api/v1/evidence/{evidence_id}", json={"state": "verified"})
    version = client.post(url, json=body).json()
    expected = {
        key: source[key] for key in ("id", "original_name", "media_type", "checksum", "size")
    }
    assert version["bullets"][0]["evidence_snapshot"]["attachments"] == [expected]
    artifact = client.post(f"/api/v1/resume-versions/{version['id']}/export", json={}).json()
    docx = client.get(f"/api/v1/exports/{artifact['id']}/download").content
    with ZipFile(BytesIO(docx)) as document:
        xml = document.read("word/document.xml")
        assert b"benchmark.txt" not in xml
        assert b"Benchmark:" not in xml
    path = settings.resolved_data_dir / "attachments" / f"{source['id']}.txt"
    path.write_bytes(b"Changed source")
    assert client.post(url, json=body).status_code == 422
    assert client.get(f"/api/v1/resume-versions/{version['id']}").json() == version
    assert (
        client.post("/api/v1/backup/export", json={"acknowledge_personal_data": True}).status_code
        == 409
    )


def test_backup_restore_checks_registry_files_and_snapshot_references(
    export_client: TestClient,
    snapshot: dict[str, Any],
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    client = export_client
    source = upload(client, snapshot).json()
    client.patch(f"/api/v1/evidence/{snapshot['evidence']['id']}", json={"state": "verified"})
    client.post(
        f"/api/v1/resumes/{snapshot['approved']['resume_id']}/draft",
        json={"evidence_ids": [snapshot["evidence"]["id"]], "approve": True},
    )
    archive = tmp_path / "backup.zip"
    archive.write_bytes(
        client.post("/api/v1/backup/export", json={"acknowledge_personal_data": True}).content
    )
    restore_root = tmp_path_factory.mktemp("attachment-restores")
    destination = restore_root / "restored"
    restore.restore_backup(archive, destination)
    relative = f"attachments/{source['id']}.txt"
    assert (destination / relative).read_bytes() == CONTENT
    with closing(sqlite3.connect(destination / "resume.db")) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE attachments SET original_name = ?", ("tampered.txt",))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM attachments")
    missing = rewritten(archive, {relative: None}, refresh_checksums=True)
    with pytest.raises(restore.RestoreError, match="Registered source"):
        restore.restore_backup(missing, restore_root / "missing")
    changed = b"New proof supplied offline"

    def change_registry(db: sqlite3.Connection) -> None:
        trigger = db.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'attachments_no_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER attachments_no_update")
        db.execute(
            "UPDATE attachments SET checksum = ?, size = ?",
            (sha256(changed).hexdigest(), len(changed)),
        )
        db.execute(trigger)

    modified = modified_database(archive, change_registry)
    modified = rewritten(modified, {relative: changed}, refresh_checksums=True)
    with pytest.raises(restore.RestoreError, match="Snapshot attachment"):
        restore.restore_backup(modified, restore_root / "inconsistent")

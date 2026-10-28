"""Portable local backup export. Restore is intentionally not enabled yet."""

import json
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.config import settings
from app.library import get_session
from app.models import utc_now

router = APIRouter(prefix="/api/v1/backup", tags=["backup"])
MAX_BACKUP_BYTES = 256 * 1024 * 1024
MAX_BACKUP_FILES = 2000


class BackupRequest(BaseModel):
    acknowledge_personal_data: Literal[True]


def safe_asset_path(relative: str, prefix: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or "\x00" in relative
        or pure.is_absolute()
        or ".." in pure.parts
        or str(pure) != relative
        or len(pure.parts) < 2
        or pure.parts[0] != prefix
    ):
        raise HTTPException(409, "Backup contains an invalid asset path")
    path = settings.resolved_data_dir / relative
    if path.resolve() != path or not path.is_file():
        raise HTTPException(409, "Backup asset is missing or uses a symbolic link")
    return path


def attachment_paths() -> list[tuple[str, Path]]:
    root = settings.resolved_data_dir / "attachments"
    if root.is_symlink():
        raise HTTPException(409, "Symbolic links in attachments cannot be backed up")
    if not root.exists():
        return []
    if not root.is_dir():
        raise HTTPException(409, "Attachments path is not a directory")
    assets = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise HTTPException(409, "Symbolic links in attachments cannot be backed up")
        if path.is_dir():
            continue
        relative = path.relative_to(settings.resolved_data_dir).as_posix()
        assets.append((relative, safe_asset_path(relative, "attachments")))
        if len(assets) > MAX_BACKUP_FILES:
            raise HTTPException(413, "Backup exceeds the file count limit")
    return sorted(assets)


def build_backup(session: Session, temporary: Path) -> Path:
    source = session.connection().connection.driver_connection
    if not isinstance(source, sqlite3.Connection):
        raise HTTPException(422, "Portable backup currently supports SQLite only")
    estimated_size = (
        source.execute("PRAGMA page_count").fetchone()[0]
        * source.execute("PRAGMA page_size").fetchone()[0]
    )
    if estimated_size > MAX_BACKUP_BYTES:
        raise HTTPException(413, "Backup exceeds the 256 MB size limit")
    database = temporary / "database.sqlite3"
    with closing(sqlite3.connect(database)) as snapshot:
        source.backup(snapshot)
        if snapshot.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise HTTPException(409, "Database integrity check failed; backup was not created")
        if snapshot.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise HTTPException(409, "Database has invalid references; backup was not created")
        revision = snapshot.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        exports = snapshot.execute(
            "SELECT relative_path, checksum FROM export_files ORDER BY relative_path"
        ).fetchall()
    assets: list[tuple[str, Path, str | None]] = [("database.sqlite3", database, None)]
    assets.extend((name, path, None) for name, path in attachment_paths())
    for relative, checksum in exports:
        assets.append((relative, safe_asset_path(relative, "exports"), checksum))
    if len(assets) > MAX_BACKUP_FILES:
        raise HTTPException(413, "Backup exceeds the file count limit")
    if len({name for name, _, _ in assets}) != len(assets):
        raise HTTPException(409, "Backup contains duplicate asset paths")
    archive_path = temporary / "resume-backup.zip"
    total = 0
    files = []
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for relative, path, expected_checksum in assets:
            digest = sha256()
            size = 0
            with path.open("rb") as source_file, archive.open(relative, "w") as target:
                while chunk := source_file.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if total > MAX_BACKUP_BYTES:
                        raise HTTPException(413, "Backup exceeds the 256 MB size limit")
                    target.write(chunk)
                    digest.update(chunk)
            checksum = digest.hexdigest()
            if expected_checksum is not None and checksum != expected_checksum:
                raise HTTPException(
                    409, "Export checksum failed; repair the original export file before backup"
                )
            files.append({"path": relative, "size": size, "sha256": checksum})
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "resume-tailor-backup",
                    "format_version": 1,
                    "created_at": utc_now().isoformat(),
                    "database_revision": revision,
                    "database": "database.sqlite3",
                    "files": files,
                    "privacy": "Contains personal data. This backup is not encrypted.",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return archive_path


@router.post("/export")
def export_backup(
    data: BackupRequest,
    session: Session = Depends(get_session),
) -> FileResponse:
    temporary = TemporaryDirectory(prefix="resume-backup-")
    try:
        archive = build_backup(session, Path(temporary.name))
    except HTTPException:
        temporary.cleanup()
        raise
    except (OSError, sqlite3.Error) as exc:
        temporary.cleanup()
        raise HTTPException(
            503, "Could not read local data for backup; no backup was created"
        ) from exc
    return FileResponse(
        archive,
        media_type="application/zip",
        filename="resume-backup.zip",
        background=BackgroundTask(temporary.cleanup),
    )

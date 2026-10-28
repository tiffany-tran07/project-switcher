"""Validate portable backups and restore only into a new, inactive data directory.

Run from backend: python -m app.restore backup.zip --destination /new/data/path
"""

import argparse
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import unicodedata
import zlib
from contextlib import closing
from functools import lru_cache
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.backups import MAX_BACKUP_BYTES, MAX_BACKUP_FILES, MAX_MANIFEST_BYTES
from app.config import settings
from app.documents import Content
from app.resumes import safe_wording

BACKEND = Path(__file__).resolve().parents[1]


class RestoreError(ValueError):
    pass


class BackupFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    size: int = Field(ge=0, le=MAX_BACKUP_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BackupManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format: Literal["resume-tailor-backup"]
    format_version: Literal[1]
    created_at: str = Field(max_length=100)
    database_revision: str = Field(min_length=1, max_length=100)
    database: Literal["database.sqlite3"]
    privacy: str = Field(max_length=1000)
    files: list[BackupFile] = Field(min_length=1, max_length=MAX_BACKUP_FILES)


def archive_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or ":" in name
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != name
        or len(name) > 1000
        or (
            name not in {"manifest.json", "database.sqlite3"}
            and (len(path.parts) < 2 or path.parts[0] not in {"attachments", "exports"})
        )
    ):
        raise RestoreError("Archive contains an unsafe or unsupported path")
    return name


def schema_signature(database: sqlite3.Connection) -> tuple[tuple[str, ...], ...]:
    return tuple(
        sorted(
            (kind, name, table, " ".join((sql or "").split()))
            for kind, name, table, sql in database.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE substr(name, 1, 7) != 'sqlite_'"
            )
        )
    )


@lru_cache(maxsize=1)
def trusted_schema() -> tuple[str, tuple[tuple[str, ...], ...]]:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    revision = ScriptDirectory.from_config(config).get_current_head()
    if revision is None:
        raise RestoreError("No supported database revision found")
    # Build a reference from our own migrations, never from SQL in the archive.
    with TemporaryDirectory(prefix="resume-schema-") as temporary:
        path = Path(temporary) / "reference.db"
        environment = {**os.environ, "DATABASE_URL": f"sqlite:///{path}", "DATA_DIR": temporary}
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(BACKEND / "alembic.ini"),
                "upgrade",
                "head",
            ],
            cwd=BACKEND,
            env=environment,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RestoreError("Could not build a trusted database schema for validation")
        with closing(sqlite3.connect(path)) as database:
            return revision, schema_signature(database)


def validate_database(path: Path, manifest: BackupManifest) -> None:
    revision, signature = trusted_schema()
    if manifest.database_revision != revision:
        raise RestoreError(
            "Backup schema version is incompatible with this app; use the matching app version"
        )
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)) as database:
        database.execute("PRAGMA trusted_schema=OFF")
        started = time.monotonic()
        database.set_progress_handler(lambda: int(time.monotonic() - started > 15), 1000)
        if schema_signature(database) != signature:
            raise RestoreError(
                "Database schema or integrity triggers do not match trusted migrations"
            )
        if database.execute("SELECT version_num FROM alembic_version").fetchall() != [(revision,)]:
            raise RestoreError("Database revision does not match the manifest")
        if database.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RestoreError("Database integrity check failed")
        if database.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RestoreError("Database contains invalid foreign-key references")
        if database.execute(
            "SELECT 1 FROM applications a JOIN resume_versions v ON v.id = a.resume_version_id "
            "JOIN resumes r ON r.id = v.resume_id "
            "WHERE v.approved_at IS NULL OR v.sealed != 1 OR a.job_id != r.job_id LIMIT 1"
        ).fetchone():
            raise RestoreError(
                "Application links do not point to approved versions for the same job"
            )
        files = {entry.path: entry for entry in manifest.files}
        registered: set[str] = set()
        for relative, checksum, format in database.execute(
            "SELECT relative_path, checksum, format FROM export_files"
        ):
            archive_name(relative)
            if (
                not relative.startswith("exports/")
                or format not in {"docx", "pdf"}
                or not relative.endswith(f".{format}")
                or relative not in files
                or files[relative].sha256 != checksum
            ):
                raise RestoreError("Registered export is missing or does not match its checksum")
            registered.add(relative)
        if {name for name in files if name.startswith("exports/")} != registered:
            raise RestoreError("Archive contains unregistered export files")
        for version_id, content, sealed in database.execute(
            "SELECT id, content, sealed FROM resume_versions"
        ):
            if sealed != 1:
                raise RestoreError("Backup contains an unsealed resume snapshot")
            document = Content.model_validate_json(content)
            expected = [id for section in document.sections for id in section.evidence_ids]
            bullets = database.execute(
                "SELECT evidence_id, text, evidence_snapshot FROM resume_bullets "
                "WHERE version_id = ? ORDER BY position",
                (version_id,),
            ).fetchall()
            if (
                not expected
                or len(set(expected)) != len(expected)
                or [row[0] for row in bullets] != expected
            ):
                raise RestoreError("Resume section and evidence links are inconsistent")
            for _, text, raw_source in bullets:
                source = json.loads(raw_source)
                if (
                    not isinstance(source, dict)
                    or not source.get("verified_at")
                    or not isinstance(source.get("source_note"), str)
                    or not source["source_note"].strip()
                    or not isinstance(source.get("claim"), str)
                    or not safe_wording(source["claim"], text)
                ):
                    raise RestoreError(
                        "Resume bullet is not backed by its verified snapshot source"
                    )


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RestoreError("Manifest contains duplicate JSON keys")
        result[key] = value
    return result


def validate_archive(archive_path: Path, staging: Path) -> BackupManifest:
    if archive_path.stat().st_size > MAX_BACKUP_BYTES + MAX_MANIFEST_BYTES:
        raise RestoreError("Backup exceeds the archive size limit")
    with ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_BACKUP_FILES + 1:
            raise RestoreError("Backup exceeds the file count limit")
        names: set[str] = set()
        normalized: set[str] = set()
        for entry in entries:
            name = archive_name(entry.filename)
            collision = unicodedata.normalize("NFC", name).casefold()
            file_type = stat.S_IFMT(entry.external_attr >> 16)
            if (
                name in names
                or collision in normalized
                or entry.is_dir()
                or file_type not in {0, stat.S_IFREG}
                or entry.flag_bits & 1
                or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
            ):
                raise RestoreError("Archive has duplicate, encrypted, or non-regular entries")
            names.add(name)
            normalized.add(collision)
        if "manifest.json" not in names:
            raise RestoreError("Backup manifest is missing")
        if archive.getinfo("manifest.json").file_size > MAX_MANIFEST_BYTES:
            raise RestoreError("Backup manifest is too large")
        manifest = BackupManifest.model_validate(
            json.loads(
                archive.read("manifest.json"),
                object_pairs_hook=unique_keys,
            )
        )
        files = {entry.path: entry for entry in manifest.files}
        if len(files) != len(manifest.files) or "database.sqlite3" not in files:
            raise RestoreError("Manifest contains duplicate paths or no database")
        if names != {"manifest.json", *files}:
            raise RestoreError("Manifest and archive file lists do not match")
        for name in files:
            if any(
                unicodedata.normalize("NFC", parent.as_posix()).casefold() in normalized
                for parent in PurePosixPath(name).parents
                if str(parent) != "."
            ):
                raise RestoreError("Archive file paths conflict with directory paths")
        if sum(entry.size for entry in manifest.files) > MAX_BACKUP_BYTES:
            raise RestoreError("Backup exceeds the uncompressed size limit")
        for name, record in files.items():
            info = archive.getinfo(name)
            if info.file_size != record.size:
                raise RestoreError("Manifest size does not match an archive entry")
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = sha256()
            size = 0
            with archive.open(info) as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > record.size:
                        raise RestoreError("Archive entry exceeds its declared size")
                    digest.update(chunk)
                    output.write(chunk)
            if size != record.size or digest.hexdigest() != record.sha256:
                raise RestoreError("Backup file checksum verification failed")
    validate_database(staging / "database.sqlite3", manifest)
    return manifest


def restore_backup(archive_path: Path, destination: Path | None = None) -> BackupManifest:
    destination = destination.expanduser().absolute() if destination is not None else None
    if destination is not None:
        if destination.exists() or destination.is_symlink():
            raise RestoreError(
                "Destination must be a new directory; existing data will not be overwritten"
            )
        if destination.resolve() != destination:
            raise RestoreError("Destination cannot contain symbolic links or parent traversal")
        if destination.is_relative_to(settings.resolved_data_dir):
            raise RestoreError("Destination cannot be inside the active data directory")
        if not destination.parent.is_dir():
            raise RestoreError("Destination parent directory must already exist")
    try:
        with TemporaryDirectory(prefix="resume-restore-") as temporary:
            staging = Path(temporary)
            manifest = validate_archive(archive_path.expanduser().resolve(), staging)
            if destination is not None:
                # Reserve a brand new directory only after every validation has passed.
                destination.mkdir(mode=0o700)
                try:
                    for name in ("attachments", "exports"):
                        source = staging / name
                        if source.exists():
                            shutil.copytree(source, destination / name)
                        else:
                            (destination / name).mkdir()
                    shutil.copyfile(staging / "database.sqlite3", destination / "resume.db")
                except BaseException:
                    shutil.rmtree(destination)
                    raise
            return manifest
    except RestoreError:
        raise
    except (
        OSError,
        sqlite3.Error,
        BadZipFile,
        ValidationError,
        json.JSONDecodeError,
        UnicodeError,
        RuntimeError,
        zlib.error,
        subprocess.TimeoutExpired,
    ) as exc:
        raise RestoreError(
            "Backup could not be validated or restored; active data was not changed"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a backup or restore into a new data directory."
    )
    parser.add_argument("archive", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--destination", type=Path, help="New, nonexistent data directory")
    group.add_argument("--check-only", action="store_true", help="Validate without restoring")
    args = parser.parse_args()
    try:
        manifest = restore_backup(args.archive, args.destination)
    except RestoreError as exc:
        parser.exit(2, f"Restore refused: {exc}\n")
    print(
        json.dumps(
            {
                "status": "validated" if args.check_only else "restored",
                "files": len(manifest.files),
                "database_revision": manifest.database_revision,
                "destination": str(args.destination.resolve()) if args.destination else None,
                "next_step": "Stop API; set DATA_DIR to restored path; clear DATABASE_URL; restart."
                if args.destination
                else "Active data was not changed.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

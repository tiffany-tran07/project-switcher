"""Bounded, local-only supporting text files. No extraction, execution, or AI calls."""

import os
import stat
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.library import demote, get_session, require, validate_context
from app.models import Attachment, EvidenceItem, new_id
from app.schemas import AttachmentOut

router = APIRouter(prefix="/api/v1", tags=["attachments"])
MAX_ATTACHMENT_BYTES = 1024 * 1024


def validate_filename(filename: str) -> None:
    if (
        "/" in filename
        or "\\" in filename
        or any(unicodedata.category(char).startswith("C") for char in filename)
        or PurePosixPath(filename).suffix.casefold() != ".txt"
    ):
        raise HTTPException(422, "Choose a plain UTF-8 .txt filename, not a filesystem path")


@contextmanager
def attachment_directory() -> Iterator[int]:
    # Pin the directory inode and reject symlinks, including during file creation/read.
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise HTTPException(
            503, "Source storage requires POSIX no-follow file support (macOS/Linux)"
        )
    try:
        directory = os.open(
            settings.resolved_data_dir / "attachments", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        raise HTTPException(
            409, "Attachment directory is missing, unavailable, or a symbolic link"
        ) from exc
    try:
        yield directory
    finally:
        os.close(directory)


def create_attachment(
    session: Session, evidence_id: str, filename: str, content: bytes
) -> AttachmentOut:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Source file must be UTF-8 text") from exc
    if not text.strip() or any(
        unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in text
    ):
        raise HTTPException(422, "Source file is empty or contains unsupported control characters")
    item: EvidenceItem = require(session, EvidenceItem, evidence_id)
    if item.archived_at:
        raise HTTPException(422, "Restore archived evidence before attaching a source")
    validate_context(session, item.experience_id, item.project_id)
    checksum = sha256(content).hexdigest()
    if session.scalar(
        select(Attachment.id).where(
            Attachment.evidence_id == evidence_id, Attachment.checksum == checksum
        )
    ):
        raise HTTPException(409, "This source file is already attached; refresh the source list")
    id = new_id()
    basename = f"{id}.txt"
    row = Attachment(
        id=id,
        evidence_id=evidence_id,
        relative_path=f"attachments/{basename}",
        original_name=filename,
        media_type="text/plain",
        checksum=checksum,
        size=len(content),
    )
    with attachment_directory() as directory:
        created = False
        try:
            descriptor = os.open(
                basename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            created = True
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            demote(item)
            session.add(row)
            session.flush()
            session.refresh(row)
            result = AttachmentOut.model_validate(row)
            session.commit()
        except (OSError, SQLAlchemyError) as exc:
            session.rollback()
            if created:
                os.unlink(basename, dir_fd=directory)
            raise HTTPException(
                409, "Source was not saved; check local storage and refresh before retrying"
            ) from exc
        return result


@router.get("/evidence/{evidence_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(evidence_id: str, session: Session = Depends(get_session)) -> list[Attachment]:
    require(session, EvidenceItem, evidence_id)
    return list(
        session.scalars(
            select(Attachment)
            .where(Attachment.evidence_id == evidence_id)
            .order_by(Attachment.created_at)
        )
    )


@router.post("/evidence/{evidence_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    request: Request,
    evidence_id: str,
    filename: str = Query(min_length=1, max_length=255),
    session: Session = Depends(get_session),
) -> AttachmentOut:
    if (
        request.headers.get("content-type", "").split(";")[0].strip().lower()
        != "application/octet-stream"
    ):
        raise HTTPException(415, "Send the raw text file as application/octet-stream")
    validate_filename(filename)
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(413, "Source file exceeds the 1 MB limit")
        content.extend(chunk)
    if not content:
        raise HTTPException(422, "Source file is empty")
    return await run_in_threadpool(
        create_attachment, session, evidence_id, filename, bytes(content)
    )


def read_attachment(row: Attachment) -> bytes:
    try:
        valid_id = str(UUID(row.id)) == row.id
    except ValueError:
        valid_id = False
    if (
        not valid_id
        or row.relative_path != f"attachments/{row.id}.txt"
        or row.media_type != "text/plain"
    ):
        raise HTTPException(409, "Invalid registered source path or type")
    with attachment_directory() as directory:
        try:
            descriptor = os.open(
                f"{row.id}.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise HTTPException(409, "Source is not a regular file")
                content = source.read(MAX_ATTACHMENT_BYTES + 1)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Source file is missing") from exc
        except OSError as exc:
            raise HTTPException(409, "Source file is unavailable or uses a symbolic link") from exc
    if len(content) != row.size or sha256(content).hexdigest() != row.checksum:
        raise HTTPException(409, "Source checksum failed; repair the original file")
    return content


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: str, session: Session = Depends(get_session)) -> Response:
    row: Attachment = require(session, Attachment, attachment_id)
    return Response(
        read_attachment(row),
        media_type="text/plain",
        headers={
            "Content-Disposition": 'attachment; filename="evidence-source.txt"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )

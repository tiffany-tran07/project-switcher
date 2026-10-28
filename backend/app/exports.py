"""Local, checksummed exports of approved immutable resume versions."""

from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.documents import render_docx
from app.library import get_session
from app.models import ExportFile, ResumeVersion, new_id
from app.schemas import ExportFileOut, ExportRequest, ResumeVersionOut

router = APIRouter(prefix="/api/v1", tags=["exports"])
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def export_path(relative_path: str) -> Path:
    root = settings.resolved_data_dir
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root / "exports"):
        raise HTTPException(409, "Invalid export path")
    return path


@router.post("/resume-versions/{version_id}/export", response_model=ExportFileOut, status_code=201)
def create_export(
    version_id: str, data: ExportRequest, session: Session = Depends(get_session)
) -> ExportFile:
    version = session.scalar(
        select(ResumeVersion)
        .options(selectinload(ResumeVersion.bullets))
        .where(ResumeVersion.id == version_id)
    )
    if version is None:
        raise HTTPException(404, "Resume version not found")
    if version.approved_at is None or not version.sealed:
        raise HTTPException(422, "Only approved, sealed snapshots can be exported")
    try:
        content, extracted = render_docx(ResumeVersionOut.model_validate(version))
    except ValueError as exc:
        raise HTTPException(422, "Snapshot could not be rendered with text preserved") from exc
    export_id = new_id()
    relative = f"exports/{export_id}.docx"
    path = export_path(relative)
    row = ExportFile(
        id=export_id,
        version_id=version_id,
        format=data.format,
        relative_path=relative,
        checksum=sha256(content).hexdigest(),
        extracted_text=extracted,
    )
    created_file = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            created_file = True
            target.write(content)
        session.add(row)
        session.commit()
    except (OSError, SQLAlchemyError) as exc:
        session.rollback()
        if created_file:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # An unregistered file may remain, but it is never downloadable by ID.
        raise HTTPException(503, "Could not save the local export; please retry") from exc
    session.refresh(row)
    return row


@router.get("/resume-versions/{version_id}/exports", response_model=list[ExportFileOut])
def list_exports(version_id: str, session: Session = Depends(get_session)) -> list[ExportFile]:
    if session.get(ResumeVersion, version_id) is None:
        raise HTTPException(404, "Resume version not found")
    return list(
        session.scalars(
            select(ExportFile)
            .where(ExportFile.version_id == version_id)
            .order_by(ExportFile.created_at.desc())
        )
    )


def read_export(row: ExportFile) -> bytes:
    path = export_path(row.relative_path)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise HTTPException(404, "Export file is unavailable; generate it again") from exc
    if sha256(content).hexdigest() != row.checksum:
        raise HTTPException(409, "Export checksum failed; generate it again")
    return content


@router.get("/exports/{export_id}/download")
def download_export(export_id: str, session: Session = Depends(get_session)) -> Response:
    row = session.get(ExportFile, export_id)
    if row is None:
        raise HTTPException(404, "Export not found")
    return Response(
        content=read_export(row),
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="resume.docx"'},
    )

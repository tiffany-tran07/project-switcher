"""Application tracking anchored to one approved immutable resume snapshot."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.library import commit, get_session
from app.models import Application, ApplicationEvent, Job, ResumeVersion, utc_now
from app.schemas import (
    ApplicationCreate,
    ApplicationEventCreate,
    ApplicationOut,
    ApplicationPatch,
    ApplicationStatus,
)

router = APIRouter(prefix="/api/v1", tags=["applications"])


def require_application(session: Session, application_id: str) -> Application:
    row = session.scalar(
        select(Application)
        .options(selectinload(Application.events))
        .where(Application.id == application_id)
    )
    if row is None:
        raise HTTPException(404, "Application not found")
    return row


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(
    status: ApplicationStatus | None = None,
    session: Session = Depends(get_session),
) -> list[Application]:
    query = (
        select(Application)
        .options(selectinload(Application.events))
        .order_by(Application.created_at.desc())
    )
    if status is not None:
        query = query.where(Application.status == status)
    return list(session.scalars(query))


@router.post("/applications", response_model=ApplicationOut, status_code=201)
def create_application(
    data: ApplicationCreate, session: Session = Depends(get_session)
) -> Application:
    job = session.get(Job, data.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    version = session.get(ResumeVersion, data.resume_version_id)
    if version is None:
        raise HTTPException(404, "Resume version not found")
    if not version.sealed or version.approved_at is None:
        raise HTTPException(422, "An application requires an approved resume snapshot")
    if version.resume.job_id != job.id:
        raise HTTPException(422, "Resume version belongs to a different job")
    row = Application(
        **data.model_dump(exclude={"applied_date"}),
        applied_date=data.applied_date or (utc_now().date() if data.status == "applied" else None),
        company=job.company,
        title=job.title,
        url=job.url,
    )
    row.events = [
        ApplicationEvent(
            event_type="created",
            status=data.status,
            note="Application record created; no external submission performed.",
        )
    ]
    session.add(row)
    commit(session)
    session.refresh(row)
    return row


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: str, session: Session = Depends(get_session)) -> Application:
    return require_application(session, application_id)


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def patch_application(
    application_id: str,
    data: ApplicationPatch,
    session: Session = Depends(get_session),
) -> Application:
    row = require_application(session, application_id)
    previous = row.status
    values = data.model_dump(exclude_unset=True, exclude={"event_note"})
    changed = any(getattr(row, key) != value for key, value in values.items())
    for key, value in values.items():
        setattr(row, key, value)
    if row.status == "applied" and previous != "applied" and row.applied_date is None:
        if "applied_date" not in data.model_fields_set:
            row.applied_date = utc_now().date()
    if changed or data.event_note.strip():
        row.events.append(
            ApplicationEvent(
                event_type="status_changed"
                if row.status != previous
                else "updated"
                if changed
                else "note",
                previous_status=previous if row.status != previous else None,
                status=row.status if row.status != previous else None,
                note=data.event_note.strip()
                or (
                    "Status updated." if row.status != previous else "Application details updated."
                ),
            )
        )
        row.updated_at = utc_now()
    commit(session)
    session.refresh(row)
    return row


@router.post(
    "/applications/{application_id}/events", response_model=ApplicationOut, status_code=201
)
def add_event(
    application_id: str,
    data: ApplicationEventCreate,
    session: Session = Depends(get_session),
) -> Application:
    row = require_application(session, application_id)
    if not data.note.strip():
        raise HTTPException(422, "Event note cannot be empty")
    row.events.append(ApplicationEvent(event_type="note", note=data.note.strip()))
    row.updated_at = utc_now()
    commit(session)
    session.refresh(row)
    return row

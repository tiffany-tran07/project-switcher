"""Read-only overview of the core workflow, using current UTC dates for follow-ups."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.library import get_session
from app.models import Application, EvidenceItem, Job, Project, Resume, utc_now
from app.resumes import usable

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


class DashboardCounts(BaseModel):
    jobs: int
    resumes: int
    applications: int
    ready_evidence: int
    evidence_needing_review: int
    follow_ups_due: int


class RecentJob(BaseModel):
    id: str
    company: str
    title: str


class RecentResume(BaseModel):
    id: str
    name: str
    latest_version: int | None
    latest_approved_version: int | None


class ApplicationSummary(BaseModel):
    id: str
    company: str
    title: str
    status: str
    follow_up_date: date | None


class EvidenceReview(BaseModel):
    id: str
    claim: str
    reason: str


class DashboardOut(BaseModel):
    today_utc: date
    counts: DashboardCounts
    recent_jobs: list[RecentJob]
    recent_resumes: list[RecentResume]
    recent_applications: list[ApplicationSummary]
    due_follow_ups: list[ApplicationSummary]
    evidence_needing_review: list[EvidenceReview]


def application_summary(row: Application) -> ApplicationSummary:
    return ApplicationSummary(
        id=row.id,
        company=row.company,
        title=row.title,
        status=row.status,
        follow_up_date=row.follow_up_date,
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(session: Session = Depends(get_session)) -> DashboardOut:
    today = utc_now().date()
    evidence = session.scalars(
        select(EvidenceItem)
        .options(
            selectinload(EvidenceItem.experience),
            selectinload(EvidenceItem.project).selectinload(Project.experience),
        )
        .where(EvidenceItem.archived_at.is_(None))
        .order_by(EvidenceItem.updated_at.desc())
    ).all()
    ready = sum(1 for row in evidence if usable(row))
    review = [row for row in evidence if row.state != "rejected" and not usable(row)]
    due_query = select(Application).where(
        Application.archived_at.is_(None),
        Application.follow_up_date <= today,
        Application.status.not_in(["rejected", "withdrawn"]),
    )
    due_count = session.scalar(select(func.count()).select_from(due_query.subquery())) or 0

    def count(model: type[Job] | type[Resume] | type[Application]) -> int:
        return (
            session.scalar(
                select(func.count()).select_from(model).where(model.archived_at.is_(None))
            )
            or 0
        )

    jobs = session.scalars(
        select(Job)
        .where(Job.archived_at.is_(None))
        .order_by(Job.created_at.desc(), Job.id)
        .limit(5)
    ).all()
    resumes = session.scalars(
        select(Resume)
        .options(selectinload(Resume.versions))
        .where(Resume.archived_at.is_(None))
        .order_by(Resume.updated_at.desc(), Resume.id)
        .limit(5)
    ).all()
    applications = session.scalars(
        select(Application)
        .where(Application.archived_at.is_(None))
        .order_by(Application.updated_at.desc(), Application.id)
        .limit(5)
    ).all()
    due = session.scalars(
        due_query.order_by(Application.follow_up_date, Application.id).limit(5)
    ).all()
    return DashboardOut(
        today_utc=today,
        counts=DashboardCounts(
            jobs=count(Job),
            resumes=count(Resume),
            applications=count(Application),
            ready_evidence=ready,
            evidence_needing_review=len(review),
            follow_ups_due=due_count,
        ),
        recent_jobs=[RecentJob(id=row.id, company=row.company, title=row.title) for row in jobs],
        recent_resumes=[
            RecentResume(
                id=row.id,
                name=row.name,
                latest_version=max((v.version_number for v in row.versions), default=None),
                latest_approved_version=max(
                    (v.version_number for v in row.versions if v.approved_at), default=None
                ),
            )
            for row in resumes
        ],
        recent_applications=[application_summary(row) for row in applications],
        due_follow_ups=[application_summary(row) for row in due],
        evidence_needing_review=[
            EvidenceReview(
                id=row.id,
                claim=row.claim,
                reason="Missing source note"
                if not row.source_note.strip()
                else "Linked source unavailable or verification incomplete"
                if row.state == "verified"
                else "Needs verification",
            )
            for row in review[:5]
        ],
    )

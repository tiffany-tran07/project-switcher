"""Immutable, source-backed resume snapshots with conservative wording edits."""

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.attachments import read_attachment
from app.library import get_session
from app.models import (
    EvidenceItem,
    Job,
    Profile,
    Project,
    Resume,
    ResumeBullet,
    ResumeVersion,
    utc_now,
)
from app.schemas import (
    DraftRequest,
    DraftValidationIssue,
    DraftValidationOut,
    ResumeCreate,
    ResumeEvidenceStatus,
    ResumeOut,
    ResumeVersionOut,
)

router = APIRouter(prefix="/api/v1", tags=["resumes"])


def evidence_snapshot(item: EvidenceItem) -> dict[str, object]:
    """Capture source context at drafting time; later library changes cannot affect it."""
    experience = item.experience or (item.project.experience if item.project else None)
    return {
        "claim": item.claim,
        "source_note": item.source_note,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        "experience": {
            "organization": experience.organization,
            "title": experience.title,
            "start_date": experience.start_date.isoformat() if experience.start_date else None,
            "end_date": experience.end_date.isoformat() if experience.end_date else None,
            "location": experience.location,
        }
        if experience
        else None,
        "project": {
            "name": item.project.name,
            "summary": item.project.summary,
            "start_date": item.project.start_date.isoformat() if item.project.start_date else None,
            "end_date": item.project.end_date.isoformat() if item.project.end_date else None,
            "url": item.project.url,
        }
        if item.project
        else None,
        "metrics": [
            {
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "context": metric.context,
                "source_note": metric.source_note,
            }
            for metric in item.metrics
        ],
        "skills": [skill.name for skill in item.skills if skill.archived_at is None],
        "attachments": [
            {
                "id": source.id,
                "original_name": source.original_name,
                "checksum": source.checksum,
                "size": source.size,
                "media_type": source.media_type,
            }
            for source in item.attachments
        ],
    }


# Keep signs, comparators, currency, technical punctuation, and ownership words.
# We do not have a semantic proof that deleting arbitrary "filler" is harmless.
WORDING_TOKEN = re.compile(
    r"[+\-−]?\d+(?:[.,/\-–]\d+)*(?:\s*[%‰‱])?"
    r"|\.?[^\W_]+(?:[.#/_\-][^\W_]+|[+#]+)*"
    r"|[^\s]",
    re.IGNORECASE,
)
FIRST_PERSON_AUXILIARIES = {"am", "was", "were", "have", "has", "had", "been"}


def wording_tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFC", value).strip()
    # A single sentence-ending full stop is optional, not a technology's leading dot.
    if value.endswith(".") and not value.endswith(".."):
        value = value[:-1]
    return WORDING_TOKEN.findall(value.casefold())


def safe_wording(claim: str, proposed: str) -> bool:
    source = wording_tokens(claim)
    target = wording_tokens(proposed)
    if not source or not target:
        return False
    if source == target:
        return True
    if source[0] != "i":
        return False
    # Resume style may omit a leading "I" (and its leading auxiliaries), but
    # cannot remove internal articles, technology names, or qualifications.
    prefix = 1
    while True:
        if source[prefix:] == target:
            return True
        if prefix >= len(source) or source[prefix] not in FIRST_PERSON_AUXILIARIES:
            return False
        prefix += 1


def usable(item: EvidenceItem | None) -> bool:
    return bool(
        item
        and item.state == "verified"
        and item.verified_at
        and item.source_note.strip()
        and not item.archived_at
        and (not item.experience or not item.experience.archived_at)
        and (
            not item.project
            or (
                not item.project.archived_at
                and (not item.project.experience or not item.project.experience.archived_at)
            )
        )
    )


def source_problem(item: EvidenceItem | None) -> str | None:
    """The same source checks power availability previews and final draft validation."""
    if not usable(item):
        return "Source is missing, archived, or no longer verified."
    assert item is not None
    try:
        for source in item.attachments:
            read_attachment(source)
    except HTTPException:
        return "An attached source file is missing or damaged. Repair it before drafting."
    return None


@router.get("/resume-evidence", response_model=list[ResumeEvidenceStatus])
def resume_evidence(
    response: Response, session: Session = Depends(get_session)
) -> list[ResumeEvidenceStatus]:
    response.headers["Cache-Control"] = "no-store"
    items = session.scalars(
        select(EvidenceItem)
        .options(
            selectinload(EvidenceItem.experience),
            selectinload(EvidenceItem.project).selectinload(Project.experience),
            selectinload(EvidenceItem.attachments),
        )
        .where(EvidenceItem.archived_at.is_(None))
        .order_by(EvidenceItem.created_at.desc())
    )
    statuses = []
    for item in items:
        problem = source_problem(item)
        statuses.append(
            ResumeEvidenceStatus(evidence_id=item.id, eligible=problem is None, problem=problem)
        )
    return statuses


@router.get("/evidence/{evidence_id}/resume-wordings", response_model=list[str])
def resume_wordings(evidence_id: str, session: Session = Depends(get_session)) -> list[str]:
    item = session.scalar(
        select(EvidenceItem)
        .options(
            selectinload(EvidenceItem.experience),
            selectinload(EvidenceItem.project).selectinload(Project.experience),
            selectinload(EvidenceItem.bullet_variants),
        )
        .where(EvidenceItem.id == evidence_id)
    )
    if not usable(item):
        raise HTTPException(422, "Only active verified evidence has resume wordings")
    assert item is not None
    wordings = [item.claim]
    for variant in item.bullet_variants:
        if variant.approved_at and safe_wording(item.claim, variant.text):
            if variant.text not in wordings:
                wordings.append(variant.text)
    return wordings


@router.get("/resumes", response_model=list[ResumeOut])
def list_resumes(session: Session = Depends(get_session)) -> list[Resume]:
    return list(session.scalars(select(Resume).order_by(Resume.created_at.desc())))


@router.post("/resumes", response_model=ResumeOut, status_code=201)
def create_resume(data: ResumeCreate, session: Session = Depends(get_session)) -> Resume:
    if session.get(Job, data.job_id) is None:
        raise HTTPException(404, "Job not found")
    if not data.name.strip():
        raise HTTPException(422, "Resume name cannot be empty")
    row = Resume(job_id=data.job_id, name=data.name.strip())
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.get("/resumes/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: str, session: Session = Depends(get_session)) -> Resume:
    row = session.get(Resume, resume_id)
    if row is None:
        raise HTTPException(404, "Resume not found")
    return row


@router.get("/resumes/{resume_id}/versions", response_model=list[ResumeVersionOut])
def list_versions(resume_id: str, session: Session = Depends(get_session)) -> list[ResumeVersion]:
    if session.get(Resume, resume_id) is None:
        raise HTTPException(404, "Resume not found")
    return list(
        session.scalars(
            select(ResumeVersion)
            .options(selectinload(ResumeVersion.bullets))
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.version_number)
        )
    )


Sections = list[tuple[str, list[tuple[str, str | None]]]]


def draft_sections(data: DraftRequest) -> Sections:
    return (
        [
            (section.heading, [(bullet.evidence_id, bullet.text) for bullet in section.bullets])
            for section in data.sections
        ]
        if data.sections is not None
        else [("Selected evidence", [(id, None) for id in data.evidence_ids])]
    )


def validate_draft(
    sections: Sections, session: Session
) -> tuple[list[EvidenceItem], DraftValidationOut]:
    evidence: list[EvidenceItem] = []
    issues: list[DraftValidationIssue] = []
    seen: set[str] = set()
    entries = [(heading, id, text) for heading, bullets in sections for id, text in bullets]
    for position, (heading, evidence_id, proposed) in enumerate(entries):

        def issue(code: str, message: str) -> None:
            issues.append(
                DraftValidationIssue.model_validate(
                    {
                        "evidence_id": evidence_id,
                        "position": position,
                        "code": code,
                        "message": message,
                    }
                )
            )

        if evidence_id in seen:
            issue("duplicate", "This evidence is selected more than once.")
        seen.add(evidence_id)
        item = session.scalar(
            select(EvidenceItem)
            .options(
                selectinload(EvidenceItem.experience),
                selectinload(EvidenceItem.project).selectinload(Project.experience),
                selectinload(EvidenceItem.metrics),
                selectinload(EvidenceItem.attachments),
                selectinload(EvidenceItem.skills),
            )
            .where(EvidenceItem.id == evidence_id)
        )
        problem = source_problem(item)
        if problem:
            issue("unavailable_evidence", problem)
            continue
        assert item is not None
        if heading == "Projects" and not item.project:
            issue("section_context", "Project bullets must link to a project.")
        if heading == "Experience" and not (
            item.experience or (item.project and item.project.experience)
        ):
            issue("section_context", "Experience bullets must link to an experience.")
        if proposed is not None and not safe_wording(item.claim, proposed):
            issue("unsafe_wording", "Preserve the source words, order, tools, dates, and metrics.")
        evidence.append(item)
    return evidence, DraftValidationOut(valid=not issues, issues=issues)


@router.post("/resumes/{resume_id}/validate", response_model=DraftValidationOut)
def check_draft(
    resume_id: str, data: DraftRequest, session: Session = Depends(get_session)
) -> DraftValidationOut:
    if session.get(Resume, resume_id) is None:
        raise HTTPException(404, "Resume not found")
    _, report = validate_draft(draft_sections(data), session)
    return report


@router.post("/resumes/{resume_id}/draft", response_model=ResumeVersionOut, status_code=201)
def draft_resume(
    resume_id: str, data: DraftRequest, session: Session = Depends(get_session)
) -> ResumeVersion:
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "Resume not found")
    sections = draft_sections(data)
    choices = [entry for _, bullets in sections for entry in bullets]
    evidence, report = validate_draft(sections, session)
    if not report.valid:
        raise HTTPException(422, "; ".join(issue.message for issue in report.issues))
    profile = session.get(Profile, 1)
    profile_snapshot = (
        {
            "name": profile.name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "links": list(profile.links),
        }
        if profile
        else {}
    )
    number = (
        session.scalar(
            select(func.max(ResumeVersion.version_number)).where(
                ResumeVersion.resume_id == resume_id
            )
        )
        or 0
    ) + 1
    version = ResumeVersion(
        resume_id=resume_id,
        version_number=number,
        content={
            "profile": profile_snapshot,
            "sections": [
                {"heading": heading, "evidence_ids": [id for id, _ in bullets]}
                for heading, bullets in sections
            ],
            "job": {"company": resume.job.company, "title": resume.job.title},
        },
        approved_at=utc_now() if data.approve else None,
    )
    version.bullets = [
        ResumeBullet(
            evidence_id=item.id,
            text=proposed if proposed is not None else item.claim,
            position=position,
            evidence_snapshot=evidence_snapshot(item),
        )
        for position, (item, (_, proposed)) in enumerate(zip(evidence, choices, strict=True))
    ]
    session.add(version)
    session.flush()  # Write all bullets before sealing the immutable snapshot.
    version.sealed = True
    resume.updated_at = utc_now()
    resume.status = "approved" if data.approve else "draft"
    session.commit()
    session.refresh(version)
    return version


@router.get("/resume-versions/{version_id}", response_model=ResumeVersionOut)
def get_version(version_id: str, session: Session = Depends(get_session)) -> ResumeVersion:
    row = session.scalar(
        select(ResumeVersion)
        .options(selectinload(ResumeVersion.bullets))
        .where(ResumeVersion.id == version_id)
    )
    if row is None:
        raise HTTPException(404, "Resume version not found")
    return row

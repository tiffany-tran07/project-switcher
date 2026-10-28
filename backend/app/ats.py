"""Conservative DOCX readiness checks, not an employer score prediction."""

import re
from io import BytesIO
from zipfile import BadZipFile

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.documents import document_lines
from app.exports import read_export
from app.library import get_session
from app.models import EvidenceItem, ExportFile, JobRequirement, Project, ResumeVersion, Skill
from app.resumes import usable
from app.schemas import (
    AtsReportOut,
    AtsRequest,
    AtsRequirementOut,
    FormattingCheck,
    ResumeVersionOut,
)

router = APIRouter(prefix="/api/v1", tags=["ATS readiness"])


def words(value: str) -> list[str]:
    tokens = re.findall(r"[^\W_]+(?:[.][^\W_]+|[+#]+)*", value.casefold())
    return [
        token[:-3] + "y"
        if len(token) > 5 and token.endswith("ies")
        else token[:-1]
        if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us"))
        else token
        for token in tokens
    ]


def contains(text: str, term: str) -> bool:
    target = words(term)
    tokens = words(text)
    if not target:
        return False
    for index in range(len(tokens) - len(target) + 1):
        if tokens[index : index + len(target)] == target:
            if not set(tokens[max(0, index - 3) : index]) & {
                "not",
                "no",
                "never",
                "without",
                "lack",
                "lacking",
            }:
                return True
    return False


def aliases_for(term: str, skills: list[Skill]) -> list[str]:
    matches = [
        [skill.name, *(alias.alias for alias in skill.aliases)]
        for skill in skills
        if any(
            words(value) == words(term) for value in [skill.name, *(a.alias for a in skill.aliases)]
        )
    ]
    # Ambiguous aliases are not proof of equivalence.
    return matches[0] if len(matches) == 1 else [term]


def requirement_result(
    req: JobRequirement,
    text: str,
    candidates: list[tuple[str, str, list[str]]],
    skills: list[Skill],
) -> AtsRequirementOut:
    terms = aliases_for(req.text, skills)
    supported = [
        id
        for id, claim, tags in candidates
        if any(
            contains(claim, term) or any(words(tag) == words(term) for tag in tags)
            for term in terms
        )
    ]
    if not supported:
        status = "no_verified_evidence"
        reason = "No direct verified source found; related concepts are not treated as proof."
    elif any(contains(line, req.text) for line in text.splitlines()):
        status = "present_exact"
        reason = "Requirement wording is present after case, punctuation, and plural normalization."
    elif any(contains(line, term) for line in text.splitlines() for term in terms):
        status = "present_alias"
        reason = "A configured, unambiguous skill alias appears in the exported text."
    else:
        status = "supported_but_missing_from_resume"
        reason = "Direct verified support exists, but its wording is absent from the exported text."
    return AtsRequirementOut.model_validate(
        {
            "requirement_id": req.id,
            "text": req.text,
            "status": status,
            "evidence_ids": list(dict.fromkeys(supported)),
            "reason": reason,
        }
    )


@router.post("/resume-versions/{version_id}/ats", response_model=AtsReportOut)
def analyze_export(
    version_id: str,
    data: AtsRequest,
    session: Session = Depends(get_session),
) -> AtsReportOut:
    version = session.scalar(
        select(ResumeVersion)
        .options(selectinload(ResumeVersion.bullets))
        .where(ResumeVersion.id == version_id)
    )
    if version is None:
        raise HTTPException(404, "Resume version not found")
    artifact = session.get(ExportFile, data.export_id)
    if artifact is None or artifact.version_id != version_id:
        raise HTTPException(404, "Export not found for this resume version")
    if artifact.format != "docx":
        raise HTTPException(422, "Only DOCX analysis is currently supported")
    content = read_export(artifact)
    try:
        document = Document(BytesIO(content))
    except (ValueError, KeyError, BadZipFile) as exc:
        raise HTTPException(422, "Could not extract DOCX text") from exc
    extracted = "\n".join(paragraph.text for paragraph in document.paragraphs)
    skills = list(
        session.scalars(
            select(Skill).options(selectinload(Skill.aliases)).where(Skill.archived_at.is_(None))
        )
    )
    library = session.scalars(
        select(EvidenceItem)
        .options(
            selectinload(EvidenceItem.skills),
            selectinload(EvidenceItem.experience),
            selectinload(EvidenceItem.project).selectinload(Project.experience),
        )
        .where(EvidenceItem.state == "verified", EvidenceItem.archived_at.is_(None))
    ).all()
    candidates = [
        (item.id, item.claim, [skill.name for skill in item.skills if not skill.archived_at])
        for item in library
        if usable(item)
    ]
    # Snapshot sources remain valid for historical resumes after the library changes.
    for bullet in version.bullets:
        source = bullet.evidence_snapshot
        tags = source.get("skills")
        if source.get("verified_at") and isinstance(source.get("claim"), str):
            candidates.append(
                (
                    bullet.evidence_id,
                    str(source["claim"]),
                    [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else [],
                )
            )
    requirements = session.scalars(
        select(JobRequirement)
        .where(
            JobRequirement.job_id == version.resume.job_id,
            JobRequirement.confirmed.is_(True),
        )
        .order_by(JobRequirement.position)
    ).all()
    expected = "\n".join(
        text for _, text in document_lines(ResumeVersionOut.model_validate(version))
    )
    checks = [
        FormattingCheck(
            name="text_order",
            status="passed" if expected == extracted else "warning",
            message="Compares contacts, headings, dates, and bullet order to the snapshot.",
        ),
        FormattingCheck(
            name="selectable_text",
            status="passed"
            if not document.tables and len(document.inline_shapes) == 0
            else "warning",
            message="Generated content is paragraph text, without tables or inline images.",
        ),
        FormattingCheck(
            name="characters",
            status="warning" if "\ufffd" in extracted else "passed",
            message="Checks for Unicode replacement characters; visually review other symbols.",
        ),
        FormattingCheck(
            name="page_target",
            status="not_checked",
            message="DOCX pagination needs a document renderer; page count is not checked.",
        ),
    ]
    return AtsReportOut(
        version_id=version_id,
        export_id=artifact.id,
        extracted_text=extracted,
        requirements=[
            requirement_result(req, extracted, candidates, skills) for req in requirements
        ],
        formatting=checks,
        notes=[
            "ATS readiness only, not a prediction of an employer score.",
            "Uses current user-confirmed requirements and configured skill aliases.",
            "Support includes verified snapshot sources and active verified library evidence.",
            "Related evidence needs human review and does not count as direct support.",
            "Text is re-extracted from the checksum-verified DOCX; PDF checks are pending.",
        ]
        + (
            []
            if requirements
            else ["No confirmed requirements; review and confirm them in Jobs first."]
        ),
    )

import re
from collections.abc import Generator
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    BulletVariant,
    EvidenceItem,
    Experience,
    Metric,
    Profile,
    Project,
    Skill,
    SkillAlias,
    utc_now,
)
from app.schemas import (
    BulletData,
    BulletOut,
    BulletPatch,
    EvidenceData,
    EvidenceOut,
    EvidencePatch,
    ExperienceData,
    ExperienceOut,
    ExperiencePatch,
    MetricData,
    MetricOut,
    MetricPatch,
    ProfileData,
    ProjectData,
    ProjectOut,
    ProjectPatch,
    SkillData,
    SkillOut,
    SkillPatch,
)

router = APIRouter(prefix="/api/v1", tags=["career library"])


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


DB = Session


def require(session: DB, model: type[Any], record_id: str) -> Any:
    row = session.get(model, record_id)
    if row is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


def commit(session: DB) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Record conflicts with an existing value") from exc


def check_dates(start: Any, end: Any) -> None:
    if start and end and end < start:
        raise HTTPException(422, "End date must be after start date")


def clean_required(value: str | None, field: str) -> str:
    if value is None or not value.strip():
        raise HTTPException(422, f"{field} cannot be empty")
    return value.strip()


def set_archive(row: Any, archived: bool | None) -> None:
    if archived is not None:
        row.archived_at = utc_now() if archived else None


def validate_experience(session: DB, record_id: str | None) -> Experience | None:
    if record_id is None:
        return None
    row: Experience = require(session, Experience, record_id)
    if row.archived_at:
        raise HTTPException(422, "Experience is archived")
    return row


def validate_project(session: DB, record_id: str | None) -> Project | None:
    if record_id is None:
        return None
    row: Project = require(session, Project, record_id)
    if row.archived_at:
        raise HTTPException(422, "Project is archived")
    if row.experience and row.experience.archived_at:
        raise HTTPException(422, "Project's experience is archived")
    return row


def validate_context(session: DB, experience_id: str | None, project_id: str | None) -> None:
    if not (experience_id or project_id):
        raise HTTPException(422, "Link evidence to an experience or project")
    experience = validate_experience(session, experience_id)
    project = validate_project(session, project_id)
    if experience and project and project.experience_id and project.experience_id != experience.id:
        raise HTTPException(422, "Project belongs to a different experience")


def validate_skills(session: DB, ids: list[str]) -> list[Skill]:
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Duplicate skill IDs")
    rows = [require(session, Skill, skill_id) for skill_id in ids]
    if any(row.archived_at for row in rows):
        raise HTTPException(422, "Archived skill cannot be linked")
    return rows


def demote(evidence: EvidenceItem) -> None:
    evidence.state = "draft"
    evidence.verified_at = None
    evidence.updated_at = utc_now()
    for bullet in evidence.bullet_variants:
        bullet.approved_at = None


def demote_for_context(session: DB, evidence_items: list[EvidenceItem]) -> None:
    for evidence in evidence_items:
        demote(evidence)


def evidence_out(row: EvidenceItem) -> EvidenceOut:
    return EvidenceOut.model_validate(
        {
            "id": row.id,
            "claim": row.claim,
            "source_note": row.source_note,
            "experience_id": row.experience_id,
            "project_id": row.project_id,
            "state": row.state,
            "verified_at": row.verified_at,
            "archived_at": row.archived_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "skill_ids": [skill.id for skill in row.skills],
            "metrics": row.metrics,
            "bullet_variants": row.bullet_variants,
        }
    )


def skill_out(row: Skill) -> SkillOut:
    return SkillOut.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "canonical_name": row.canonical_name,
            "category": row.category,
            "aliases": [alias.alias for alias in row.aliases],
            "archived_at": row.archived_at,
        }
    )


def canonical(value: str) -> str:
    return " ".join(value.casefold().split())


def set_aliases(row: Skill, aliases: list[str]) -> None:
    clean = [alias.strip() for alias in aliases]
    if canonical(row.name) in {canonical(alias) for alias in clean}:
        raise HTTPException(422, "An alias cannot equal the skill name")
    row.aliases = [SkillAlias(alias=alias) for alias in clean]


@router.get("/profile", response_model=ProfileData)
def get_profile(session: DB = Depends(get_session)) -> ProfileData:
    row = session.get(Profile, 1)
    return ProfileData.model_validate(row) if row else ProfileData()


@router.put("/profile", response_model=ProfileData)
def put_profile(data: ProfileData, session: DB = Depends(get_session)) -> ProfileData:
    row = session.get(Profile, 1) or Profile(id=1)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    session.add(row)
    commit(session)
    return ProfileData.model_validate(row)


@router.get("/experiences", response_model=list[ExperienceOut])
def list_experiences(
    include_archived: bool = False, session: DB = Depends(get_session)
) -> list[Experience]:
    query = select(Experience).order_by(Experience.start_date.desc(), Experience.created_at.desc())
    if not include_archived:
        query = query.where(Experience.archived_at.is_(None))
    return list(session.scalars(query))


@router.post("/experiences", response_model=ExperienceOut, status_code=201)
def create_experience(data: ExperienceData, session: DB = Depends(get_session)) -> Experience:
    row = Experience(**data.model_dump())
    row.organization = clean_required(row.organization, "Organization")
    row.title = clean_required(row.title, "Title")
    session.add(row)
    commit(session)
    session.refresh(row)
    return row


@router.get("/experiences/{record_id}", response_model=ExperienceOut)
def get_experience(record_id: str, session: DB = Depends(get_session)) -> Experience:
    return cast(Experience, require(session, Experience, record_id))


@router.patch("/experiences/{record_id}", response_model=ExperienceOut)
def patch_experience(
    record_id: str, data: ExperiencePatch, session: DB = Depends(get_session)
) -> Experience:
    row: Experience = require(session, Experience, record_id)
    values = data.model_dump(exclude_unset=True, exclude={"archived"})
    for field, value in values.items():
        setattr(row, field, value)
    row.organization = clean_required(row.organization, "Organization")
    row.title = clean_required(row.title, "Title")
    check_dates(row.start_date, row.end_date)
    set_archive(row, data.archived)
    if values:
        demote_for_context(session, row.evidence_items)
        for project in row.projects:
            demote_for_context(session, project.evidence_items)
    commit(session)
    session.refresh(row)
    return row


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    include_archived: bool = False, session: DB = Depends(get_session)
) -> list[Project]:
    query = select(Project).order_by(Project.created_at.desc())
    if not include_archived:
        query = query.where(Project.archived_at.is_(None))
    return list(session.scalars(query))


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectData, session: DB = Depends(get_session)) -> Project:
    validate_experience(session, data.experience_id)
    row = Project(**data.model_dump())
    row.name = clean_required(row.name, "Project name")
    session.add(row)
    commit(session)
    session.refresh(row)
    return row


@router.get("/projects/{record_id}", response_model=ProjectOut)
def get_project(record_id: str, session: DB = Depends(get_session)) -> Project:
    return cast(Project, require(session, Project, record_id))


@router.patch("/projects/{record_id}", response_model=ProjectOut)
def patch_project(
    record_id: str, data: ProjectPatch, session: DB = Depends(get_session)
) -> Project:
    row: Project = require(session, Project, record_id)
    values = data.model_dump(exclude_unset=True, exclude={"archived"})
    if "experience_id" in values:
        validate_experience(session, values["experience_id"])
    for field, value in values.items():
        setattr(row, field, value)
    row.name = clean_required(row.name, "Project name")
    check_dates(row.start_date, row.end_date)
    if row.experience_id:
        for evidence in row.evidence_items:
            if evidence.experience_id and evidence.experience_id != row.experience_id:
                raise HTTPException(422, "Project has evidence linked to a different experience")
    set_archive(row, data.archived)
    if values:
        demote_for_context(session, row.evidence_items)
    commit(session)
    session.refresh(row)
    return row


@router.get("/skills", response_model=list[SkillOut])
def list_skills(
    include_archived: bool = False, session: DB = Depends(get_session)
) -> list[SkillOut]:
    query = select(Skill).order_by(Skill.name)
    if not include_archived:
        query = query.where(Skill.archived_at.is_(None))
    return [skill_out(row) for row in session.scalars(query)]


@router.post("/skills", response_model=SkillOut, status_code=201)
def create_skill(data: SkillData, session: DB = Depends(get_session)) -> SkillOut:
    name = clean_required(data.name, "Skill name")
    row = Skill(name=name, canonical_name=canonical(name), category=data.category)
    set_aliases(row, data.aliases)
    session.add(row)
    commit(session)
    return skill_out(row)


@router.get("/skills/{record_id}", response_model=SkillOut)
def get_skill(record_id: str, session: DB = Depends(get_session)) -> SkillOut:
    return skill_out(require(session, Skill, record_id))


@router.patch("/skills/{record_id}", response_model=SkillOut)
def patch_skill(record_id: str, data: SkillPatch, session: DB = Depends(get_session)) -> SkillOut:
    row: Skill = require(session, Skill, record_id)
    values = data.model_dump(exclude_unset=True, exclude={"archived", "aliases"})
    if "name" in values:
        row.name = clean_required(values.pop("name"), "Skill name")
        row.canonical_name = canonical(row.name)
    for field, value in values.items():
        setattr(row, field, value)
    if data.aliases is not None:
        set_aliases(row, data.aliases)
    set_archive(row, data.archived)
    if data.name is not None:
        demote_for_context(session, row.evidence_items)
    commit(session)
    return skill_out(row)


@router.get("/evidence", response_model=list[EvidenceOut])
def list_evidence(
    include_archived: bool = False, session: DB = Depends(get_session)
) -> list[EvidenceOut]:
    query = select(EvidenceItem).order_by(EvidenceItem.created_at.desc())
    if not include_archived:
        query = query.where(EvidenceItem.archived_at.is_(None))
    return [evidence_out(row) for row in session.scalars(query)]


@router.post("/evidence", response_model=EvidenceOut, status_code=201)
def create_evidence(data: EvidenceData, session: DB = Depends(get_session)) -> EvidenceOut:
    validate_context(session, data.experience_id, data.project_id)
    skills = validate_skills(session, data.skill_ids)
    row = EvidenceItem(
        claim=clean_required(data.claim, "Claim"),
        source_note=data.source_note.strip(),
        experience_id=data.experience_id,
        project_id=data.project_id,
        skills=skills,
    )
    session.add(row)
    commit(session)
    return evidence_out(row)


@router.get("/evidence/{record_id}", response_model=EvidenceOut)
def get_evidence(record_id: str, session: DB = Depends(get_session)) -> EvidenceOut:
    return evidence_out(require(session, EvidenceItem, record_id))


@router.patch("/evidence/{record_id}", response_model=EvidenceOut)
def patch_evidence(
    record_id: str, data: EvidencePatch, session: DB = Depends(get_session)
) -> EvidenceOut:
    row: EvidenceItem = require(session, EvidenceItem, record_id)
    values = data.model_dump(exclude_unset=True, exclude={"archived", "skill_ids", "state"})
    material_change = bool(values) or data.skill_ids is not None
    for field, value in values.items():
        setattr(
            row,
            field,
            value.strip() if field in {"claim", "source_note"} and value is not None else value,
        )
    row.claim = clean_required(row.claim, "Claim")
    if row.source_note is None:
        raise HTTPException(422, "Source note cannot be null")
    validate_context(session, row.experience_id, row.project_id)
    if data.skill_ids is not None:
        row.skills = validate_skills(session, data.skill_ids)
    if material_change:
        demote(row)
    if data.state == "verified":
        if row.archived_at or data.archived is True:
            raise HTTPException(422, "Archived evidence cannot be verified")
        if not row.source_note.strip():
            raise HTTPException(422, "A source note is required to verify evidence")
        if any(not metric.source_note.strip() for metric in row.metrics):
            raise HTTPException(422, "Every metric needs a source note before verification")
        row.state = "verified"
        row.verified_at = utc_now()
    elif data.state in {"draft", "rejected"}:
        demote(row)
        row.state = data.state
    set_archive(row, data.archived)
    commit(session)
    return evidence_out(row)


@router.get("/evidence/{record_id}/metrics", response_model=list[MetricOut])
def list_metrics(record_id: str, session: DB = Depends(get_session)) -> list[Metric]:
    row: EvidenceItem = require(session, EvidenceItem, record_id)
    return row.metrics


@router.post("/evidence/{record_id}/metrics", response_model=MetricOut, status_code=201)
def create_metric(record_id: str, data: MetricData, session: DB = Depends(get_session)) -> Metric:
    evidence: EvidenceItem = require(session, EvidenceItem, record_id)
    row = Metric(evidence=evidence, **data.model_dump())
    row.name = clean_required(row.name, "Metric name")
    row.value = clean_required(row.value, "Metric value")
    session.add(row)
    demote(evidence)
    commit(session)
    return row


@router.patch("/metrics/{record_id}", response_model=MetricOut)
def patch_metric(record_id: str, data: MetricPatch, session: DB = Depends(get_session)) -> Metric:
    row: Metric = require(session, Metric, record_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.name = clean_required(row.name, "Metric name")
    row.value = clean_required(row.value, "Metric value")
    if row.source_note is None:
        raise HTTPException(422, "Metric source note cannot be null")
    demote(row.evidence)
    commit(session)
    return row


@router.get("/evidence/{record_id}/bullets", response_model=list[BulletOut])
def list_bullets(record_id: str, session: DB = Depends(get_session)) -> list[BulletVariant]:
    row: EvidenceItem = require(session, EvidenceItem, record_id)
    return row.bullet_variants


@router.post("/evidence/{record_id}/bullets", response_model=BulletOut, status_code=201)
def create_bullet(
    record_id: str, data: BulletData, session: DB = Depends(get_session)
) -> BulletVariant:
    evidence: EvidenceItem = require(session, EvidenceItem, record_id)
    if data.approved and (evidence.state != "verified" or evidence.archived_at):
        raise HTTPException(422, "Verify the source evidence before approving a bullet")
    row = BulletVariant(
        evidence=evidence,
        text=clean_required(data.text, "Bullet text"),
        tone=data.tone,
        approved_at=utc_now() if data.approved else None,
    )
    session.add(row)
    commit(session)
    return row


@router.patch("/bullets/{record_id}", response_model=BulletOut)
def patch_bullet(
    record_id: str, data: BulletPatch, session: DB = Depends(get_session)
) -> BulletVariant:
    row: BulletVariant = require(session, BulletVariant, record_id)
    if data.text is not None:
        row.text = clean_required(data.text, "Bullet text")
        row.approved_at = None
    if data.tone is not None:
        row.tone = data.tone
    if data.approved is True:
        if row.evidence.state != "verified" or row.evidence.archived_at:
            raise HTTPException(422, "Verify active source evidence before approving a bullet")
        row.approved_at = utc_now()
    elif data.approved is False:
        row.approved_at = None
    commit(session)
    return row


@router.delete("/metrics/{record_id}", status_code=204)
def delete_metric(record_id: str, session: DB = Depends(get_session)) -> None:
    row: Metric = require(session, Metric, record_id)
    demote(row.evidence)
    session.delete(row)
    commit(session)


@router.delete("/bullets/{record_id}", status_code=204)
def delete_bullet(record_id: str, session: DB = Depends(get_session)) -> None:
    row: BulletVariant = require(session, BulletVariant, record_id)
    session.delete(row)
    commit(session)


def search_query(value: str) -> str:
    tokens = re.findall(r"\w+", value.casefold(), re.UNICODE)
    return " AND ".join(f'"{token}"*' for token in tokens[:12])


@router.get("/library/search")
def search_library(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    session: DB = Depends(get_session),
) -> list[dict[str, Any]]:
    expression = search_query(q)
    if not expression:
        return []
    rows = session.execute(
        text(
            "SELECT entity_type, entity_id, title FROM library_fts "
            "WHERE library_fts MATCH :query LIMIT :limit"
        ),
        {"query": expression, "limit": limit * 3},
    ).all()
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    models: dict[str, type[Any]] = {
        "experience": Experience,
        "project": Project,
        "skill": Skill,
        "evidence": EvidenceItem,
    }
    for entity_type_raw, entity_id_raw, title_raw in rows:
        entity_type, entity_id, title = str(entity_type_raw), str(entity_id_raw), str(title_raw)
        key = (entity_type, entity_id)
        if key in seen:
            continue
        record = session.get(models[entity_type], entity_id)
        if record is not None and record.archived_at is None:
            results.append({"type": entity_type, "id": entity_id, "title": title})
            seen.add(key)
        if len(results) >= limit:
            break
    return results


@router.get("/library/export")
def export_library(response: Response, session: DB = Depends(get_session)) -> dict[str, Any]:
    response.headers["Content-Disposition"] = 'attachment; filename="career-library.json"'
    profile = session.get(Profile, 1)
    return {
        "format_version": 1,
        "exported_at": utc_now().isoformat(),
        "profile": ProfileData.model_validate(profile).model_dump(mode="json") if profile else None,
        "experiences": [
            ExperienceOut.model_validate(row).model_dump(mode="json")
            for row in session.scalars(select(Experience))
        ],
        "projects": [
            ProjectOut.model_validate(row).model_dump(mode="json")
            for row in session.scalars(select(Project))
        ],
        "skills": [
            skill_out(row).model_dump(mode="json") for row in session.scalars(select(Skill))
        ],
        "evidence": [
            evidence_out(row).model_dump(mode="json")
            for row in session.scalars(select(EvidenceItem))
        ],
    }

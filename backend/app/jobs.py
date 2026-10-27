import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.job_analysis import extract_with_ollama
from app.library import get_session
from app.models import EvidenceItem, Job, JobRequirement, Project, Skill
from app.schemas import (
    JobCreate,
    JobOut,
    JobPatch,
    RequirementData,
    RequirementList,
    RequirementMatchOut,
    RequirementOut,
)

router = APIRouter(prefix="/api/v1", tags=["jobs"])


DB = Session

# Conservative deterministic vocabulary; model output is not needed for a usable first pass.
TERMS: dict[str, tuple[str, str]] = {
    "python": ("skill", "Python"),
    "typescript": ("skill", "TypeScript"),
    "javascript": ("skill", "JavaScript"),
    "react": ("skill", "React"),
    "fastapi": ("tool", "FastAPI"),
    "sql": ("skill", "SQL"),
    "sqlite": ("tool", "SQLite"),
    "postgresql": ("tool", "PostgreSQL"),
    "postgres": ("tool", "PostgreSQL"),
    "docker": ("tool", "Docker"),
    "kubernetes": ("tool", "Kubernetes"),
    "aws": ("tool", "AWS"),
    "azure": ("tool", "Azure"),
    "gcp": ("tool", "GCP"),
    "machine learning": ("skill", "Machine Learning"),
    "data analysis": ("skill", "Data Analysis"),
    "project management": ("skill", "Project Management"),
    "communication": ("skill", "Communication"),
    "leadership": ("skill", "Leadership"),
    "bachelor's degree": ("education", "Bachelor's degree"),
    "master's degree": ("education", "Master's degree"),
    "certification": ("certification", "Certification"),
}


def infer_priority(context: str) -> str:
    context = context.casefold()
    if any(marker in context for marker in ("required", "require ", "must ", "minimum")):
        return "required"
    if any(marker in context for marker in ("preferred", "nice to have", "bonus")):
        return "preferred"
    return "unclear"


def extract_requirements(description: str) -> list[RequirementData]:
    found: dict[str, RequirementData] = {}
    lowered = description.casefold()
    for term, (kind, label) in TERMS.items():
        match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
        if match and label.casefold() not in found:
            start = (
                max(lowered.rfind("\n", 0, match.start()), lowered.rfind(".", 0, match.start())) + 1
            )
            end_candidates = [
                i
                for i in (lowered.find("\n", match.end()), lowered.find(".", match.end()))
                if i != -1
            ]
            end = min(end_candidates) if end_candidates else len(lowered)
            found[label.casefold()] = RequirementData(
                text=label,
                supporting_span=description[match.start() : match.end()],
                normalized_term=label.casefold(),
                kind=kind,
                priority=infer_priority(description[start:end]),
            )
    for sentence in re.split(r"[\n.!;]+", description):
        line = re.sub(r"^[\s•*\-]+", "", sentence).strip()
        if len(line) < 24 or len(line) > 240:
            continue
        low = line.casefold()
        if any(
            marker in low
            for marker in (
                "responsibilit",
                "experience",
                "ability to",
                "proven",
                "manage ",
                "lead ",
                "develop ",
                "build ",
                "design ",
                "deliver ",
                "required",
                "preferred",
            )
        ):
            normalized = re.sub(r"[^\w ]", "", line.casefold()).strip()
            if normalized not in found:
                priority = infer_priority(low)
                found[normalized] = RequirementData(
                    text=line,
                    supporting_span=line,
                    normalized_term=normalized[:200],
                    kind="responsibility",
                    priority=priority,
                )
    return list(found.values())


def job_out(job: Job) -> JobOut:
    return JobOut.model_validate(job)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(session: DB = Depends(get_session)) -> list[JobOut]:
    return [
        job_out(job)
        for job in session.scalars(
            select(Job).options(selectinload(Job.requirements)).order_by(Job.created_at.desc())
        )
    ]


@router.post("/jobs", response_model=JobOut, status_code=201)
def create_job(data: JobCreate, session: DB = Depends(get_session)) -> JobOut:
    job = Job(**data.model_dump())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: DB = Depends(get_session)) -> JobOut:
    job = session.scalar(
        select(Job).options(selectinload(Job.requirements)).where(Job.id == job_id)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    return job_out(job)


@router.post("/jobs/{job_id}/analyze", response_model=JobOut)
def analyze_job(
    job_id: str,
    method: str = Query(default="deterministic", pattern="^(deterministic|ollama)$"),
    force: bool = False,
    session: DB = Depends(get_session),
) -> JobOut:
    job = session.scalar(
        select(Job).options(selectinload(Job.requirements)).where(Job.id == job_id)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    if not force and any(requirement.confirmed for requirement in job.requirements):
        raise HTTPException(409, "Re-extraction replaces reviewed requirements; set force=true")
    requirements = extract_requirements(job.raw_description)
    if method == "ollama":
        try:
            model_requirements = extract_with_ollama(job.raw_description)
            if model_requirements:
                requirements = model_requirements
        except (OSError, ValueError, KeyError, TypeError):
            # No local model, invalid response, or timeout: keep the offline workflow usable.
            pass
    job.requirements = [
        JobRequirement(**item.model_dump(exclude={"id"}), position=index)
        for index, item in enumerate(requirements)
    ]
    session.commit()
    session.refresh(job)
    return job_out(job)


@router.patch("/jobs/{job_id}", response_model=JobOut)
def patch_job(job_id: str, data: JobPatch, session: DB = Depends(get_session)) -> JobOut:
    job = session.scalar(
        select(Job).options(selectinload(Job.requirements)).where(Job.id == job_id)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    values = data.model_dump(exclude_unset=True)
    for field, value in values.items():
        setattr(job, field, value)
    session.commit()
    session.refresh(job)
    return job_out(job)


@router.get("/jobs/{job_id}/requirements", response_model=list[RequirementOut])
def get_requirements(job_id: str, session: DB = Depends(get_session)) -> list[JobRequirement]:
    job = session.scalar(
        select(Job).options(selectinload(Job.requirements)).where(Job.id == job_id)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    return job.requirements


@router.patch("/jobs/{job_id}/requirements", response_model=list[RequirementOut])
def update_requirements(
    job_id: str, data: RequirementList, session: DB = Depends(get_session)
) -> list[JobRequirement]:
    job = session.scalar(
        select(Job).options(selectinload(Job.requirements)).where(Job.id == job_id)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    old = {row.id: row for row in job.requirements}
    seen: set[str] = set()
    updated: list[JobRequirement] = []
    for position, item in enumerate(data.requirements):
        value = item.text.strip()
        if len(value) < 2:
            raise HTTPException(422, "Requirement text cannot be empty")
        if item.id and (item.id not in old or item.id in seen):
            raise HTTPException(422, "Unknown or duplicate requirement ID")
        if item.id:
            seen.add(item.id)
        row = old[item.id] if item.id else JobRequirement()
        changed = row.text != value if item.id else True
        row.text = value
        row.supporting_span = old[item.id].supporting_span if item.id and not changed else None
        row.normalized_term = normalize(value)[:200]
        row.kind = item.kind
        row.priority = item.priority
        row.confirmed = item.confirmed if not changed else False
        row.position = position
        updated.append(row)
    job.requirements = updated
    session.commit()
    return job.requirements


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#.]+", value.casefold()))


STOP_WORDS = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "have",
    "using",
    "work",
    "working",
    "experience",
    "required",
    "preferred",
    "ability",
    "skills",
    "strong",
    "years",
    "you",
    "will",
    "are",
    "our",
    "team",
    "role",
    "must",
    "plus",
    "knowledge",
}


def classify_match(requirement: str, claim: str, skills: list[str]) -> str | None:
    term = normalize(requirement)
    if not term:
        return None
    claim_text = normalize(claim)
    # Only the verified claim and demonstrated skill tags count. Source notes can
    # contain negations or background context and are not resume claims.
    claim_words = claim_text.split()
    term_words = term.split()
    for index in range(len(claim_words) - len(term_words) + 1):
        if claim_words[index : index + len(term_words)] == term_words:
            if set(claim_words[max(0, index - 3) : index]) & {
                "no",
                "not",
                "without",
                "never",
                "lack",
                "lacking",
            }:
                return None
            return "direct"
    if any(f" {term} " in f" {normalize(skill)} " for skill in skills):
        return "direct"
    tokens = {word for word in term.split() if len(word) >= 4 and word not in STOP_WORDS}
    overlap = tokens & set(claim_words)
    # A single incidental shared word is not evidence of a related capability.
    if len(tokens) >= 2 and len(overlap) >= 2 and len(overlap) / len(tokens) >= 0.5:
        return "related"
    return None


@router.post("/jobs/{job_id}/matches", response_model=list[RequirementMatchOut])
def match_job(job_id: str, session: DB = Depends(get_session)) -> list[dict[str, Any]]:
    job = session.scalar(
        select(Job).options(selectinload(Job.requirements)).where(Job.id == job_id)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    evidence_rows = session.scalars(
        select(EvidenceItem)
        .options(
            selectinload(EvidenceItem.skills).selectinload(Skill.aliases),
            selectinload(EvidenceItem.experience),
            selectinload(EvidenceItem.project).selectinload(Project.experience),
        )
        .where(EvidenceItem.state == "verified", EvidenceItem.archived_at.is_(None))
    ).all()
    results = []
    for req in job.requirements:
        matches = []
        for item in evidence_rows:
            if (item.experience and item.experience.archived_at) or (
                item.project
                and (
                    item.project.archived_at
                    or (item.project.experience and item.project.experience.archived_at)
                )
            ):
                continue
            skill_terms = [
                term
                for skill in item.skills
                if skill.archived_at is None
                for term in [skill.name, *(alias.alias for alias in skill.aliases)]
            ]
            status = classify_match(req.normalized_term or req.text, item.claim, skill_terms)
            if status:
                matches.append(
                    {
                        "evidence_id": item.id,
                        "evidence_text": item.claim,
                        "state": item.state,
                        "status": status,
                        "reason": "Exact phrase in verified claim or demonstrated skill."
                        if status == "direct"
                        else "Some terms overlap; review relevance.",
                    }
                )
        matches.sort(key=lambda m: (m["status"] != "direct", m["evidence_text"].casefold()))
        results.append(
            {
                "requirement": {
                    "id": req.id,
                    "text": req.text,
                    "kind": req.kind,
                    "priority": req.priority,
                    "confirmed": req.confirmed,
                },
                "status": "direct"
                if any(m["status"] == "direct" for m in matches)
                else "related"
                if matches
                else "unsupported",
                "matches": matches,
            }
        )
    return results

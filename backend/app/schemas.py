from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResumeCreate(BaseModel):
    job_id: str
    name: str = Field(min_length=1, max_length=200)


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: str
    name: str
    status: str
    created_at: datetime


class ResumeBulletInput(BaseModel):
    evidence_id: str
    text: str = Field(min_length=1, max_length=2000)


class ResumeSectionInput(BaseModel):
    heading: Literal["Experience", "Projects", "Selected evidence"]
    bullets: list[ResumeBulletInput] = Field(min_length=1, max_length=50)


class DraftRequest(BaseModel):
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    sections: list[ResumeSectionInput] | None = Field(default=None, min_length=1, max_length=3)
    approve: bool = False

    @model_validator(mode="after")
    def validate_selection(self) -> "DraftRequest":
        if self.sections is not None:
            if self.evidence_ids:
                raise ValueError("Use sections or evidence_ids, not both")
            if sum(len(section.bullets) for section in self.sections) > 50:
                raise ValueError("Maximum 50 bullets")
            headings = [section.heading for section in self.sections]
            if len(headings) != len(set(headings)):
                raise ValueError("Duplicate section headings")
        elif not self.evidence_ids:
            raise ValueError("Select at least one evidence item")
        return self


class DraftValidationIssue(BaseModel):
    evidence_id: str
    position: int
    code: Literal["duplicate", "unavailable_evidence", "section_context", "unsafe_wording"]
    message: str


class DraftValidationOut(BaseModel):
    valid: bool
    issues: list[DraftValidationIssue]


class ResumeBulletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    evidence_id: str
    text: str
    position: int
    evidence_snapshot: dict[str, object]


class ResumeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    resume_id: str
    version_number: int
    content: dict[str, object]
    template: str
    created_at: datetime
    approved_at: datetime | None
    bullets: list[ResumeBulletOut]


class JobCreate(BaseModel):
    company: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(default="", max_length=1000)
    raw_description: str = Field(min_length=20, max_length=100000)
    source: str = Field(default="pasted", max_length=200)


class RequirementData(BaseModel):
    id: str | None = None
    text: str = Field(min_length=2, max_length=1000)
    supporting_span: str | None = Field(default=None, max_length=1000)
    normalized_term: str = Field(default="", max_length=200)
    kind: Literal["skill", "tool", "responsibility", "experience", "education", "certification"] = (
        "skill"
    )
    priority: Literal["required", "preferred", "unclear"] = "unclear"
    confirmed: bool = False


class RequirementOut(RequirementData):
    model_config = ConfigDict(from_attributes=True)
    id: str


class RequirementList(BaseModel):
    requirements: list[RequirementData] = Field(max_length=100)


class JobPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=1000)


class MatchedEvidence(BaseModel):
    evidence_id: str
    evidence_text: str
    state: Literal["verified"]
    status: Literal["direct", "related"]
    reason: str


class MatchRequirement(BaseModel):
    id: str
    text: str
    kind: str
    priority: str
    confirmed: bool


class RequirementMatchOut(BaseModel):
    requirement: MatchRequirement
    status: Literal["direct", "related", "unsupported"]
    matches: list[MatchedEvidence]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company: str
    title: str
    url: str
    raw_description: str
    source: str
    created_at: datetime
    requirements: list[RequirementOut]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfileData(Out):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class ExperienceData(BaseModel):
    organization: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    location: str = ""
    description: str = ""

    @model_validator(mode="after")
    def dates_in_order(self) -> "ExperienceData":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be after start date")
        return self


class ExperiencePatch(BaseModel):
    organization: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    description: str | None = None
    archived: bool | None = None


class ExperienceOut(ExperienceData, Out):
    id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProjectData(BaseModel):
    experience_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    summary: str = ""
    start_date: date | None = None
    end_date: date | None = None
    url: str = ""

    @model_validator(mode="after")
    def dates_in_order(self) -> "ProjectData":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be after start date")
        return self


class ProjectPatch(BaseModel):
    experience_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    url: str | None = None
    archived: bool | None = None


class ProjectOut(ProjectData, Out):
    id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class SkillData(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = ""
    aliases: list[str] = Field(default_factory=list)

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, value: list[str]) -> list[str]:
        aliases = [alias.strip() for alias in value]
        if any(not alias or len(alias) > 120 for alias in aliases):
            raise ValueError("Aliases must be 1 to 120 characters")
        if len(set(alias.casefold() for alias in aliases)) != len(aliases):
            raise ValueError("Aliases must be unique")
        return aliases


class SkillPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = None
    aliases: list[str] | None = None
    archived: bool | None = None

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, value: list[str] | None) -> list[str] | None:
        return SkillData(name="placeholder", aliases=value).aliases if value is not None else None


class SkillOut(Out):
    id: str
    name: str
    canonical_name: str
    category: str
    aliases: list[str]
    archived_at: datetime | None


class EvidenceData(BaseModel):
    claim: str = Field(min_length=1)
    source_note: str = ""
    experience_id: str | None = None
    project_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_context(self) -> "EvidenceData":
        if not (self.experience_id or self.project_id):
            raise ValueError("Link evidence to an experience or project")
        return self


class EvidencePatch(BaseModel):
    claim: str | None = Field(default=None, min_length=1)
    source_note: str | None = None
    experience_id: str | None = None
    project_id: str | None = None
    skill_ids: list[str] | None = None
    state: Literal["draft", "verified", "rejected"] | None = None
    archived: bool | None = None


class MetricData(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=120)
    unit: str = ""
    context: str = ""
    source_note: str = ""


class MetricPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    value: str | None = Field(default=None, min_length=1, max_length=120)
    unit: str | None = None
    context: str | None = None
    source_note: str | None = None


class MetricOut(MetricData, Out):
    id: str
    evidence_id: str


class BulletData(BaseModel):
    text: str = Field(min_length=1)
    tone: str = ""
    approved: bool = False


class BulletPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    tone: str | None = None
    approved: bool | None = None


class BulletOut(Out):
    id: str
    evidence_id: str
    text: str
    tone: str
    approved_at: datetime | None


class EvidenceOut(Out):
    id: str
    claim: str
    source_note: str
    experience_id: str | None
    project_id: str | None
    state: str
    verified_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    skill_ids: list[str]
    metrics: list[MetricOut]
    bullet_variants: list[BulletOut]

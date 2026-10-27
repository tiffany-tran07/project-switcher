from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(1000), nullable=False)


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(100), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    links: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(RecordMixin, Base):
    __tablename__ = "jobs"

    company: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000), default="")
    raw_description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="pasted")
    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobRequirement.position"
    )


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('skill','tool','responsibility','experience','education','certification')",
            name="requirement_kind",
        ),
        CheckConstraint(
            "priority IN ('required','preferred','unclear')", name="requirement_priority"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    supporting_span: Mapped[str | None] = mapped_column(Text)
    normalized_term: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(30), default="skill")
    priority: Mapped[str] = mapped_column(String(20), default="unclear")
    confirmed: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(default=0)
    job: Mapped[Job] = relationship(back_populates="requirements")


class Resume(RecordMixin, Base):
    __tablename__ = "resumes"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    job: Mapped[Job] = relationship()
    versions: Mapped[list["ResumeVersion"]] = relationship(
        back_populates="resume", order_by="ResumeVersion.version_number"
    )


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="RESTRICT"))
    version_number: Mapped[int] = mapped_column()
    content: Mapped[dict[str, object]] = mapped_column(JSON)
    template: Mapped[str] = mapped_column(String(100), default="single_column")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sealed: Mapped[bool] = mapped_column(default=False)
    resume: Mapped[Resume] = relationship(back_populates="versions")
    bullets: Mapped[list["ResumeBullet"]] = relationship(
        back_populates="version", order_by="ResumeBullet.position"
    )


class ResumeBullet(Base):
    __tablename__ = "resume_bullets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(ForeignKey("resume_versions.id", ondelete="RESTRICT"))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_items.id", ondelete="RESTRICT"))
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column()
    evidence_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    version: Mapped[ResumeVersion] = relationship(back_populates="bullets")


class Experience(RecordMixin, Base):
    __tablename__ = "experiences"

    organization: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    projects: Mapped[list["Project"]] = relationship(back_populates="experience")
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(back_populates="experience")


class Project(RecordMixin, Base):
    __tablename__ = "projects"

    experience_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiences.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str] = mapped_column(String(1000), default="")
    experience: Mapped[Experience | None] = relationship(back_populates="projects")
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(back_populates="project")


class Skill(RecordMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("canonical_name"),)

    name: Mapped[str] = mapped_column(String(120))
    canonical_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(100), default="")
    aliases: Mapped[list["SkillAlias"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        secondary="evidence_skills", back_populates="skills"
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (UniqueConstraint("skill_id", "alias"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(120))
    skill: Mapped[Skill] = relationship(back_populates="aliases")


class EvidenceSkill(Base):
    __tablename__ = "evidence_skills"

    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True
    )


class EvidenceItem(RecordMixin, Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        CheckConstraint("state IN ('draft', 'verified', 'rejected')", name="evidence_state"),
    )

    claim: Mapped[str] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text, default="")
    experience_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiences.id", ondelete="RESTRICT")
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(String(20), default="draft")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    experience: Mapped[Experience | None] = relationship(back_populates="evidence_items")
    project: Mapped[Project | None] = relationship(back_populates="evidence_items")
    skills: Mapped[list[Skill]] = relationship(
        secondary="evidence_skills", back_populates="evidence_items"
    )
    metrics: Mapped[list["Metric"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )
    bullet_variants: Mapped[list["BulletVariant"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(80), default="")
    context: Mapped[str] = mapped_column(Text, default="")
    source_note: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[EvidenceItem] = relationship(back_populates="metrics")


class BulletVariant(Base):
    __tablename__ = "bullet_variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(String(80), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[EvidenceItem] = relationship(back_populates="bullet_variants")

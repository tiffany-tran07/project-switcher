"""Single-column DOCX rendering from immutable snapshots, never current career data."""

from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt
from pydantic import BaseModel, Field

from app.schemas import ProfileData, ResumeVersionOut


class Section(BaseModel):
    heading: str
    evidence_ids: list[str]


class Content(BaseModel):
    profile: ProfileData = Field(default_factory=ProfileData)
    sections: list[Section]


class Role(BaseModel):
    organization: str = ""
    title: str = ""
    start_date: str | None = None
    end_date: str | None = None
    location: str = ""


class ProjectContext(BaseModel):
    name: str = ""
    start_date: str | None = None
    end_date: str | None = None
    url: str = ""


class Source(BaseModel):
    experience: Role | None = None
    project: ProjectContext | None = None


def context_lines(source: Source, heading: str) -> list[str]:
    role, project = source.experience, source.project
    if heading == "Projects" and project:
        return [
            line
            for line in [
                project.name,
                role.organization if role else "",
                " – ".join(date for date in (project.start_date, project.end_date) if date),
                project.url,
            ]
            if line
        ]
    if role:
        dates = " – ".join(date for date in (role.start_date, role.end_date) if date)
        return [
            line
            for line in [
                role.title,
                role.organization,
                " · ".join(value for value in (dates, role.location) if value),
            ]
            if line
        ]
    if project:
        return [
            line
            for line in [
                project.name,
                " – ".join(date for date in (project.start_date, project.end_date) if date),
                project.url,
            ]
            if line
        ]
    return []


def document_lines(version: ResumeVersionOut) -> list[tuple[str, str]]:
    content = Content.model_validate(version.content)
    lines: list[tuple[str, str]] = []
    profile = content.profile
    if profile.name:
        lines.append(("Title", profile.name))
    contact = " · ".join(
        value for value in (profile.email, profile.phone, profile.location) if value
    )
    if contact:
        lines.append(("Normal", contact))
    lines.extend(("Normal", link) for link in profile.links if link)
    bullets = {bullet.evidence_id: bullet for bullet in version.bullets}
    seen: set[str] = set()
    for section in content.sections:
        lines.append(("Heading 1", section.heading))
        previous: list[str] | None = None
        for evidence_id in section.evidence_ids:
            if evidence_id not in bullets or evidence_id in seen:
                raise ValueError("Snapshot has missing or duplicate bullet links")
            seen.add(evidence_id)
            bullet = bullets[evidence_id]
            context = context_lines(
                Source.model_validate(bullet.evidence_snapshot), section.heading
            )
            if context != previous:
                lines.extend(("Normal", line) for line in context)
                previous = context
            lines.append(("List Bullet", bullet.text))
    if seen != set(bullets):
        raise ValueError("Snapshot contains bullets outside its sections")
    return lines


def render_docx(version: ResumeVersionOut) -> tuple[bytes, str]:
    lines = document_lines(version)
    document = Document()
    document.core_properties.author = ""
    document.core_properties.last_modified_by = ""
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    for section in document.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
    for style, text in lines:
        document.add_paragraph(text, style=style)
    buffer = BytesIO()
    document.save(buffer)
    data = buffer.getvalue()
    extracted = "\n".join(paragraph.text for paragraph in Document(BytesIO(data)).paragraphs)
    if extracted != "\n".join(text for _, text in lines):
        raise ValueError("DOCX text extraction did not preserve approved text order")
    return data, extracted

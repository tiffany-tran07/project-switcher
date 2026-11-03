import stat
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from fastapi.testclient import TestClient

from app import resume_intake
from app.config import settings

pytest_plugins = ("test_library",)


@pytest.fixture
def intake_client(client: TestClient) -> TestClient:
    return client


def docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("Jane Example")
    document.add_paragraph("Engineer · 2020–2023")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "PostgreSQL"
    document.add_paragraph("Reduced latency by -30% at €20 cost.")
    document.part.relate_to(
        "https://example.invalid/private", RELATIONSHIP_TYPE.HYPERLINK, is_external=True
    )
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def modified_docx(data: bytes, changes: dict[str, bytes]) -> bytes:
    with ZipFile(BytesIO(data)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members.update(changes)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_selected_excerpt_saves_only_unverified_draft(intake_client: TestClient) -> None:
    from hashlib import sha256

    client = intake_client
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Example",
            "title": "Engineer",
        },
    ).json()
    text = "Jane Example\nprivate@example.test\nBuilt Python services with -30% latency change"
    claim = "Built Python services with -30% latency change"
    payload = {
        "source_text": text,
        "source_name": "resume.txt",
        "claim": claim,
        "experience_id": experience["id"],
        "source_note": "Benchmark report for later review",
    }
    response = client.post("/api/v1/resume-intake/drafts", json=payload)
    assert response.status_code == 201
    evidence = response.json()
    assert evidence["claim"] == claim
    assert evidence["experience_id"] == experience["id"]
    assert evidence["state"] == "draft"
    assert evidence["verified_at"] is None
    assert evidence["metrics"] == []
    assert evidence["bullet_variants"] == []
    assert evidence["skill_ids"] == []
    assert "resume.txt" in evidence["source_note"]
    assert sha256(text.encode()).hexdigest() in evidence["source_note"]
    assert "private@example.test" not in evidence["source_note"]
    assert "verify against underlying work" in evidence["source_note"]
    assert client.get("/api/v1/resumes").json() == []
    assert client.post("/api/v1/resume-intake/drafts", json=payload).status_code == 409
    assert len(client.get("/api/v1/evidence").json()) == 1
    assert (
        client.post(
            f"/api/v1/evidence/{evidence['id']}/bullets",
            json={
                "text": claim,
                "approved": True,
            },
        ).status_code
        == 422
    )


def test_intake_drafts_require_exact_excerpt_and_active_context(intake_client: TestClient) -> None:
    client = intake_client
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Example",
            "title": "Engineer",
        },
    ).json()
    project = client.post(
        "/api/v1/projects",
        json={
            "name": "Pipeline",
            "experience_id": experience["id"],
        },
    ).json()
    payload = {"source_text": "Built Python services", "claim": "Built Python services"}
    for invalid in (
        payload,
        {**payload, "experience_id": "missing"},
        {**payload, "experience_id": experience["id"], "claim": "Built Kubernetes services"},
        {**payload, "experience_id": experience["id"], "state": "verified"},
        {**payload, "experience_id": experience["id"], "verified_at": "2026-01-01T00:00:00Z"},
        {**payload, "experience_id": experience["id"], "claim": "   "},
        {**payload, "experience_id": experience["id"], "source_name": "\n"},
    ):
        assert client.post("/api/v1/resume-intake/drafts", json=invalid).status_code in {404, 422}
    assert client.get("/api/v1/evidence").json() == []
    client.patch(f"/api/v1/experiences/{experience['id']}", json={"archived": True})
    assert (
        client.post(
            "/api/v1/resume-intake/drafts",
            json={
                **payload,
                "project_id": project["id"],
            },
        ).status_code
        == 422
    )
    assert client.get("/api/v1/evidence").json() == []


def test_intake_draft_accepts_unicode_excerpt_without_offset_guessing(
    intake_client: TestClient,
) -> None:
    client = intake_client
    project = client.post("/api/v1/projects", json={"name": "Personal project"}).json()
    claim = "Built résumé tools at €20 cost"
    response = client.post(
        "/api/v1/resume-intake/drafts",
        json={
            "source_text": f"👋\n{claim}\nOther work",
            "claim": claim,
            "project_id": project["id"],
        },
    )
    assert response.status_code == 201
    assert response.json()["claim"] == claim
    assert response.json()["project_id"] == project["id"]
    assert response.json()["state"] == "draft"


def test_docx_preview_preserves_order_and_never_creates_records(intake_client: TestClient) -> None:
    client = intake_client
    before = client.get("/api/v1/dashboard").json()["counts"]
    files = set(settings.resolved_data_dir.rglob("*"))
    response = client.post(
        "/api/v1/resume-intake/preview", params={"filename": "my-resume.docx"}, content=docx_bytes()
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["format"] == "docx"
    assert preview["filename"] == "my-resume.docx"
    assert (
        preview["text"] == "Jane Example\nEngineer · 2020–2023\nPython | PostgreSQL\n"
        "Reduced latency by -30% at €20 cost."
    )
    assert any("Tables detected" in warning for warning in preview["warnings"])
    assert any("no career records" in warning for warning in preview["warnings"])
    assert client.get("/api/v1/dashboard").json()["counts"] == before
    assert set(settings.resolved_data_dir.rglob("*")) == files
    assert client.get("/api/v1/evidence").json() == []


def test_utf8_text_preview_and_line_endings(intake_client: TestClient) -> None:
    text = "\ufeffRésumé\r\nBuilt multilingual Python services\r\n"
    result = intake_client.post(
        "/api/v1/resume-intake/preview", params={"filename": "resume.TXT"}, content=text.encode()
    ).json()
    assert result["text"] == "Résumé\nBuilt multilingual Python services"
    assert result["format"] == "txt"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("resume.pdf", b"%PDF-1.0"),
        ("resume.docm", b"PK"),
        ("../resume.docx", b"PK"),
        ("/private/resume.txt", b"text"),
        ("folder\\resume.txt", b"text"),
        ("resume.txt", b"bad\x00text"),
        ("resume.txt", b"\xff\xfeinvalid"),
        ("resume.txt", b"   "),
        ("resume.docx", b"not a zip"),
        ("resume.txt", b""),
    ],
)
def test_intake_rejects_unsupported_or_invalid_files(
    intake_client: TestClient, filename: str, content: bytes
) -> None:
    response = intake_client.post(
        "/api/v1/resume-intake/preview",
        params={"filename": filename},
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422


def test_docx_path_entities_and_macros_rejected(intake_client: TestClient) -> None:
    data = docx_bytes()
    with ZipFile(BytesIO(data)) as archive:
        document = archive.read("word/document.xml")
    unsafe = [
        {"../escape": b"unsafe"},
        {"word/vbaProject.bin": b"macro"},
        {"word/embeddings/oleObject1.bin": b"object"},
        {
            "word/document.xml": b'<!DOCTYPE document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            + document
        },
        {"word/document.xml": '<!DOCTYPE x [<!ENTITY xxe "bad">]><x/>'.encode("utf-16")},
    ]
    for change in unsafe:
        response = intake_client.post(
            "/api/v1/resume-intake/preview",
            params={"filename": "resume.docx"},
            content=modified_docx(data, change),
        )
        assert response.status_code == 422


def test_docx_huge_grid_span_does_not_expand_cells(intake_client: TestClient) -> None:
    data = docx_bytes()
    with ZipFile(BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")
    # A malicious merged-cell width must never allocate millions of cell wrappers.
    xml = xml.replace(b"<w:tcPr>", b'<w:tcPr><w:gridSpan w:val="1000000000"/>', 1)
    result = intake_client.post(
        "/api/v1/resume-intake/preview",
        params={"filename": "resume.docx"},
        content=modified_docx(data, {"word/document.xml": xml}),
    )
    assert result.status_code == 200
    assert result.json()["text"].count("Python") == 1


def test_empty_docx_tables_are_not_readable_text(intake_client: TestClient) -> None:
    document = Document()
    document.add_table(rows=2, cols=2)
    output = BytesIO()
    document.save(output)
    response = intake_client.post(
        "/api/v1/resume-intake/preview",
        params={"filename": "empty.docx"},
        content=output.getvalue(),
    )
    assert response.status_code == 422
    assert "No readable resume text" in response.json()["detail"]


def test_intake_limits(intake_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resume_intake, "MAX_UPLOAD_BYTES", 10)
    assert (
        intake_client.post(
            "/api/v1/resume-intake/preview", params={"filename": "resume.txt"}, content=b"a" * 11
        ).status_code
        == 413
    )
    monkeypatch.setattr(resume_intake, "MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
    monkeypatch.setattr(resume_intake, "MAX_TEXT_CHARS", 10)
    assert (
        intake_client.post(
            "/api/v1/resume-intake/preview", params={"filename": "resume.txt"}, content=b"a" * 11
        ).status_code
        == 413
    )
    assert (
        intake_client.post(
            "/api/v1/resume-intake/preview",
            params={"filename": "resume.docx"},
            content=docx_bytes(),
        ).status_code
        == 413
    )
    monkeypatch.setattr(resume_intake, "MAX_TEXT_CHARS", 100000)
    monkeypatch.setattr(resume_intake, "MAX_PACKAGE_BYTES", 100)
    assert (
        intake_client.post(
            "/api/v1/resume-intake/preview",
            params={"filename": "resume.docx"},
            content=docx_bytes(),
        ).status_code
        == 413
    )


def test_docx_duplicate_and_symlink_entries_rejected(intake_client: TestClient) -> None:
    data = docx_bytes()
    for symlink in (True, False):
        output = BytesIO()
        with ZipFile(BytesIO(data)) as source, ZipFile(output, "w") as target:
            for entry in source.infolist():
                target.writestr(entry, source.read(entry))
            if symlink:
                entry = ZipInfo("word/link")
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(entry, "/private/file")
            else:
                with pytest.warns(UserWarning, match="Duplicate name"):
                    target.writestr("word/document.xml", b"<x/>")
        assert (
            intake_client.post(
                "/api/v1/resume-intake/preview",
                params={"filename": "resume.docx"},
                content=output.getvalue(),
            ).status_code
            == 422
        )

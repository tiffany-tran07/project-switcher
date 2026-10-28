from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import exports
from app.config import settings
from app.documents import render_docx
from app.schemas import ResumeVersionOut

pytest_plugins = ("test_library",)


@pytest.fixture
def export_client(client: TestClient) -> TestClient:
    return client


@pytest.fixture
def snapshot(export_client: TestClient) -> dict[str, Any]:
    client = export_client
    client.put(
        "/api/v1/profile",
        json={
            "name": "Saved Name",
            "email": "saved@example.test",
            "phone": "555-0100",
            "location": "Remote",
            "links": ["https://example.test"],
        },
    )
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Target role",
            "raw_description": "Required Kubernetes experience with Python.",
        },
    ).json()
    resume = client.post("/api/v1/resumes", json={"job_id": job["id"], "name": "Targeted"}).json()
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Saved Employer",
            "title": "Engineer",
            "start_date": "2020-01-01",
            "end_date": "2023-06-30",
        },
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "Improved Python reports by 30%",
            "source_note": "Private verification notes",
        },
    ).json()
    client.patch(f"/api/v1/evidence/{evidence['id']}", json={"state": "verified"})
    approved = client.post(
        f"/api/v1/resumes/{resume['id']}/draft",
        json={
            "evidence_ids": [evidence["id"]],
            "approve": True,
        },
    ).json()
    draft = client.post(
        f"/api/v1/resumes/{resume['id']}/draft",
        json={
            "evidence_ids": [evidence["id"]],
        },
    ).json()
    return {"approved": approved, "draft": draft, "evidence": evidence}


def test_docx_export_preserves_snapshot_and_extracted_text(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    version = snapshot["approved"]
    # Export must not fetch updated profile/evidence values.
    client.put("/api/v1/profile", json={"name": "Changed Name"})
    client.patch(
        f"/api/v1/evidence/{snapshot['evidence']['id']}",
        json={
            "claim": "Changed claim",
            "archived": True,
        },
    )
    response = client.post(
        f"/api/v1/resume-versions/{version['id']}/export", json={"format": "docx"}
    )
    assert response.status_code == 201
    artifact = response.json()
    downloaded = client.get(f"/api/v1/exports/{artifact['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == exports.DOCX_MEDIA_TYPE
    assert "attachment" in downloaded.headers["content-disposition"]
    assert sha256(downloaded.content).hexdigest() == artifact["checksum"]
    document = Document(BytesIO(downloaded.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert text == artifact["extracted_text"]
    for expected in (
        "Saved Name",
        "saved@example.test",
        "Saved Employer",
        "Engineer",
        "2020-01-01 – 2023-06-30",
        "Improved Python reports by 30%",
    ):
        assert expected in text
    for excluded in ("Changed Name", "Changed claim", "Private verification notes", "Kubernetes"):
        assert excluded not in text
    assert text.index("Saved Name") < text.index("Saved Employer") < text.index("Improved Python")
    assert document.tables == []
    assert document.inline_shapes.__len__() == 0
    assert client.get(f"/api/v1/resume-versions/{version['id']}/exports").json() == [artifact]
    assert client.get(f"/api/v1/resume-versions/{version['id']}").json() == version


def test_export_rejects_drafts_unknown_versions_and_unsupported_formats(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    assert (
        client.post(
            f"/api/v1/resume-versions/{snapshot['draft']['id']}/export", json={}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/resume-versions/missing/export", json={}).status_code == 404
    assert client.get("/api/v1/resume-versions/missing/exports").status_code == 404
    assert client.get("/api/v1/exports/missing/download").status_code == 404
    assert (
        client.post(
            f"/api/v1/resume-versions/{snapshot['approved']['id']}/export", json={"format": "pdf"}
        ).status_code
        == 422
    )
    assert list((settings.resolved_data_dir / "exports").glob("*.docx")) == []


def test_download_detects_tampering_and_missing_file(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    artifact = export_client.post(
        f"/api/v1/resume-versions/{snapshot['approved']['id']}/export",
        json={},
    ).json()
    path = settings.resolved_data_dir / "exports" / f"{artifact['id']}.docx"
    path.write_bytes(b"tampered")
    assert export_client.get(f"/api/v1/exports/{artifact['id']}/download").status_code == 409
    path.unlink()
    assert export_client.get(f"/api/v1/exports/{artifact['id']}/download").status_code == 404


def test_export_path_blocks_traversal_and_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    outside = tmp_path / "outside"
    outside.mkdir()
    settings.resolved_data_dir.mkdir()
    (settings.resolved_data_dir / "exports").symlink_to(outside, target_is_directory=True)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        exports.export_path("exports/test.docx")
    with pytest.raises(HTTPException):
        exports.export_path("../outside/test.docx")


def test_docx_respects_section_order_and_project_dates(snapshot: dict[str, Any]) -> None:
    version = ResumeVersionOut.model_validate(snapshot["approved"])
    original = version.bullets[0]
    project = original.model_copy(deep=True)
    project.evidence_id = "project-evidence"
    project.id = "project-bullet"
    project.text = "Built a pipeline"
    project.evidence_snapshot["project"] = {
        "name": "Saved Pipeline",
        "start_date": "2022-01-01",
        "end_date": "2022-06-01",
        "url": "https://example.test/project",
    }
    version.bullets.append(project)
    version.content["sections"] = [
        {"heading": "Projects", "evidence_ids": ["project-evidence"]},
        {"heading": "Experience", "evidence_ids": [original.evidence_id]},
    ]
    data, extracted = render_docx(version)
    assert data.startswith(b"PK")
    assert (
        extracted.index("Projects")
        < extracted.index("Built a pipeline")
        < extracted.index("Experience")
    )
    assert "2022-01-01 – 2022-06-01" in extracted
    assert "https://example.test/project" in extracted
    version.content["sections"] = [{"heading": "Projects", "evidence_ids": ["missing"]}]
    with pytest.raises(ValueError):
        render_docx(version)


def test_storage_failure_creates_no_export_record(
    export_client: TestClient,
    snapshot: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocker = settings.resolved_data_dir / "blocker"
    blocker.write_text("Not a directory")
    monkeypatch.setattr(exports, "export_path", lambda _: blocker / "file.docx")
    version_id = snapshot["approved"]["id"]
    assert (
        export_client.post(f"/api/v1/resume-versions/{version_id}/export", json={}).status_code
        == 503
    )
    assert export_client.get(f"/api/v1/resume-versions/{version_id}/exports").json() == []


def test_failed_extraction_does_not_create_artifact(
    export_client: TestClient,
    snapshot: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed(_: object) -> tuple[bytes, str]:
        raise ValueError("Text mismatch")

    monkeypatch.setattr(exports, "render_docx", failed)
    version_id = snapshot["approved"]["id"]
    assert (
        export_client.post(f"/api/v1/resume-versions/{version_id}/export", json={}).status_code
        == 422
    )
    assert export_client.get(f"/api/v1/resume-versions/{version_id}/exports").json() == []
    assert list((settings.resolved_data_dir / "exports").glob("*.docx")) == []

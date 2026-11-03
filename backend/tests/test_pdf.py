import subprocess
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from acceptance_documents import acceptance_version
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import create_engine

from app import pdf
from app.ats import analyze_document, requirement_result
from app.config import settings
from app.documents import render_docx
from app.models import JobRequirement
from app.resume_intake import preview_resume
from app.schemas import ResumeVersionOut

pytest_plugins = ("test_library", "test_exports")


def pdf_bytes(lines: list[str], pages: int = 1) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    commands = [b"BT /F1 11 Tf 40 750 Td 14 TL"]
    for line in lines:
        escaped = (
            line.encode("cp1252")
            .replace(b"\\", b"\\\\")
            .replace(b"(", b"\\(")
            .replace(b")", b"\\)")
        )
        commands.append(b"(" + escaped + b") Tj T*")
    commands.append(b"ET")
    stream = DecodedStreamObject()
    stream.set_data(b"\n".join(commands))
    page[NameObject("/Contents")] = stream
    for _ in range(pages - 1):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_extraction_and_order_preservation() -> None:
    data = pdf_bytes(["Saved Name", "Engineer", "2020-01-01 – 2023-06-30", "Improved reports 30%"])
    text, pages = pdf.extract_pdf(data)
    assert pages == 1
    assert pdf.preserves_text(
        "Saved Name\nEngineer\n2020-01-01 – 2023-06-30\nImproved reports 30%", text
    )
    assert not pdf.preserves_text("Engineer\nSaved Name", text)
    assert not pdf.preserves_text("Improved reports 40%", text)
    with pytest.raises(pdf.PdfConversionError):
        pdf.extract_pdf(b"not a pdf")


def test_pdf_readiness_warns_on_lost_or_reordered_text() -> None:
    _, _, checks = analyze_document(
        pdf_bytes(["Last bullet", "First bullet"]),
        "pdf",
        "First bullet\nLast bullet",
        2,
    )
    assert next(check for check in checks if check.name == "text_order").status == "warning"
    with pytest.raises(HTTPException) as error:
        analyze_document(b"bad pdf", "pdf", "Expected text", 2)
    assert error.value.status_code == 422
    # PDF line wrapping must not hide an otherwise exact, supported phrase.
    text = pdf.normalized_text("Performed data\nanalysis")
    result = requirement_result(
        JobRequirement(id="r", text="data analysis"),
        text,
        [("e", "Performed data analysis", [])],
        [],
    )
    assert result.status == "present_exact"


def test_converter_isolated_and_checks_real_pdf_text(monkeypatch: pytest.MonkeyPatch) -> None:
    paths: list[Path] = []
    monkeypatch.setattr(pdf, "find_libreoffice", lambda: "/mock/soffice")

    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        assert command[0] == "/mock/soffice"
        assert "--headless" in command
        assert any(arg.startswith("-env:UserInstallation=file:") for arg in command)
        assert options == {"capture_output": True, "timeout": 45, "check": False}
        output = Path(command[command.index("--outdir") + 1])
        assert Path(command[-1]).read_bytes() == b"docx input"
        paths.append(output.parent)
        (output / "resume.pdf").write_bytes(pdf_bytes(["Saved Name", "Built Python services"]))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(pdf.subprocess, "run", run)
    result, text, count = pdf.convert_pdf(b"docx input", "Saved Name\nBuilt Python services")
    assert result.startswith(b"%PDF-")
    assert count == 1
    assert "Built Python services" in text
    assert all(not path.exists() for path in paths)
    with pytest.raises(pdf.PdfConversionError, match="lost or reordered"):
        pdf.convert_pdf(b"docx input", "Invented content")


@pytest.mark.parametrize("failure", ["missing", "timeout", "nonzero", "no_output"])
def test_converter_failures(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    monkeypatch.setattr(
        pdf, "find_libreoffice", lambda: None if failure == "missing" else "/mock/soffice"
    )

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 45)
        return subprocess.CompletedProcess(command, 1 if failure == "nonzero" else 0)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    with pytest.raises(pdf.PdfConversionError):
        pdf.convert_pdf(b"input", "Expected text")


@pytest.mark.parametrize(("target", "status"), [(1, "warning"), (2, "passed"), (3, "passed")])
def test_pdf_ats_reextracts_pages_and_checks_target(
    export_client: TestClient,
    snapshot: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    target: int,
    status: str,
) -> None:
    monkeypatch.setattr(pdf, "find_libreoffice", lambda: "/mock/soffice")

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        paragraphs = Document(command[-1]).paragraphs
        output = Path(command[command.index("--outdir") + 1])
        (output / "resume.pdf").write_bytes(pdf_bytes([p.text for p in paragraphs], pages=2))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    client = export_client
    version = snapshot["approved"]
    artifact = client.post(
        f"/api/v1/resume-versions/{version['id']}/export", json={"format": "pdf"}
    ).json()
    resume = client.get(f"/api/v1/resumes/{version['resume_id']}").json()
    req_path = f"/api/v1/jobs/{resume['job_id']}/requirements"
    rows = client.patch(req_path, json={"requirements": [{"text": "Python"}]}).json()
    client.patch(req_path, json={"requirements": [{**row, "confirmed": True} for row in rows]})
    # Deliberately stale cached extraction and count must not influence the report.
    engine = create_engine(settings.resolved_database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE export_files SET page_count = 999, extracted_text = ? WHERE id = ?",
                ("Cached text is wrong", artifact["id"]),
            )
    finally:
        engine.dispose()
    url = f"/api/v1/resume-versions/{version['id']}/ats"
    result = client.post(url, json={"export_id": artifact["id"], "page_target": target})
    assert result.status_code == 200
    report = result.json()
    assert report["format"] == "pdf"
    assert report["page_count"] == 2
    assert report["page_target"] == target
    assert "Improved Python reports" in report["extracted_text"]
    assert "Cached text is wrong" not in report["extracted_text"]
    assert report["requirements"][0]["status"] == "present_exact"
    checks = {row["name"]: row for row in report["formatting"]}
    assert checks["page_target"]["status"] == status
    assert checks["text_order"]["status"] == "passed"
    assert checks["selectable_text"]["status"] == "not_checked"
    assert client.post(url, json={"export_id": artifact["id"], "page_target": 0}).status_code == 422
    assert (
        client.post(url, json={"export_id": artifact["id"], "page_target": 11}).status_code == 422
    )
    path = settings.resolved_data_dir / "exports" / f"{artifact['id']}.pdf"
    path.write_bytes(b"tampered")
    assert client.post(url, json={"export_id": artifact["id"]}).status_code == 409


@pytest.mark.skipif(not pdf.find_libreoffice(), reason="LibreOffice is not installed")
def test_real_libreoffice_conversion(snapshot: dict[str, Any]) -> None:
    content, expected = render_docx(ResumeVersionOut.model_validate(snapshot["approved"]))
    converted, extracted, pages = pdf.convert_pdf(content, expected)
    assert converted.startswith(b"%PDF-")
    assert pages >= 1
    assert pdf.preserves_text(expected, extracted)


@pytest.mark.skipif(not pdf.find_libreoffice(), reason="LibreOffice is not installed")
@pytest.mark.parametrize("multipage", [False, True], ids=["symbols-and-context", "pagination"])
def test_real_libreoffice_acceptance_fixtures(multipage: bool) -> None:
    content, expected = render_docx(acceptance_version(multipage))
    converted, extracted, pages = pdf.convert_pdf(content, expected)
    assert converted.startswith(b"%PDF-")
    assert pages >= (2 if multipage else 1)
    assert pdf.preserves_text(expected, extracted)
    assert "2020-01-01" in extracted
    assert "2023-06-30" in extracted
    assert "C%2B%2B?tag=A+B#Overview" in extracted
    assert "≥30%" in extracted
    assert "≤80 ms" in extracted
    assert "−5%" in extracted
    assert "€10,000" in extracted
    preview = preview_resume(converted, "fictional-resume.pdf")
    assert preview.format == "pdf"
    assert pdf.preserves_text(expected, preview.text)
    assert any("no OCR" in warning for warning in preview.warnings)


@pytest.mark.skipif(not pdf.find_libreoffice(), reason="LibreOffice is not installed")
def test_real_pdf_export_download_and_ats(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    version = snapshot["approved"]
    response = client.post(
        f"/api/v1/resume-versions/{version['id']}/export", json={"format": "pdf"}
    )
    assert response.status_code == 201
    artifact = response.json()
    downloaded = client.get(f"/api/v1/exports/{artifact['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/pdf"
    assert sha256(downloaded.content).hexdigest() == artifact["checksum"]
    report = client.post(
        f"/api/v1/resume-versions/{version['id']}/ats",
        json={"export_id": artifact["id"], "page_target": 1},
    )
    assert report.status_code == 200
    result = report.json()
    assert result["page_count"] == artifact["page_count"] == 1
    assert "Improved Python reports by 30% with Postgres" in result["extracted_text"]
    checks = {row["name"]: row["status"] for row in result["formatting"]}
    assert checks["text_order"] == "passed"
    assert checks["page_target"] == "passed"
    assert client.get(f"/api/v1/resume-versions/{version['id']}").json() == version


def test_pdf_api_stores_extraction_pages_and_downloads(
    export_client: TestClient,
    snapshot: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf, "find_libreoffice", lambda: "/mock/soffice")

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        paragraphs = Document(command[-1]).paragraphs
        output = Path(command[command.index("--outdir") + 1])
        (output / "resume.pdf").write_bytes(pdf_bytes([p.text for p in paragraphs]))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    version_id = snapshot["approved"]["id"]
    response = export_client.post(
        f"/api/v1/resume-versions/{version_id}/export", json={"format": "pdf"}
    )
    assert response.status_code == 201
    artifact = response.json()
    assert artifact["format"] == "pdf"
    assert artifact["page_count"] == 1
    assert "Improved Python reports by 30% with Postgres" in artifact["extracted_text"]
    downloaded = export_client.get(f"/api/v1/exports/{artifact['id']}/download")
    assert downloaded.headers["content-type"] == "application/pdf"
    assert "resume.pdf" in downloaded.headers["content-disposition"]
    assert downloaded.content.startswith(b"%PDF-")
    assert len(export_client.get(f"/api/v1/resume-versions/{version_id}/exports").json()) == 1
    # Missing converter must never register an artifact or disrupt prior exports.
    monkeypatch.setattr(pdf, "find_libreoffice", lambda: None)
    failed = export_client.post(
        f"/api/v1/resume-versions/{version_id}/export", json={"format": "pdf"}
    )
    assert failed.status_code == 503
    assert "requires LibreOffice" in failed.json()["detail"]
    assert len(export_client.get(f"/api/v1/resume-versions/{version_id}/exports").json()) == 1
    assert len(list((settings.resolved_data_dir / "exports").iterdir())) == 1

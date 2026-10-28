import subprocess
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import pdf
from app.config import settings
from app.documents import render_docx
from app.schemas import ResumeVersionOut

pytest_plugins = ("test_library", "test_exports")


def pdf_bytes(lines: list[str]) -> bytes:
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


@pytest.mark.skipif(not pdf.find_libreoffice(), reason="LibreOffice is not installed")
def test_real_libreoffice_conversion(snapshot: dict[str, Any]) -> None:
    content, expected = render_docx(ResumeVersionOut.model_validate(snapshot["approved"]))
    converted, extracted, pages = pdf.convert_pdf(content, expected)
    assert converted.startswith(b"%PDF-")
    assert pages >= 1
    assert pdf.preserves_text(expected, extracted)


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

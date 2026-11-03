import os
import subprocess
import sys
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter, get_configuration
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    NameObject,
    TextStringObject,
)

from app import pdf_intake, pdf_intake_worker
from app.config import settings

pytest_plugins = ("test_library",)


def pdf_bytes(pages: list[str], password: str | None = None, mode: str = "") -> bytes:
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        operations = ["BT /F1 12 Tf 50 740 Td 16 TL"]
        for line in text.splitlines():
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            operations.append(f"({escaped}) Tj T*")
        operations.append("ET")
        stream.set_data("\n".join(operations).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password is not None:
        writer.encrypt(password)
    if mode == "javascript":
        script = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject('app.alert("not executed")'),
            }
        )
        writer.root_object[NameObject("/Names")] = DictionaryObject(
            {
                NameObject("/JavaScript"): DictionaryObject(
                    {
                        NameObject("/Names"): ArrayObject(
                            [TextStringObject("fixture"), writer._add_object(script)]
                        )
                    }
                )
            }
        )
    elif mode == "attachment":
        writer.add_attachment("not-opened.txt", b"Never saved or opened")
    elif mode == "action":
        writer.root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/Launch"),
                NameObject("/F"): TextStringObject("/not/executed"),
            }
        )
    elif mode == "xfa":
        writer.root_object[NameObject("/AcroForm")] = DictionaryObject(
            {NameObject("/XFA"): TextStringObject("not parsed")}
        )
    elif mode == "link":
        writer.add_uri(0, "http://127.0.0.1:1/never-fetched", [0, 0, 100, 100])
    elif mode == "bomb":
        encoded = EncodedStreamObject()
        encoded._data = zlib.compress(b" " * (pdf_intake_worker.MAX_STREAM_BYTES + 1))
        encoded[NameObject("/Filter")] = NameObject("/FlateDecode")
        writer.pages[0][NameObject("/Contents")] = writer._add_object(encoded)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def preview(client: TestClient, data: bytes, filename: str = "resume.pdf") -> Any:
    return client.post(
        "/api/v1/resume-intake/preview",
        params={"filename": filename},
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def test_pdf_preview_reads_order_and_is_temporary_without_verification(client: TestClient) -> None:
    before = client.get("/api/v1/dashboard").json()["counts"]
    files = set(settings.resolved_data_dir.rglob("*"))
    response = preview(
        client,
        pdf_bytes(
            [
                "Fictional Candidate\nBuilt Python services with -30% latency",
                "Reviewed C++ and A/B tests",
            ]
        ),
        "Resume.PDF",
    )
    assert response.status_code == 200
    result = response.json()
    assert result["format"] == "pdf"
    assert result["filename"] == "Resume.PDF"
    assert result["text"].index("Built Python") < result["text"].index("Reviewed C++")
    assert any("reading order" in warning for warning in result["warnings"])
    assert any("no OCR" in warning for warning in result["warnings"])
    assert any("no career records" in warning for warning in result["warnings"])
    assert client.get("/api/v1/dashboard").json()["counts"] == before
    assert set(settings.resolved_data_dir.rglob("*")) == files
    assert client.get("/api/v1/evidence").json() == []
    project = client.post("/api/v1/projects", json={"name": "Fixture source"}).json()
    claim = "Built Python services with -30% latency"
    saved = client.post(
        "/api/v1/resume-intake/drafts",
        json={
            "source_text": result["text"],
            "source_name": result["filename"],
            "claim": claim,
            "project_id": project["id"],
        },
    ).json()
    assert saved["claim"] == claim
    assert saved["state"] == "draft"
    assert saved["verified_at"] is None
    assert "Resume.PDF" in saved["source_note"]
    assert "Fictional Candidate" not in saved["source_note"]


def test_empty_text_layer_reports_ocr_and_partial_pages_warn(client: TestClient) -> None:
    response = preview(client, pdf_bytes([""]))
    assert response.status_code == 422
    assert "OCR is required" in response.json()["detail"]
    result = preview(client, pdf_bytes(["Built tools", "", "Reviewed tests"])).json()
    assert "Built tools" in result["text"] and "Reviewed tests" in result["text"]
    assert any("Pages 2 produced no readable text" in warning for warning in result["warnings"])
    assert any("may be incomplete" in warning for warning in result["warnings"])


@pytest.mark.parametrize("password", ["fixture-password", ""])
def test_password_protected_pdfs_are_rejected_without_requesting_credentials(
    client: TestClient, password: str
) -> None:
    response = preview(client, pdf_bytes(["Private fixture"], password=password))
    assert response.status_code == 422
    assert "Password-protected" in response.json()["detail"]
    assert "fixture-password" not in response.json()["detail"]


@pytest.mark.parametrize("mode", ["javascript", "attachment", "action", "xfa"])
def test_active_and_embedded_pdf_content_is_rejected(client: TestClient, mode: str) -> None:
    assert preview(client, pdf_bytes(["Fixture text"], mode=mode)).status_code == 422


def test_pdf_links_are_not_followed(client: TestClient) -> None:
    result = preview(client, pdf_bytes(["Fixture text"], mode="link"))
    assert result.status_code == 200
    assert result.json()["text"] == "Fixture text"
    assert any("not followed or executed" in warning for warning in result.json()["warnings"])


@pytest.mark.parametrize("content", [b"not pdf", b"%PDF-1.7\nbroken\n%%EOF"])
def test_malformed_pdfs_have_clear_non_ocr_errors(client: TestClient, content: bytes) -> None:
    result = preview(client, content)
    assert result.status_code == 422
    assert "OCR is required" not in result.json()["detail"]


def test_pdf_page_text_and_decompression_limits(client: TestClient) -> None:
    result = preview(client, pdf_bytes(["text"] * 21))
    assert result.status_code == 413
    assert "20-page" in result.json()["detail"]
    result = preview(client, pdf_bytes(["a" * 100001]))
    assert result.status_code == 413
    result = preview(client, pdf_bytes(["placeholder"], mode="bomb"))
    assert result.status_code == 413
    assert "safety limit" in result.json()["detail"]


def test_parser_configuration_does_not_change_parent_process() -> None:
    before = get_configuration()
    result = pdf_intake_worker.parse_pdf(pdf_bytes(["Fixture text"]))
    assert result["text"].strip() == "Fixture text"
    assert get_configuration() is before


def test_pdf_input_requires_nonsimple_content_type(client: TestClient) -> None:
    result = client.post(
        "/api/v1/resume-intake/preview?filename=resume.pdf",
        content=pdf_bytes(["Fixture"]),
        headers={"Content-Type": "text/plain"},
    )
    assert result.status_code == 415


def test_worker_timeout_and_capacity_are_retryable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker = tmp_path / "slow-worker.py"
    worker.write_text("import time\ntime.sleep(30)\n")
    monkeypatch.setattr(pdf_intake, "WORKER_SCRIPT", worker)
    monkeypatch.setattr(pdf_intake, "PDF_TIMEOUT_SECONDS", 0.1)
    result = preview(client, pdf_bytes(["Fixture text"]))
    assert result.status_code == 422
    assert "timed out" in result.json()["detail"]
    pdf_intake.PDF_WORKERS.acquire()
    pdf_intake.PDF_WORKERS.acquire()
    try:
        assert preview(client, pdf_bytes(["Fixture text"])).status_code == 503
    finally:
        pdf_intake.PDF_WORKERS.release()
        pdf_intake.PDF_WORKERS.release()


@pytest.mark.parametrize(
    "stdout",
    [b"not-json", b"{}", b"x" * (1024 * 1024 + 1), b'{"status": [], "error": "invalid status"}'],
)
def test_invalid_worker_responses_fail_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, stdout: bytes
) -> None:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert command[:3] == [sys.executable, "-I", "-B"]
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["env"] == {"PATH": os.defpath}
        assert kwargs["timeout"] == 15
        return subprocess.CompletedProcess(command, 0, stdout)

    monkeypatch.setattr(pdf_intake.subprocess, "run", run)
    assert preview(client, pdf_bytes(["Fixture text"])).status_code == 422

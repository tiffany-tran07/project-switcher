"""Optional, isolated LibreOffice conversion with PDF text-preservation checks."""

import re
import shutil
import subprocess
import unicodedata
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import settings


class PdfConversionError(Exception):
    pass


def find_libreoffice() -> str | None:
    if settings.libreoffice_path:
        return shutil.which(settings.libreoffice_path)
    return (
        shutil.which("soffice")
        or shutil.which("libreoffice")
        or shutil.which("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    )


def extract_pdf(content: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Encrypted or empty PDF")
        return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise PdfConversionError("Could not extract readable text from the PDF") from exc


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def preserves_text(expected: str, actual: str) -> bool:
    text = normalized_text(actual)
    cursor = 0
    for line in expected.splitlines():
        paragraph = normalized_text(line)
        if not paragraph:
            continue
        index = text.find(paragraph, cursor)
        if index == -1:
            return False
        cursor = index + len(paragraph)
    return True


def convert_pdf(docx: bytes, expected_text: str) -> tuple[bytes, str, int]:
    executable = find_libreoffice()
    if not executable:
        raise PdfConversionError(
            "PDF export requires LibreOffice. Install it or set LIBREOFFICE_PATH to soffice."
        )
    try:
        with TemporaryDirectory(prefix="resume-pdf-") as temporary:
            root = Path(temporary)
            source = root / "resume.docx"
            output = root / "output"
            output.mkdir()
            source.write_bytes(docx)
            result = subprocess.run(
                [
                    executable,
                    f"-env:UserInstallation={(root / 'profile').as_uri()}",
                    "--headless",
                    "--convert-to",
                    "pdf:writer_pdf_Export",
                    "--outdir",
                    str(output),
                    str(source),
                ],
                capture_output=True,
                timeout=45,
                check=False,
            )
            target = output / "resume.pdf"
            if result.returncode != 0 or not target.is_file():
                raise PdfConversionError(
                    "LibreOffice could not produce a PDF. DOCX export is still available."
                )
            if target.stat().st_size > 20 * 1024 * 1024:
                raise PdfConversionError("Generated PDF exceeds the 20 MB export limit")
            content = target.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise PdfConversionError(
            "PDF conversion timed out. DOCX export is still available."
        ) from exc
    except OSError as exc:
        raise PdfConversionError(
            "Could not run PDF conversion. Check LibreOffice and local permissions."
        ) from exc
    extracted, page_count = extract_pdf(content)
    if not preserves_text(expected_text, extracted):
        raise PdfConversionError(
            "PDF text extraction lost or reordered approved content; export was not saved."
        )
    return content, extracted, page_count

"""Bounded, preview-only DOCX/UTF-8 text intake. No AI, persistence, or verification."""

import stat
import unicodedata
import zlib
from collections.abc import Iterable, Iterator
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from docx import Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from fastapi import APIRouter, HTTPException, Query, Request
from lxml.etree import XMLSyntaxError  # type: ignore[import-untyped]
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/v1/resume-intake", tags=["resume intake"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 500
MAX_TEXT_CHARS = 100000


class IntakePreview(BaseModel):
    filename: str
    format: str
    text: str
    warnings: list[str]


def validate_package(data: bytes) -> None:
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_PACKAGE_ENTRIES:
            raise HTTPException(413, "DOCX contains too many package entries")
        if sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES:
            raise HTTPException(413, "Expanded DOCX exceeds the 32 MB limit")
        names: set[str] = set()
        for entry in entries:
            name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
            path = PurePosixPath(name)
            if (
                not name
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or "\x00" in name
                or str(path) != name
                or name in names
            ):
                raise HTTPException(422, "DOCX contains invalid or duplicate package paths")
            names.add(name)
            file_type = stat.S_IFMT(entry.external_attr >> 16)
            allowed_types = {0, stat.S_IFDIR} if entry.is_dir() else {0, stat.S_IFREG}
            if (
                file_type not in allowed_types
                or entry.flag_bits & 1
                or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
            ):
                raise HTTPException(422, "Encrypted or non-regular DOCX entries are unsupported")
            lower = name.lower()
            if "vbaproject" in lower or lower.startswith("word/embeddings/"):
                raise HTTPException(422, "Macros and embedded objects are not supported")
            if lower.endswith((".xml", ".rels")):
                if entry.file_size > MAX_XML_BYTES:
                    raise HTTPException(413, "DOCX XML part exceeds the 8 MB limit")
                xml = archive.read(entry)
                # Also catch declarations in UTF-16 XML. No XML entities are needed for intake.
                markup = xml.replace(b"\x00", b"").upper()
                if b"<!DOCTYPE" in markup or b"<!ENTITY" in markup:
                    raise HTTPException(422, "DOCX XML entity declarations are unsupported")
        if not {"[Content_Types].xml", "word/document.xml"} <= names:
            raise HTTPException(422, "File is not a supported DOCX document")
        types = archive.read("[Content_Types].xml").replace(b"\x00", b"").lower()
        if (
            b"macroenabled" in types
            or b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            not in types
        ):
            raise HTTPException(422, "Only standard, macro-free DOCX documents are supported")


def checked_text(text: str) -> str:
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(413, "Extracted resume text exceeds 100,000 characters")
    if any(
        unicodedata.category(character) == "Cc" and character not in "\r\n\t" for character in text
    ):
        raise HTTPException(422, "Resume contains unsupported control characters")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise HTTPException(
            422, "No readable resume text found; paste text from the document instead"
        )
    return text


def table_lines(table: Table) -> Iterator[str]:
    # Visit physical XML cells once, without expanding merged-cell grid spans.
    for row in table._tbl.tr_lst:
        values = [_Cell(cell, table).text for cell in row.tc_lst]
        if any(value.strip() for value in values):
            yield " | ".join(values)


def preview_resume(data: bytes, filename: str) -> IntakePreview:
    if not data:
        raise HTTPException(422, "Resume file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Resume file exceeds the 5 MB limit")
    format = PurePosixPath(filename).suffix.casefold()
    warnings = ["Preview only: no career records are created or marked verified."]
    try:
        if format == ".txt":
            text = checked_text(data.decode("utf-8-sig"))
        elif format == ".docx":
            validate_package(data)
            document = Document(BytesIO(data))
            lines: list[str] = []
            length = 0
            tables = False
            paragraphs: Iterable[str]
            for block in document.iter_inner_content():
                if isinstance(block, Paragraph):
                    paragraphs = [block.text]
                elif isinstance(block, Table):
                    tables = True
                    paragraphs = table_lines(block)
                else:
                    continue
                for paragraph in paragraphs:
                    length += len(paragraph) + 1
                    if length > MAX_TEXT_CHARS:
                        raise HTTPException(413, "Extracted resume text exceeds 100,000 characters")
                    if paragraph.strip():
                        lines.append(paragraph)
            text = checked_text("\n".join(lines))
            warnings.append(
                "Headers, footers, text boxes, images, and nested tables may be omitted."
            )
            if tables:
                warnings.append(
                    "Tables detected: check cell order, merged cells, and duplicated text manually."
                )
        else:
            raise HTTPException(
                422, "Choose a .docx or UTF-8 .txt file; PDF intake is not available yet"
            )
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Text files must use UTF-8 encoding") from exc
    except (BadZipFile, KeyError, ValueError, XMLSyntaxError, RuntimeError, zlib.error) as exc:
        raise HTTPException(
            422, "Could not read the resume as a standard DOCX or UTF-8 text file"
        ) from exc
    return IntakePreview(filename=filename, format=format.lstrip("."), text=text, warnings=warnings)


@router.post("/preview", response_model=IntakePreview)
async def preview_upload(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
) -> IntakePreview:
    if (
        "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or any(unicodedata.category(char) == "Cc" for char in filename)
    ):
        raise HTTPException(422, "Use a filename, not a filesystem path")
    if PurePosixPath(filename).suffix.casefold() not in {".docx", ".txt"}:
        raise HTTPException(
            422, "Choose a .docx or UTF-8 .txt file; PDF intake is not available yet"
        )
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Resume file exceeds the 5 MB limit")
        chunks.extend(chunk)
    return await run_in_threadpool(preview_resume, bytes(chunks), filename)

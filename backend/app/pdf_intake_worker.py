"""Isolated text-only PDF reader. No app settings, database, OCR, rendering, or saved uploads."""

import json
import os
import sys
from io import BytesIO
from typing import Any

MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT_CHARS = 100000
MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_CONTENT_BYTES = 32 * 1024 * 1024


class PreviewError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def parse_pdf(data: bytes) -> dict[str, Any]:
    from pypdf import PdfReader, apply_configuration
    from pypdf.errors import LimitReachedError

    if not data or len(data) > MAX_INPUT_BYTES:
        raise PreviewError(413, "PDF exceeds the 5 MB intake limit")
    if not data.startswith(b"%PDF-"):
        raise PreviewError(422, "File is not a standard PDF document")
    try:
        with apply_configuration(
            maximum_declared_stream_length=MAX_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_STREAM_BYTES,
            zlib_maximum_output_length=MAX_STREAM_BYTES,
            lzw_maximum_output_length=MAX_STREAM_BYTES,
            run_length_maximum_output_length=MAX_STREAM_BYTES,
            brotli_maximum_output_length=MAX_STREAM_BYTES,
            image_maximum_buffer_size=MAX_STREAM_BYTES,
            jbig2_maximum_output_length=MAX_STREAM_BYTES,
            jbig2dec_binary=None,
            stream_decoding_work_maximum_length=MAX_CONTENT_BYTES,
            stream_parsing_work_maximum_count=200000,
            stream_filters_maximum_length=8,
            array_maximum_element_count=10000,
            dictionary_maximum_element_count=10000,
            page_tree_maximum_entries=300,
            page_tree_maximum_depth=30,
            xform_maximum_invocations_per_extraction=256,
        ):
            reader = PdfReader(
                BytesIO(data),
                strict=True,
                root_object_recovery_limit=1000,
                xref_stream_maximum_entries=50000,
            )
            if reader.is_encrypted:
                raise PreviewError(
                    422, "Password-protected PDFs are unsupported; save an unencrypted copy locally"
                )
            root = reader.root_object
            names = root.get("/Names", {})
            if hasattr(names, "get_object"):
                names = names.get_object()
            if "/EmbeddedFiles" in names or "/JavaScript" in names or "/AF" in root:
                raise PreviewError(
                    422, "PDF embedded files and JavaScript are unsupported; export a plain PDF"
                )
            action = root.get("/OpenAction")
            if action is not None and hasattr(action, "get_object"):
                action = action.get_object()
            if "/AA" in root or (isinstance(action, dict) and action.get("/S") != "/GoTo"):
                raise PreviewError(422, "PDF document actions are unsupported; export a plain PDF")
            form = root.get("/AcroForm")
            if form is not None and "/XFA" in form.get_object():
                raise PreviewError(422, "XFA form PDFs are unsupported; export a standard text PDF")
            count = len(reader.pages)
            if count > MAX_PAGES:
                raise PreviewError(413, "PDF exceeds the 20-page intake limit")
            if not count:
                raise PreviewError(422, "PDF has no pages")
            pages: list[str] = []
            empty: list[int] = []
            content_bytes = 0
            text_chars = 0
            visited_chars = 0

            def text_budget(text: str, *_: Any) -> None:
                nonlocal visited_chars
                visited_chars += len(text)
                if visited_chars > MAX_TEXT_CHARS:
                    raise PreviewError(413, "Extracted resume text exceeds 100,000 characters")

            for index, page in enumerate(reader.pages, start=1):
                content = page.get_contents()
                if content is not None:
                    content_bytes += len(content.get_data())
                    if content_bytes > MAX_CONTENT_BYTES:
                        raise PreviewError(413, "PDF decoded page content exceeds the 32 MB limit")
                text = page.extract_text(visitor_text=text_budget) or ""
                text_chars += len(text) + 2
                if text_chars > MAX_TEXT_CHARS:
                    raise PreviewError(413, "Extracted resume text exceeds 100,000 characters")
                if not text.strip():
                    empty.append(index)
                pages.append(text)
            if not any(page.strip() for page in pages):
                raise PreviewError(
                    422,
                    "No readable PDF text layer found. The PDF may be scanned, image-only, "
                    "or blank. OCR is required for scanned content; "
                    "run OCR locally or paste reviewed text instead.",
                )
            warnings = [
                "PDF text layer only; no OCR is performed. Compare every page with the original.",
                "PDF columns, tables, headers/footers, ligatures, and reading order "
                "may be incomplete or reordered. Review dates, metrics, and symbols "
                "before selecting claims.",
                "Images and form-field values may be omitted; "
                "links and PDF actions are not followed or executed.",
            ]
            if empty:
                warnings.append(
                    f"Pages {', '.join(map(str, empty))} produced no readable text; "
                    "they may be blank or image-only. Use local OCR if these pages "
                    "contain content. This preview may be incomplete."
                )
            return {"text": "\n\n".join(pages), "warnings": warnings}
    except LimitReachedError as exc:
        raise PreviewError(
            413, "PDF parser safety limit exceeded; export a simpler PDF or paste reviewed text"
        ) from exc


def restrict_worker() -> None:
    sys.setrecursionlimit(500)
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        # Darwin does not reliably enforce address-space limits.
        # Parser budgets and timeout still apply there.
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

    def deny_external(event: str, args: tuple[Any, ...]) -> None:
        if event.startswith("socket.") or event in {
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
        }:
            raise PermissionError("Network and external processes are disabled for PDF intake")

    sys.addaudithook(deny_external)


def main() -> None:
    try:
        restrict_worker()
        result = parse_pdf(sys.stdin.buffer.read(MAX_INPUT_BYTES + 1))
    except PreviewError as exc:
        result = {"status": exc.status, "error": exc.detail}
    except MemoryError:
        result = {
            "status": 413,
            "error": "PDF exceeded available parsing memory; paste reviewed text instead",
        }
    except Exception:
        result = {
            "status": 422,
            "error": "Could not read a standard PDF within safety limits; "
            "export a simpler PDF or paste reviewed text",
        }
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()

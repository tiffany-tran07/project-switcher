"""Bounded IPC for untrusted PDF text extraction; independent of trusted PDF export parsing."""

import json
import os
import subprocess
import sys
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

WORKER_SCRIPT = Path(__file__).with_name("pdf_intake_worker.py")
PDF_TIMEOUT_SECONDS = 15
MAX_OUTPUT_BYTES = 1024 * 1024
PDF_WORKERS = BoundedSemaphore(2)


class PdfText(BaseModel):
    text: str = Field(max_length=100000)
    warnings: list[str] = Field(max_length=25)


def preview_pdf(data: bytes) -> PdfText:
    if not PDF_WORKERS.acquire(blocking=False):
        raise HTTPException(503, "PDF intake is busy; retry without clearing your current preview")
    try:
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(WORKER_SCRIPT)],
                input=data,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=PDF_TIMEOUT_SECONDS,
                check=False,
                env={"PATH": os.defpath},
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(
                422, "PDF reading timed out; export a simpler PDF or paste reviewed text"
            ) from exc
        except OSError as exc:
            raise HTTPException(
                503, "Could not start the local PDF reader; check local permissions"
            ) from exc
        if result.returncode or len(result.stdout) > MAX_OUTPUT_BYTES:
            raise HTTPException(
                422, "PDF could not be read within safety limits; paste reviewed text instead"
            )
        try:
            payload = json.loads(result.stdout)
            if isinstance(payload, dict) and "error" in payload:
                status = payload.get("status")
                raise HTTPException(
                    status if isinstance(status, int) and status in {413, 422} else 422,
                    str(payload["error"]),
                )
            return PdfText.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(
                422, "The local PDF reader returned an invalid preview; paste reviewed text"
            ) from exc
    finally:
        PDF_WORKERS.release()

"""Hardened evidence validation, metadata extraction, and private MinIO ingestion."""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.integrations.minio_client import AgentMinIOClient

MAGIC_SIGNATURES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"%PDF-": "application/pdf",
}

_EXECUTABLE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "PE/EXE executable payload rejected"),
    (b"\x7fELF", "ELF binary payload rejected"),
    (b"\xfe\xed\xfa\xce", "Mach-O binary payload rejected"),
    (b"\xfe\xed\xfa\xcf", "Mach-O binary payload rejected"),
    (b"\xca\xfe\xba\xbe", "Mach-O universal binary payload rejected"),
    (b"#!", "Shell script payload rejected"),
    (b"PK\x03\x04", "Archive/ZIP payload rejected"),
)

_SCRIPT_MARKERS: tuple[bytes, ...] = (
    b"<script",
    b"<!doctype html",
    b"<html",
    b"<svg",
    b"<?php",
    b"javascript:",
)

_DISALLOWED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".sh",
        ".ps1",
        ".js",
        ".mjs",
        ".html",
        ".htm",
        ".svg",
        ".php",
        ".py",
        ".jar",
    }
)

_PDF_VERSION_RE = re.compile(rb"^%PDF-(\d+\.\d+)")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class EvidenceValidationError(ValueError):
    """Raised when uploaded evidence fails size, magic-byte, MIME, or integrity checks."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 422,
        error_code: str = "INVALID_EVIDENCE",
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


@dataclass(slots=True)
class ValidatedEvidence:
    """Verified evidence metadata and storage key ready for MinIO/DB persistence."""

    file_name: str
    detected_mime: str
    file_size: int
    sha256_hash: str
    storage_key: str
    extracted_metadata: dict[str, Any] = field(default_factory=dict)
    verification_status: str = "VERIFIED"


def _sanitize_filename(filename: str) -> str:
    """Strip path traversal components and non-safe characters from a filename."""
    raw = (filename or "").replace("\\", "/").split("/")[-1]
    base = Path(raw).name.lstrip(".")
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("_")
    return cleaned or "evidence.bin"


def _normalize_mime(mime: str | None) -> str:
    if not mime:
        return ""
    base = mime.split(";", 1)[0].strip().lower()
    if base == "image/jpg":
        return "image/jpeg"
    return base


def _detect_magic_mime(file_bytes: bytes) -> str | None:
    for sig, mime in MAGIC_SIGNATURES.items():
        if file_bytes.startswith(sig):
            return mime
    return None


def _check_dangerous_payload(file_bytes: bytes, safe_filename: str) -> None:
    ext = Path(safe_filename).suffix.lower()
    if ext in _DISALLOWED_EXTENSIONS:
        raise EvidenceValidationError(
            f"Disallowed evidence file extension '{ext}'",
            status_code=422,
            error_code="DISALLOWED_EXTENSION",
        )

    for prefix, reason in _EXECUTABLE_SIGNATURES:
        if file_bytes.startswith(prefix):
            raise EvidenceValidationError(
                reason,
                status_code=422,
                error_code="EXECUTABLE_PAYLOAD_REJECTED",
            )

    head_lower = file_bytes[:4096].lstrip().lower()
    for marker in _SCRIPT_MARKERS:
        if marker in head_lower:
            raise EvidenceValidationError(
                "HTML/script content is not permitted in evidence uploads",
                status_code=422,
                error_code="SCRIPT_PAYLOAD_REJECTED",
            )


class EvidenceService:
    """Validates evidence bytes (magic bytes, size, Pillow/PDF structure) and stores privately."""

    def __init__(
        self,
        minio_client: AgentMinIOClient | None = None,
        *,
        max_bytes: int | None = None,
        persist_callback: Callable[[ValidatedEvidence, bytes | None], Any] | None = None,
    ) -> None:
        self.minio_client = minio_client or AgentMinIOClient()
        self.max_bytes = max_bytes if max_bytes is not None else settings.MAX_EVIDENCE_BYTES
        self._persist_callback = persist_callback

    def extract_document_metadata(
        self,
        file_bytes: bytes,
        detected_mime: str,
    ) -> tuple[dict[str, Any], str]:
        """Extract safe structural metadata and verification status without executing content."""
        if detected_mime in ("image/jpeg", "image/png"):
            try:
                with Image.open(io.BytesIO(file_bytes)) as img:
                    img.verify()
                with Image.open(io.BytesIO(file_bytes)) as img:
                    img.load()
                    fmt = (img.format or "").upper()
                    expected_fmt = "JPEG" if detected_mime == "image/jpeg" else "PNG"
                    if fmt != expected_fmt:
                        raise EvidenceValidationError(
                            f"Image format '{fmt}' does not match magic bytes '{detected_mime}'",
                            status_code=422,
                            error_code="IMAGE_FORMAT_MISMATCH",
                        )
                    metadata = {
                        "width": img.width,
                        "height": img.height,
                        "format": fmt,
                        "mode": img.mode,
                    }
                    return metadata, "VERIFIED"
            except EvidenceValidationError:
                raise
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise EvidenceValidationError(
                    f"Corrupt or invalid image evidence: {exc}",
                    status_code=422,
                    error_code="CORRUPT_IMAGE",
                ) from exc

        if detected_mime == "application/pdf":
            match = _PDF_VERSION_RE.match(file_bytes)
            pdf_version = match.group(1).decode("ascii") if match else "unknown"
            warnings: list[str] = []
            lower_pdf = file_bytes.lower()
            if b"%%eof" not in lower_pdf[-2048:]:
                warnings.append("missing_eof_marker")
            if b"/javascript" in lower_pdf or b"/js " in lower_pdf or b"<script" in lower_pdf:
                warnings.append("active_script_token_detected")
            status = "FLAGGED" if warnings else "VERIFIED"
            metadata: dict[str, Any] = {
                "pdf_version": pdf_version,
                "byte_length": len(file_bytes),
            }
            if warnings:
                metadata["warnings"] = warnings
            return metadata, status

        raise EvidenceValidationError(
            f"Unsupported evidence MIME type '{detected_mime}'",
            status_code=422,
            error_code="UNSUPPORTED_MIME",
        )

    def validate_and_prepare(
        self,
        file_bytes: bytes,
        filename: str,
        claimed_mime_type: str | None = None,
        *,
        case_id: str | None = None,
    ) -> ValidatedEvidence:
        """Validate evidence size, magic bytes, claimed MIME, and extract safe metadata."""
        if not file_bytes:
            raise EvidenceValidationError(
                "Evidence file must not be empty",
                status_code=422,
                error_code="EMPTY_EVIDENCE",
            )
        if len(file_bytes) > self.max_bytes:
            raise EvidenceValidationError(
                f"Evidence exceeds maximum allowed size of {self.max_bytes} bytes",
                status_code=422,
                error_code="EVIDENCE_TOO_LARGE",
            )

        safe_name = _sanitize_filename(filename)
        _check_dangerous_payload(file_bytes, safe_name)

        detected_mime = _detect_magic_mime(file_bytes)
        if detected_mime is None:
            raise EvidenceValidationError(
                "File magic bytes do not match an allowed JPEG, PNG, or PDF document",
                status_code=422,
                error_code="UNSUPPORTED_MAGIC_BYTES",
            )

        claimed = _normalize_mime(claimed_mime_type)
        if claimed and claimed != "application/octet-stream" and claimed != detected_mime:
            raise EvidenceValidationError(
                f"Claimed MIME type '{claimed}' does not match detected '{detected_mime}'",
                status_code=422,
                error_code="MIME_MISMATCH",
            )

        extracted_metadata, verification_status = self.extract_document_metadata(
            file_bytes,
            detected_mime,
        )
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        prefix = f"cases/{_sanitize_filename(case_id)}" if case_id else "evidence"
        storage_key = f"{prefix}/{uuid.uuid4().hex}_{safe_name}"

        return ValidatedEvidence(
            file_name=safe_name,
            detected_mime=detected_mime,
            file_size=len(file_bytes),
            sha256_hash=sha256_hash,
            storage_key=storage_key,
            extracted_metadata=extracted_metadata,
            verification_status=verification_status,
        )

    def store_evidence(
        self,
        file_bytes: bytes,
        filename: str,
        claimed_mime_type: str | None = None,
        *,
        case_id: str | None = None,
        bucket: str | None = None,
        ensure_bucket: bool = True,
    ) -> ValidatedEvidence:
        """Validate evidence bytes and upload them to the private MinIO evidence bucket."""
        validated = self.validate_and_prepare(
            file_bytes,
            filename,
            claimed_mime_type,
            case_id=case_id,
        )
        target_bucket = bucket or settings.BUCKET_EVIDENCE
        if ensure_bucket:
            self.minio_client.ensure_buckets((target_bucket,))
        self.minio_client.upload_bytes(
            target_bucket,
            validated.storage_key,
            file_bytes,
            content_type=validated.detected_mime,
        )
        if self._persist_callback is not None:
            self._persist_callback(validated, None)
        return validated

    def ingest_and_verify_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        claimed_mime_type: str | None = None,
        *,
        case_id: str | None = None,
    ) -> ValidatedEvidence:
        """Alias for `store_evidence` supporting plan naming conventions."""
        return self.store_evidence(
            file_bytes,
            filename,
            claimed_mime_type,
            case_id=case_id,
        )

    def generate_presigned_url(
        self,
        storage_key: str,
        *,
        bucket: str | None = None,
        expires_seconds: int = 300,
    ) -> str:
        """Issue a short-lived presigned GET URL for an already-stored private evidence object."""
        target_bucket = bucket or settings.BUCKET_EVIDENCE
        return self.minio_client.presigned_get_url(
            target_bucket,
            storage_key,
            expires_seconds=expires_seconds,
        )

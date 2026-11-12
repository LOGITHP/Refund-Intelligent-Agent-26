"""Customer evidence upload route (`/api/v1/returns/{return_id}/evidence`)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import (
    assert_customer_case_access,
    get_actor_shipkart_id,
    get_actor_type_label,
    get_evidence_service,
    resolve_return_case,
    serialize_evidence,
)
from app.core.security import require_roles
from app.db.base import utcnow
from app.db.models import Evidence, RefundCase, RefundTimelineEvent
from app.db.session import get_db
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService

router = APIRouter(prefix="/returns", tags=["Customer Evidence"])


@router.post("/{return_id}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_return_evidence(
    return_id: str,
    file: UploadFile = File(...),
    refund_case_id: uuid.UUID | None = Form(default=None),
    source_type: str = Form(default="CUSTOMER_UPLOAD"),
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> dict[str, Any]:
    """Validate magic bytes/SHA-256, store privately in MinIO, and persist an Evidence row."""
    return_case = resolve_return_case(db, return_id)
    assert_customer_case_access(db, return_case, actor)

    linked_refund_id = refund_case_id
    if linked_refund_id is None:
        latest_refund = db.scalar(
            select(RefundCase)
            .where(RefundCase.return_case_id == return_case.id)
            .order_by(RefundCase.opened_at.desc())
        )
        if latest_refund is not None:
            linked_refund_id = latest_refund.id

    raw_bytes = await file.read()
    validated = evidence_service.store_evidence(
        raw_bytes,
        file.filename or "evidence.bin",
        file.content_type,
        case_id=str(return_case.id),
    )

    actor_sk_id = get_actor_shipkart_id(actor)
    now = utcnow()
    evidence = Evidence(
        id=uuid.uuid4(),
        return_case_id=return_case.id,
        refund_case_id=linked_refund_id,
        shipkart_uploaded_by=actor_sk_id,
        file_name=validated.file_name,
        storage_key=validated.storage_key,
        mime_type=validated.detected_mime,
        file_size=validated.file_size,
        sha256_hash=validated.sha256_hash,
        source_type=source_type.strip().upper() or "CUSTOMER_UPLOAD",
        verification_status=validated.verification_status,
        extracted_metadata=validated.extracted_metadata,
        created_at=now,
    )
    db.add(evidence)
    db.flush()

    db.add(
        RefundTimelineEvent(
            id=uuid.uuid4(),
            return_case_id=return_case.id,
            refund_case_id=linked_refund_id,
            event_type="EVIDENCE_UPLOADED",
            source_type=get_actor_type_label(actor),
            source_reference=str(evidence.id),
            description=f"Uploaded verified evidence '{evidence.file_name}' ({evidence.mime_type}).",
            event_data={
                "evidence_id": str(evidence.id),
                "sha256_hash": evidence.sha256_hash,
                "verification_status": evidence.verification_status,
            },
            occurred_at=now,
            recorded_at=now,
            verified=True,
        )
    )
    AuditService.record_audit(
        db,
        actor_type=get_actor_type_label(actor),
        shipkart_actor_id=actor_sk_id,
        action="EVIDENCE_UPLOADED",
        resource_type="evidence",
        resource_id=evidence.id,
        after_state={
            "return_case_id": str(return_case.id),
            "mime_type": evidence.mime_type,
            "sha256_hash": evidence.sha256_hash,
            "verification_status": evidence.verification_status,
        },
    )
    db.commit()
    db.refresh(evidence)
    return serialize_evidence(evidence)


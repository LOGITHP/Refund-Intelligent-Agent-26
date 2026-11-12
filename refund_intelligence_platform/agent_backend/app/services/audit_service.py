"""Immutable audit logging service with secret/PII redaction (AUD-001)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging_redact import redact_sensitive_data
from app.db.base import utcnow
from app.db.models import AuditLog


def _sanitize_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    redacted = redact_sensitive_data(state)
    # Ensure Decimal/UUID/datetime values serialize cleanly into JSON/JSONB columns.
    return json.loads(json.dumps(redacted, default=str))


class AuditService:
    """Appends immutable, redacted audit records for state-changing operations."""

    @staticmethod
    def record_audit(
        db: Session,
        *,
        actor_type: str,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        shipkart_actor_id: int | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=uuid.uuid4(),
            actor_id=actor_id,
            shipkart_actor_id=shipkart_actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=_sanitize_state(before_state),
            after_state=_sanitize_state(after_state),
            ip_address=ip_address,
            created_at=utcnow(),
        )
        db.add(entry)
        db.flush()
        return entry

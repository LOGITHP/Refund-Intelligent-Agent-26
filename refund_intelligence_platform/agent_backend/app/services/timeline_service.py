"""Unified physical-return and financial-refund timeline service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import RefundCase, RefundTimelineEvent

_PHYSICAL_SOURCE_TYPES = frozenset(
    {
        "CARRIER",
        "CARRIER_SIMULATOR",
        "LOGISTICS",
        "WAREHOUSE",
        "INSPECTION",
        "RETURN",
        "SHIPKART_RETURN",
        "CUSTOMER_RETURN",
    }
)

_FINANCIAL_SOURCE_TYPES = frozenset(
    {
        "PAYPAL",
        "PAYPAL_API",
        "PAYPAL_WEBHOOK",
        "ISSUER",
        "ISSUER_SIMULATOR",
        "BANK",
        "MERCHANT_APPROVAL",
        "APPROVAL",
        "REFUND",
        "PAYMENT",
        "REGULATORY",
    }
)

_PHYSICAL_EVENT_PREFIXES = (
    "RETURN_",
    "PICKUP_",
    "CARRIER_",
    "SHIPMENT_",
    "PARCEL_",
    "DELIVERED_",
    "DELIVERY_",
    "INSPECTION_",
    "WAREHOUSE_",
)

_FINANCIAL_EVENT_PREFIXES = (
    "REFUND_",
    "PAYPAL_",
    "PAYMENT_",
    "CAPTURE_",
    "APPROVAL_",
    "MERCHANT_APPROVAL",
    "ISSUER_",
    "BANK_",
    "CREDIT_",
    "ARN_",
    "REGULATORY_",
)


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _classify_event_track(event: RefundTimelineEvent) -> str:
    """Classify a timeline event into PHYSICAL_RETURN or FINANCIAL_REFUND."""
    src = (event.source_type or "").strip().upper()
    evt = (event.event_type or "").strip().upper()

    if src in _PHYSICAL_SOURCE_TYPES:
        return "PHYSICAL_RETURN"
    if src in _FINANCIAL_SOURCE_TYPES:
        return "FINANCIAL_REFUND"

    if evt.startswith(_FINANCIAL_EVENT_PREFIXES):
        return "FINANCIAL_REFUND"
    if evt.startswith(_PHYSICAL_EVENT_PREFIXES):
        return "PHYSICAL_RETURN"

    if event.refund_case_id is not None and event.return_case_id is None:
        return "FINANCIAL_REFUND"
    if event.return_case_id is not None and event.refund_case_id is None:
        return "PHYSICAL_RETURN"
    return "FINANCIAL_REFUND"


def _serialize_event(event: RefundTimelineEvent) -> dict[str, Any]:
    track = _classify_event_track(event)
    return {
        "id": str(event.id),
        "return_case_id": str(event.return_case_id) if event.return_case_id else None,
        "refund_case_id": str(event.refund_case_id) if event.refund_case_id else None,
        "event_type": event.event_type,
        "source_type": event.source_type,
        "source_reference": event.source_reference,
        "description": event.description,
        "event_data": dict(event.event_data or {}),
        "occurred_at": ensure_utc(event.occurred_at).isoformat(),
        "recorded_at": ensure_utc(event.recorded_at).isoformat(),
        "verified": bool(event.verified),
        "track": track,
    }


class TimelineService:
    """Records deduplicated dual-timestamp events and builds unified timelines."""

    def record_event(
        self,
        db: Session,
        *,
        event_type: str,
        source_type: str,
        description: str,
        occurred_at: datetime,
        source_reference: str | None = None,
        return_case_id: uuid.UUID | None = None,
        refund_case_id: uuid.UUID | None = None,
        event_data: dict[str, Any] | None = None,
        verified: bool = False,
    ) -> RefundTimelineEvent:
        """Persist a timeline event, deduplicating on (source_type, source_reference)."""
        if return_case_id is None and refund_case_id is None:
            raise ValueError("At least one of return_case_id or refund_case_id must be provided.")

        clean_source_type = source_type.strip().upper()
        clean_ref = source_reference.strip() if source_reference and source_reference.strip() else None

        if clean_ref is not None:
            if refund_case_id is not None and return_case_id is not None:
                scope_clause = and_(
                    RefundTimelineEvent.refund_case_id == refund_case_id,
                    RefundTimelineEvent.return_case_id == return_case_id,
                )
            elif refund_case_id is not None:
                scope_clause = RefundTimelineEvent.refund_case_id == refund_case_id
            else:
                scope_clause = RefundTimelineEvent.return_case_id == return_case_id

            existing = db.scalar(
                select(RefundTimelineEvent).where(
                    scope_clause,
                    RefundTimelineEvent.source_type == clean_source_type,
                    RefundTimelineEvent.source_reference == clean_ref,
                )
            )
            if existing is not None:
                return existing

        event = RefundTimelineEvent(
            return_case_id=return_case_id,
            refund_case_id=refund_case_id,
            event_type=event_type.strip(),
            source_type=clean_source_type,
            source_reference=clean_ref,
            description=description,
            event_data=dict(event_data or {}),
            occurred_at=ensure_utc(occurred_at),
            recorded_at=utcnow(),
            verified=bool(verified),
        )
        db.add(event)
        db.flush()
        return event

    def get_unified_timeline(
        self,
        db: Session,
        *,
        refund_case_id: uuid.UUID | None = None,
        return_case_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Return physical return, financial refund, and merged timelines sorted by occurred_at."""
        if refund_case_id is None and return_case_id is None:
            raise ValueError("At least one of refund_case_id or return_case_id must be provided.")

        resolved_return_id = return_case_id
        linked_refund_ids: list[uuid.UUID] = []

        if refund_case_id is not None:
            linked_refund_ids.append(refund_case_id)
            if resolved_return_id is None:
                refund_case = db.get(RefundCase, refund_case_id)
                if refund_case is not None and refund_case.return_case_id is not None:
                    resolved_return_id = refund_case.return_case_id
        elif resolved_return_id is not None:
            linked_refund_ids = list(
                db.scalars(
                    select(RefundCase.id).where(RefundCase.return_case_id == resolved_return_id)
                ).all()
            )

        filters = []
        if linked_refund_ids:
            filters.append(RefundTimelineEvent.refund_case_id.in_(linked_refund_ids))
        if resolved_return_id is not None:
            filters.append(RefundTimelineEvent.return_case_id == resolved_return_id)

        events = list(
            db.scalars(select(RefundTimelineEvent).where(or_(*filters))).all()
        )
        events.sort(
            key=lambda ev: (
                ensure_utc(ev.occurred_at),
                ensure_utc(ev.recorded_at),
                str(ev.id),
            )
        )

        physical_events: list[dict[str, Any]] = []
        financial_events: list[dict[str, Any]] = []
        merged_events: list[dict[str, Any]] = []

        for ev in events:
            serialized = _serialize_event(ev)
            merged_events.append(serialized)
            if serialized["track"] == "PHYSICAL_RETURN":
                physical_events.append(serialized)
            else:
                financial_events.append(serialized)

        return {
            "refund_case_id": str(refund_case_id) if refund_case_id else None,
            "return_case_id": str(resolved_return_id) if resolved_return_id else None,
            "physical_return_events": physical_events,
            "financial_refund_events": financial_events,
            "merged_events": merged_events,
            "total_events": len(merged_events),
        }

"""Best-effort synchronization of 3-agent recommendations back to Shipkart Commerce."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_redact import redact_sensitive_data
from app.db.models import AgentDecision, AgentExecution, RefundCase
from app.integrations.shipkart_client import ShipkartBridgeClient

logger = logging.getLogger(__name__)


def _map_recommended_action(raw_action: str | None) -> str:
    action = str(raw_action or "").strip().upper()
    if action in {"QUEUE_MERCHANT_APPROVAL", "APPROVE", "APPROVED"}:
        return "APPROVE"
    if action in {"REJECT", "REJECTED", "CLOSE_REJECTED"}:
        return "REJECT"
    return "ESCALATE"


def sync_decision_to_shipkart(
    db: Session,
    refund_case: RefundCase,
    pipeline_result: dict[str, Any],
    shipkart_client: ShipkartBridgeClient | None = None,
) -> bool:
    """Push latest AI investigation recommendation to Shipkart `/returns/{id}/agent-decision` (REF-001 safe)."""
    if refund_case.shipkart_return_id is None:
        return False

    is_custom_mock = shipkart_client is not None and type(shipkart_client) is not ShipkartBridgeClient
    if not is_custom_mock and not settings.is_bridge_configured:
        return False

    client = shipkart_client or ShipkartBridgeClient()
    resolution = dict(pipeline_result.get("resolution_result") or {})
    mapped_action = _map_recommended_action(resolution.get("recommended_action"))

    latest_dec = db.scalar(
        select(AgentDecision)
        .join(AgentExecution, AgentDecision.execution_id == AgentExecution.id)
        .where(AgentExecution.case_id == refund_case.id)
        .order_by(AgentDecision.created_at.desc())
    )
    confidence = 0.85
    if latest_dec is not None and latest_dec.confidence is not None:
        try:
            confidence = max(0.0, min(1.0, float(latest_dec.confidence)))
        except (TypeError, ValueError):
            confidence = 0.85

    merchant_brief = str(resolution.get("merchant_brief") or "").strip()
    customer_expl = str(
        resolution.get("customer_explanation") or resolution.get("customer_message") or ""
    ).strip()
    rationale = str(resolution.get("rationale") or "").strip()

    parts = [p for p in (merchant_brief, rationale, customer_expl) if p]
    deduped_parts: list[str] = []
    for part in parts:
        if part not in deduped_parts:
            deduped_parts.append(part)
    reasoning = " | ".join(deduped_parts) if deduped_parts else f"AI recommendation: {mapped_action}"
    reasoning = str(redact_sensitive_data(reasoning))[:1500]

    payload: dict[str, Any] = {
        "action": mapped_action,
        "confidence_score": round(confidence, 4),
        "reasoning": reasoning,
        "execute_paypal_refund": False,  # REF-001: never bypass explicit merchant approval
        "paypal_capture_id": refund_case.paypal_capture_id,
    }

    try:
        client.post_agent_recommendation(int(refund_case.shipkart_return_id), payload)
        return True
    except Exception as exc:
        logger.warning(
            "Unable to sync AI recommendation to Shipkart return_id=%s: %s",
            refund_case.shipkart_return_id,
            redact_sensitive_data(str(exc)),
        )
        return False


"""Idempotent Celery tasks for agent runs, webhook processing, follow-ups, and reconciliation."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.graph import run_refund_intelligence_pipeline
from app.core.config import settings
from app.core.logging_redact import redact_sensitive_data
from app.db.base import utcnow
from app.db.models import RefundCase, RefundFollowup, RefundTransaction, ReturnCase
from app.db.session import SessionLocal as DefaultSessionLocal
from app.integrations.paypal_client import PayPalClient
from app.integrations.shipkart_client import ShipkartBridgeClient
from app.services.delay_service import DelayService
from app.services.eta_service import ETAService
from app.services.reconciliation_service import ReconciliationService, ShipkartPayPalRefundAdapter
from app.services.shipkart_sync_service import sync_decision_to_shipkart
from app.services.timeline_service import TimelineService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_SESSION_FACTORY_OVERRIDE: sessionmaker[Session] | None = None
_PAYPAL_CLIENT_FACTORY_OVERRIDE: Callable[[], PayPalClient] | None = None
_SHIPKART_CLIENT_FACTORY_OVERRIDE: Callable[[], ShipkartBridgeClient] | None = None

_TERMINAL_CASE_STATUSES = frozenset(
    {
        "CONFIRMED_POSTED",
        "ISSUER_POSTED",
        "REJECTED_BY_MERCHANT",
        "RETURN_REJECTED",
        "CANCELLED",
        "CLOSED_REJECTED",
        "REFUND_FAILED",
    }
)
_MAX_FOLLOWUP_ATTEMPTS = 3


def set_session_factory(factory: sessionmaker[Session] | None) -> None:
    """Override the worker SQLAlchemy session factory (used in isolated unit tests)."""
    global _SESSION_FACTORY_OVERRIDE
    _SESSION_FACTORY_OVERRIDE = factory


def set_paypal_client_factory(factory: Callable[[], PayPalClient] | None) -> None:
    """Override the PayPalClient factory (used in isolated unit tests)."""
    global _PAYPAL_CLIENT_FACTORY_OVERRIDE
    _PAYPAL_CLIENT_FACTORY_OVERRIDE = factory


def set_shipkart_client_factory(factory: Callable[[], ShipkartBridgeClient] | None) -> None:
    """Override the ShipkartBridgeClient factory (used in isolated unit tests)."""
    global _SHIPKART_CLIENT_FACTORY_OVERRIDE
    _SHIPKART_CLIENT_FACTORY_OVERRIDE = factory


def _get_session_factory() -> sessionmaker[Session]:
    return _SESSION_FACTORY_OVERRIDE or DefaultSessionLocal


def _handle_task_error(task_self: Any, task_name: str, exc: Exception) -> None:
    redacted_msg = redact_sensitive_data(str(exc))
    logger.warning("Celery task %s failed: %s", task_name, redacted_msg)
    if not celery_app.conf.task_always_eager and getattr(task_self.request, "retries", 0) < task_self.max_retries:
        raise task_self.retry(exc=exc)
    raise exc


@celery_app.task(
    bind=True,
    name="app.worker.tasks.run_agent_pipeline_task",
    max_retries=3,
    default_retry_delay=30,
)
def run_agent_pipeline_task(
    self: Any,
    refund_case_id: str,
    customer_query: str | None = None,
) -> dict[str, Any]:
    """Run the 3-agent LangGraph pipeline for a RefundCase."""
    factory = _get_session_factory()
    db = factory()
    try:
        result = run_refund_intelligence_pipeline(
            db,
            refund_case_id,
            customer_query=customer_query,
        )
        try:
            case_uuid = uuid.UUID(str(result.get("refund_case_id") or refund_case_id))
            refund_case = db.get(RefundCase, case_uuid)
            if refund_case is not None:
                sk_client = (
                    _SHIPKART_CLIENT_FACTORY_OVERRIDE()
                    if _SHIPKART_CLIENT_FACTORY_OVERRIDE is not None
                    else None
                )
                sync_decision_to_shipkart(db, refund_case, result, shipkart_client=sk_client)
        except Exception as sync_exc:
            logger.warning("Post-pipeline Shipkart sync skipped: %s", redact_sensitive_data(str(sync_exc)))
        return {
            "status": "COMPLETED",
            "refund_case_id": str(result.get("refund_case_id") or refund_case_id),
            "case_status": result.get("status"),
            "recommended_action": (result.get("resolution_result") or {}).get("recommended_action"),
        }
    except Exception as exc:
        db.rollback()
        _handle_task_error(self, "run_agent_pipeline_task", exc)
        return {}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.worker.tasks.process_webhook_event_task",
    max_retries=3,
    default_retry_delay=30,
)
def process_webhook_event_task(
    self: Any,
    provider_event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Idempotently process a PayPal webhook payload in the background."""
    factory = _get_session_factory()
    db = factory()
    try:
        reconciler = ReconciliationService()
        result = reconciler.process_paypal_webhook(
            db,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload=redact_sensitive_data(payload),
        )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        _handle_task_error(self, "process_webhook_event_task", exc)
        return {}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.worker.tasks.poll_due_followups_task",
    max_retries=3,
    default_retry_delay=30,
)
def poll_due_followups_task(self: Any) -> dict[str, Any]:
    """Execute scheduled RefundFollowup rows whose scheduled_at <= now()."""
    factory = _get_session_factory()
    db = factory()
    try:
        now = utcnow()
        due_followups = list(
            db.scalars(
                select(RefundFollowup)
                .where(
                    RefundFollowup.status == "SCHEDULED",
                    RefundFollowup.scheduled_at <= now,
                )
                .order_by(RefundFollowup.scheduled_at.asc())
            ).all()
        )

        delay_svc = DelayService()
        eta_svc = ETAService()
        executed_count = 0
        rescheduled_count = 0

        for followup in due_followups:
            refund_case = db.get(RefundCase, followup.refund_case_id)
            followup.attempt_count = int(followup.attempt_count or 0) + 1
            followup.last_attempt_at = now

            if refund_case is None or (refund_case.status or "").upper() in _TERMINAL_CASE_STATUSES:
                followup.status = "EXECUTED"
                executed_count += 1
                continue

            delay_report = delay_svc.evaluate_delays(db, refund_case.id, as_of=now)
            eta_svc.compute_and_persist_eta(db, refund_case.id, estimated_from=now)

            has_delays = bool(delay_report.get("delays"))
            if not has_delays or followup.attempt_count >= _MAX_FOLLOWUP_ATTEMPTS:
                followup.status = "EXECUTED"
                executed_count += 1
            else:
                followup.status = "SCHEDULED"
                followup.scheduled_at = now + timedelta(hours=4)
                rescheduled_count += 1

        db.commit()
        return {
            "processed": len(due_followups),
            "executed": executed_count,
            "rescheduled": rescheduled_count,
        }
    except Exception as exc:
        db.rollback()
        _handle_task_error(self, "poll_due_followups_task", exc)
        return {}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.worker.tasks.reconcile_pending_paypal_refunds_task",
    max_retries=3,
    default_retry_delay=30,
)
def reconcile_pending_paypal_refunds_task(self: Any) -> dict[str, Any]:
    """Poll PayPal API or Shipkart merchant bridge for PENDING RefundTransaction rows and reconcile changes."""
    use_paypal = _PAYPAL_CLIENT_FACTORY_OVERRIDE is not None or settings.is_paypal_configured
    use_shipkart_bridge = not use_paypal and (
        _SHIPKART_CLIENT_FACTORY_OVERRIDE is not None
        or bool(settings.SERVICE_JWT_SECRET.strip())
    )
    if not use_paypal and not use_shipkart_bridge:
        return {
            "skipped": True,
            "reason": "paypal_not_configured",
            "checked": 0,
            "reconciled": 0,
        }

    factory = _get_session_factory()
    db = factory()
    try:
        reconciler = ReconciliationService()
        pending_txs = list(
            db.scalars(
                select(RefundTransaction)
                .where(RefundTransaction.status == "PENDING")
                .order_by(RefundTransaction.created_at.asc())
            ).all()
        )

        checked_count = 0
        reconciled_count = 0

        if use_paypal:
            client = (
                _PAYPAL_CLIENT_FACTORY_OVERRIDE()
                if _PAYPAL_CLIENT_FACTORY_OVERRIDE is not None
                else PayPalClient()
            )
            for tx in pending_txs:
                checked_count += 1
                before_status = tx.status
                reconciler.reconcile_pending_refund_transaction(db, tx, client)
                if tx.status != before_status:
                    reconciled_count += 1
        else:
            shipkart_client = (
                _SHIPKART_CLIENT_FACTORY_OVERRIDE()
                if _SHIPKART_CLIENT_FACTORY_OVERRIDE is not None
                else ShipkartBridgeClient()
            )
            for tx in pending_txs:
                refund_case = db.get(RefundCase, tx.refund_case_id)
                shipkart_return_id = (
                    refund_case.shipkart_return_id if refund_case is not None else None
                )
                if (
                    shipkart_return_id is None
                    and refund_case is not None
                    and refund_case.return_case_id is not None
                ):
                    ret_case = db.get(ReturnCase, refund_case.return_case_id)
                    if ret_case is not None:
                        shipkart_return_id = ret_case.shipkart_return_id
                if shipkart_return_id is None:
                    continue
                checked_count += 1
                before_status = tx.status
                adapter = ShipkartPayPalRefundAdapter(shipkart_client, shipkart_return_id)
                reconciler.reconcile_pending_refund_transaction(db, tx, adapter)
                if tx.status != before_status:
                    reconciled_count += 1

        db.commit()
        return {
            "skipped": False,
            "mode": "paypal_direct" if use_paypal else "shipkart_bridge",
            "checked": checked_count,
            "reconciled": reconciled_count,
        }
    except Exception as exc:
        db.rollback()
        _handle_task_error(self, "reconcile_pending_paypal_refunds_task", exc)
        return {}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.worker.tasks.detect_overdue_cases_task",
    max_retries=3,
    default_retry_delay=30,
)
def detect_overdue_cases_task(self: Any) -> dict[str, Any]:
    """Evaluate active RefundCases for DELAY-001..DELAY-006 breaches and refresh ETAs."""
    factory = _get_session_factory()
    db = factory()
    try:
        now = utcnow()
        active_cases = list(
            db.scalars(
                select(RefundCase)
                .where(RefundCase.status.notin_(list(_TERMINAL_CASE_STATUSES)))
                .order_by(RefundCase.opened_at.asc())
            ).all()
        )

        delay_svc = DelayService()
        eta_svc = ETAService()
        timeline_svc = TimelineService()

        overdue_cases = 0
        breaches_detected = 0

        for refund_case in active_cases:
            report = delay_svc.evaluate_delays(db, refund_case.id, as_of=now)
            delays = list(report.get("delays") or [])
            if delays:
                overdue_cases += 1
                for delay in delays:
                    breaches_detected += 1
                    rule_code = str(delay.get("rule_code") or "DELAY")
                    timeline_svc.record_event(
                        db,
                        refund_case_id=refund_case.id,
                        return_case_id=refund_case.return_case_id,
                        event_type=f"SLA_BREACH_{rule_code}",
                        source_type="DELAY_MONITOR",
                        source_reference=f"{refund_case.id}:{rule_code}",
                        description=str(delay.get("description") or f"Delay detected ({rule_code})."),
                        occurred_at=now,
                        event_data=delay,
                        verified=True,
                    )
            eta_svc.compute_and_persist_eta(db, refund_case.id, estimated_from=now)

        db.commit()
        return {
            "evaluated": len(active_cases),
            "overdue_cases": overdue_cases,
            "breaches_detected": breaches_detected,
        }
    except Exception as exc:
        db.rollback()
        _handle_task_error(self, "detect_overdue_cases_task", exc)
        return {}
    finally:
        db.close()

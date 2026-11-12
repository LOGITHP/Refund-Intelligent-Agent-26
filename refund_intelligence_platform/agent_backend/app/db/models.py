import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.db.types import GUID, INETVariant, JSONBVariant


class ReturnCase(Base):
    __tablename__ = "return_cases"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    # Shipkart integer cross-platform mapping keys
    shipkart_return_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    shipkart_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shipkart_customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shipkart_merchant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="RETURN_REQUESTED")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    items: Mapped[list["ReturnCaseItem"]] = relationship(
        back_populates="return_case", cascade="all, delete-orphan"
    )
    shipments: Mapped[list["ReturnShipment"]] = relationship(
        back_populates="return_case", cascade="all, delete-orphan"
    )
    inspections: Mapped[list["ReturnInspection"]] = relationship(
        back_populates="return_case", cascade="all, delete-orphan"
    )
    refund_cases: Mapped[list["RefundCase"]] = relationship(back_populates="return_case")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="return_case")
    timeline_events: Mapped[list["RefundTimelineEvent"]] = relationship(back_populates="return_case")

    __table_args__ = (
        Index("ix_return_cases_merchant_status_created", "merchant_id", "status", "created_at"),
        Index("ix_return_cases_customer_created", "customer_id", "created_at"),
        Index("ix_return_cases_sk_merchant_status_created", "shipkart_merchant_id", "status", "created_at"),
    )


class ReturnCaseItem(Base):
    __tablename__ = "return_case_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    return_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("return_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    shipkart_order_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    quantity_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_approved: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_reported: Mapped[str] = mapped_column(String(40), nullable=False, default="UNKNOWN")
    condition_inspected: Mapped[str | None] = mapped_column(String(40), nullable=True)
    refund_amount_requested: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    refund_amount_approved: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    return_case: Mapped["ReturnCase"] = relationship(back_populates="items")


class ReturnShipment(Base):
    __tablename__ = "return_shipments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    return_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("return_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    carrier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(150), nullable=False)
    carrier_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PICKUP_SCHEDULED")
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pickup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    return_case: Mapped["ReturnCase"] = relationship(back_populates="shipments")

    __table_args__ = (
        Index("ix_return_shipments_carrier_tracking", "carrier_name", "tracking_number"),
    )


class ReturnInspection(Base):
    __tablename__ = "return_inspections"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    return_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("return_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    shipkart_inspector_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    inspection_status: Mapped[str] = mapped_column(String(40), nullable=False, default="INSPECTION_PENDING")
    condition_result: Mapped[str] = mapped_column(String(40), nullable=False, default="UNKNOWN")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    return_case: Mapped["ReturnCase"] = relationship(back_populates="inspections")


class RefundCase(Base):
    __tablename__ = "refund_cases"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    return_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("return_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    shipkart_return_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shipkart_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shipkart_customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shipkart_merchant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    case_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="INVESTIGATING")
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    captured_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    original_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="INR")
    paypal_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    paypal_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    return_case: Mapped["ReturnCase | None"] = relationship(back_populates="refund_cases")
    transactions: Mapped[list["RefundTransaction"]] = relationship(
        back_populates="refund_case", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["RefundApproval"]] = relationship(
        back_populates="refund_case", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="refund_case")
    timeline_events: Mapped[list["RefundTimelineEvent"]] = relationship(back_populates="refund_case")
    eta_estimates: Mapped[list["RefundEtaEstimate"]] = relationship(
        back_populates="refund_case", cascade="all, delete-orphan"
    )
    followups: Mapped[list["RefundFollowup"]] = relationship(
        back_populates="refund_case", cascade="all, delete-orphan"
    )
    issuer_inquiries: Mapped[list["IssuerInquiry"]] = relationship(
        back_populates="refund_case", cascade="all, delete-orphan"
    )
    regulatory_evaluations: Mapped[list["RegulatoryEvaluation"]] = relationship(back_populates="refund_case")
    compliance_violations: Mapped[list["ComplianceViolation"]] = relationship(back_populates="refund_case")

    __table_args__ = (
        Index("ix_refund_cases_merchant_status_opened", "merchant_id", "status", "opened_at"),
        Index("ix_refund_cases_customer_opened", "customer_id", "opened_at"),
        Index("ix_refund_cases_sk_merchant_status_opened", "shipkart_merchant_id", "status", "opened_at"),
    )


class RefundTransaction(Base):
    __tablename__ = "refund_transactions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_record_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paypal_capture_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    paypal_refund_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    paypal_response: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant(), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    refund_case: Mapped["RefundCase"] = relationship(back_populates="transactions")


class RefundApproval(Base):
    __tablename__ = "refund_approvals"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=False
    )
    merchant_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    shipkart_merchant_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1.0")
    approval_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    refund_case: Mapped["RefundCase"] = relationship(back_populates="approvals")

    __table_args__ = (
        Index("ix_refund_approvals_case_created", "refund_case_id", "created_at"),
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    return_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("return_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    refund_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    shipkart_uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False, default="UNVERIFIED")
    extracted_metadata: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    return_case: Mapped["ReturnCase | None"] = relationship(back_populates="evidence_items")
    refund_case: Mapped["RefundCase | None"] = relationship(back_populates="evidence_items")


class RefundTimelineEvent(Base):
    __tablename__ = "refund_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    return_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("return_cases.id", ondelete="CASCADE"), nullable=True
    )
    refund_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    return_case: Mapped["ReturnCase | None"] = relationship(back_populates="timeline_events")
    refund_case: Mapped["RefundCase | None"] = relationship(back_populates="timeline_events")

    __table_args__ = (
        Index("ix_refund_timeline_events_refund_occurred", "refund_case_id", "occurred_at"),
        Index("ix_refund_timeline_events_return_occurred", "return_case_id", "occurred_at"),
    )


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    case_type: Mapped[str] = mapped_column(String(30), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RUNNING")
    input_reference: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)

    decisions: Mapped[list["AgentDecision"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_agent_executions_case_agent_started", "case_id", "agent_name", "started_at"),
    )


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_type: Mapped[str] = mapped_column(String(60), nullable=False)
    recommendation: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    evidence_references: Mapped[list[Any]] = mapped_column(JSONBVariant(), nullable=False, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    decision_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PROPOSED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    execution: Mapped["AgentExecution"] = relationship(back_populates="decisions")


class RefundEtaEstimate(Base):
    __tablename__ = "refund_eta_estimates"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    eta_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_ESTIMABLE")
    estimated_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    earliest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence_level: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW")
    basis: Mapped[list[Any]] = mapped_column(JSONBVariant(), nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    refund_case: Mapped["RefundCase"] = relationship(back_populates="eta_estimates")


class RefundFollowup(Base):
    __tablename__ = "refund_followups"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="SCHEDULED")
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    refund_case: Mapped["RefundCase"] = relationship(back_populates="followups")


class IssuerInquiry(Base):
    __tablename__ = "issuer_inquiries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_type: Mapped[str] = mapped_column(String(30), nullable=False, default="SIMULATOR")
    provider_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    institution_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING")
    request_data: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    response_data: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    refund_case: Mapped["RefundCase"] = relationship(back_populates="issuer_inquiries")


class RegulatoryEvaluation(Base):
    __tablename__ = "regulatory_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    jurisdiction: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_context: Mapped[dict[str, Any]] = mapped_column(JSONBVariant(), nullable=False, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    matched_rules: Mapped[list[Any]] = mapped_column(JSONBVariant(), nullable=False, default=list)
    unresolved_questions: Mapped[list[Any]] = mapped_column(JSONBVariant(), nullable=False, default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    refund_case: Mapped["RefundCase | None"] = relationship(back_populates="regulatory_evaluations")


class ComplianceViolation(Base):
    __tablename__ = "compliance_violations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    refund_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("refund_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    refund_case: Mapped["RefundCase | None"] = relationship(back_populates="compliance_violations")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    shipkart_actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant(), nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant(), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INETVariant(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        Index("ix_audit_logs_resource_created", "resource_type", "resource_id", "created_at"),
    )


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(150), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(30), nullable=False, default="RECEIVED")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_processed_webhook_provider_event"),
    )


class PlatformUser(Base):
    """Dedicated platform operations account (decoupled from Shipkart merchant/customer accounts)."""

    __tablename__ = "platform_users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, default="Platform Operator")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="operations")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# ORM-Level Immutability Enforcement for RefundApproval and AuditLog
# ---------------------------------------------------------------------------
@event.listens_for(RefundApproval, "before_update")
def _prevent_refund_approval_update(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("RefundApproval records are immutable and cannot be updated.")


@event.listens_for(RefundApproval, "before_delete")
def _prevent_refund_approval_delete(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("RefundApproval records are immutable and cannot be deleted.")


@event.listens_for(AuditLog, "before_update")
def _prevent_audit_log_update(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("AuditLog records are immutable and cannot be updated.")


@event.listens_for(AuditLog, "before_delete")
def _prevent_audit_log_delete(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("AuditLog records are immutable and cannot be deleted.")

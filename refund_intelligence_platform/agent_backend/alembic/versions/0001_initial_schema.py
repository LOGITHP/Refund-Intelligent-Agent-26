"""initial schema with 18 blueprint tables and immutability triggers

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-12 06:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. return_cases
    op.create_table(
        "return_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_return_id", sa.Integer(), nullable=True),
        sa.Column("shipkart_order_id", sa.Integer(), nullable=True),
        sa.Column("shipkart_customer_id", sa.Integer(), nullable=True),
        sa.Column("shipkart_merchant_id", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("customer_description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_return_cases_order_id", "return_cases", ["order_id"])
    op.create_index("ix_return_cases_customer_id", "return_cases", ["customer_id"])
    op.create_index("ix_return_cases_merchant_id", "return_cases", ["merchant_id"])
    op.create_index("ix_return_cases_shipkart_return_id", "return_cases", ["shipkart_return_id"], unique=True)
    op.create_index("ix_return_cases_shipkart_order_id", "return_cases", ["shipkart_order_id"])
    op.create_index("ix_return_cases_shipkart_customer_id", "return_cases", ["shipkart_customer_id"])
    op.create_index("ix_return_cases_shipkart_merchant_id", "return_cases", ["shipkart_merchant_id"])
    op.create_index("ix_return_cases_merchant_status_created", "return_cases", ["merchant_id", "status", "created_at"])
    op.create_index("ix_return_cases_customer_created", "return_cases", ["customer_id", "created_at"])
    op.create_index("ix_return_cases_sk_merchant_status_created", "return_cases", ["shipkart_merchant_id", "status", "created_at"])

    # 2. return_case_items
    op.create_table(
        "return_case_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "return_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("return_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_order_item_id", sa.Integer(), nullable=True),
        sa.Column("quantity_requested", sa.Integer(), nullable=False),
        sa.Column("quantity_approved", sa.Integer(), nullable=True),
        sa.Column("condition_reported", sa.String(length=40), nullable=False),
        sa.Column("condition_inspected", sa.String(length=40), nullable=True),
        sa.Column("refund_amount_requested", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("refund_amount_approved", sa.Numeric(precision=18, scale=2), nullable=True),
    )
    op.create_index("ix_return_case_items_return_case_id", "return_case_items", ["return_case_id"])
    op.create_index("ix_return_case_items_order_item_id", "return_case_items", ["order_item_id"])
    op.create_index("ix_return_case_items_shipkart_order_item_id", "return_case_items", ["shipkart_order_item_id"])

    # 3. return_shipments
    op.create_table(
        "return_shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "return_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("return_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("carrier_name", sa.String(length=100), nullable=False),
        sa.Column("tracking_number", sa.String(length=150), nullable=False),
        sa.Column("carrier_reference", sa.String(length=150), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("pickup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_return_shipments_return_case_id", "return_shipments", ["return_case_id"])
    op.create_index("ix_return_shipments_carrier_tracking", "return_shipments", ["carrier_name", "tracking_number"])

    # 4. return_inspections
    op.create_table(
        "return_inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "return_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("return_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("inspector_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_inspector_id", sa.Integer(), nullable=True),
        sa.Column("inspection_status", sa.String(length=40), nullable=False),
        sa.Column("condition_result", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_return_inspections_return_case_id", "return_inspections", ["return_case_id"])
    op.create_index("ix_return_inspections_shipkart_inspector_id", "return_inspections", ["shipkart_inspector_id"])

    # 5. refund_cases
    op.create_table(
        "refund_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "return_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("return_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_return_id", sa.Integer(), nullable=True),
        sa.Column("shipkart_order_id", sa.Integer(), nullable=True),
        sa.Column("shipkart_customer_id", sa.Integer(), nullable=True),
        sa.Column("shipkart_merchant_id", sa.Integer(), nullable=True),
        sa.Column("case_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("requested_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("approved_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("captured_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("original_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("paypal_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("paypal_order_id", sa.String(length=100), nullable=True),
        sa.Column("paypal_capture_id", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refund_cases_return_case_id", "refund_cases", ["return_case_id"])
    op.create_index("ix_refund_cases_order_id", "refund_cases", ["order_id"])
    op.create_index("ix_refund_cases_customer_id", "refund_cases", ["customer_id"])
    op.create_index("ix_refund_cases_merchant_id", "refund_cases", ["merchant_id"])
    op.create_index("ix_refund_cases_shipkart_return_id", "refund_cases", ["shipkart_return_id"])
    op.create_index("ix_refund_cases_shipkart_order_id", "refund_cases", ["shipkart_order_id"])
    op.create_index("ix_refund_cases_shipkart_customer_id", "refund_cases", ["shipkart_customer_id"])
    op.create_index("ix_refund_cases_shipkart_merchant_id", "refund_cases", ["shipkart_merchant_id"])
    op.create_index("ix_refund_cases_paypal_order_id", "refund_cases", ["paypal_order_id"])
    op.create_index("ix_refund_cases_paypal_capture_id", "refund_cases", ["paypal_capture_id"])
    op.create_index("ix_refund_cases_merchant_status_opened", "refund_cases", ["merchant_id", "status", "opened_at"])
    op.create_index("ix_refund_cases_customer_opened", "refund_cases", ["customer_id", "opened_at"])
    op.create_index("ix_refund_cases_sk_merchant_status_opened", "refund_cases", ["shipkart_merchant_id", "status", "opened_at"])

    # 6. refund_transactions
    op.create_table(
        "refund_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payment_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paypal_order_id", sa.String(length=100), nullable=True),
        sa.Column("paypal_capture_id", sa.String(length=100), nullable=False),
        sa.Column("paypal_refund_id", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=150), nullable=False),
        sa.Column("paypal_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_refund_transactions_idempotency_key"),
        sa.UniqueConstraint("paypal_refund_id", name="uq_refund_transactions_paypal_refund_id"),
    )
    op.create_index("ix_refund_transactions_refund_case_id", "refund_transactions", ["refund_case_id"])
    op.create_index("ix_refund_transactions_paypal_capture_id", "refund_transactions", ["paypal_capture_id"])

    # 7. refund_approvals (immutable)
    op.create_table(
        "refund_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("merchant_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_merchant_user_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("approved_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("approval_reference", sa.String(length=150), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refund_approvals_shipkart_merchant_user_id", "refund_approvals", ["shipkart_merchant_user_id"])
    op.create_index("ix_refund_approvals_case_created", "refund_approvals", ["refund_case_id", "created_at"])

    # 8. evidence
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "return_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("return_cases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_uploaded_by", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("extracted_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_return_case_id", "evidence", ["return_case_id"])
    op.create_index("ix_evidence_refund_case_id", "evidence", ["refund_case_id"])
    op.create_index("ix_evidence_shipkart_uploaded_by", "evidence", ["shipkart_uploaded_by"])
    op.create_index("ix_evidence_sha256_hash", "evidence", ["sha256_hash"])

    # 9. refund_timeline_events
    op.create_table(
        "refund_timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "return_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("return_cases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_reference", sa.String(length=150), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_refund_timeline_events_refund_occurred", "refund_timeline_events", ["refund_case_id", "occurred_at"])
    op.create_index("ix_refund_timeline_events_return_occurred", "refund_timeline_events", ["return_case_id", "occurred_at"])

    # 10. agent_executions
    op.create_table(
        "agent_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_type", sa.String(length=30), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
    )
    op.create_index("ix_agent_executions_case_id", "agent_executions", ["case_id"])
    op.create_index("ix_agent_executions_case_agent_started", "agent_executions", ["case_id", "agent_name", "started_at"])

    # 11. agent_decisions
    op.create_table(
        "agent_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_type", sa.String(length=60), nullable=False),
        sa.Column("recommendation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("decision_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_decisions_execution_id", "agent_decisions", ["execution_id"])

    # 12. refund_eta_estimates
    op.create_table(
        "refund_eta_estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("eta_status", sa.String(length=30), nullable=False),
        sa.Column("estimated_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("earliest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence_level", sa.String(length=20), nullable=False),
        sa.Column("basis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refund_eta_estimates_refund_case_id", "refund_eta_estimates", ["refund_case_id"])

    # 13. refund_followups
    op.create_table(
        "refund_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_reference", sa.String(length=150), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refund_followups_refund_case_id", "refund_followups", ["refund_case_id"])

    # 14. issuer_inquiries
    op.create_table(
        "issuer_inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_type", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=150), nullable=True),
        sa.Column("institution_code", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("request_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_issuer_inquiries_refund_case_id", "issuer_inquiries", ["refund_case_id"])

    # 15. regulatory_evaluations
    op.create_table(
        "regulatory_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("jurisdiction", sa.CHAR(length=2), nullable=False),
        sa.Column("evaluation_status", sa.String(length=40), nullable=False),
        sa.Column("transaction_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("matched_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unresolved_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_regulatory_evaluations_refund_case_id", "regulatory_evaluations", ["refund_case_id"])

    # 16. compliance_violations
    op.create_table(
        "compliance_violations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "refund_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refund_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rule_code", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_compliance_violations_refund_case_id", "compliance_violations", ["refund_case_id"])
    op.create_index("ix_compliance_violations_rule_code", "compliance_violations", ["rule_code"])

    # 17. audit_logs (immutable)
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipkart_actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_shipkart_actor_id", "audit_logs", ["shipkart_actor_id"])
    op.create_index("ix_audit_logs_resource_created", "audit_logs", ["resource_type", "resource_id", "created_at"])

    # 18. processed_webhook_events
    op.create_table(
        "processed_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_event_id", sa.String(length=150), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_processed_webhook_provider_event"),
    )

    # PostgreSQL DB-level immutability enforcement for refund_approvals and audit_logs
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_immutable_table_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table % is immutable and does not allow % operations', TG_TABLE_NAME, TG_OP;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_refund_approvals_immutable
            BEFORE UPDATE OR DELETE ON refund_approvals
            FOR EACH ROW EXECUTE FUNCTION prevent_immutable_table_mutation()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_logs_immutable
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_immutable_table_mutation()
            """
        )


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs")
        op.execute("DROP TRIGGER IF EXISTS trg_refund_approvals_immutable ON refund_approvals")
        op.execute("DROP FUNCTION IF EXISTS prevent_immutable_table_mutation()")

    op.drop_table("processed_webhook_events")
    op.drop_index("ix_audit_logs_resource_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_shipkart_actor_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_compliance_violations_rule_code", table_name="compliance_violations")
    op.drop_index("ix_compliance_violations_refund_case_id", table_name="compliance_violations")
    op.drop_table("compliance_violations")
    op.drop_index("ix_regulatory_evaluations_refund_case_id", table_name="regulatory_evaluations")
    op.drop_table("regulatory_evaluations")
    op.drop_index("ix_issuer_inquiries_refund_case_id", table_name="issuer_inquiries")
    op.drop_table("issuer_inquiries")
    op.drop_index("ix_refund_followups_refund_case_id", table_name="refund_followups")
    op.drop_table("refund_followups")
    op.drop_index("ix_refund_eta_estimates_refund_case_id", table_name="refund_eta_estimates")
    op.drop_table("refund_eta_estimates")
    op.drop_index("ix_agent_decisions_execution_id", table_name="agent_decisions")
    op.drop_table("agent_decisions")
    op.drop_index("ix_agent_executions_case_agent_started", table_name="agent_executions")
    op.drop_index("ix_agent_executions_case_id", table_name="agent_executions")
    op.drop_table("agent_executions")
    op.drop_index("ix_refund_timeline_events_return_occurred", table_name="refund_timeline_events")
    op.drop_index("ix_refund_timeline_events_refund_occurred", table_name="refund_timeline_events")
    op.drop_table("refund_timeline_events")
    op.drop_index("ix_evidence_sha256_hash", table_name="evidence")
    op.drop_index("ix_evidence_shipkart_uploaded_by", table_name="evidence")
    op.drop_index("ix_evidence_refund_case_id", table_name="evidence")
    op.drop_index("ix_evidence_return_case_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_refund_approvals_case_created", table_name="refund_approvals")
    op.drop_index("ix_refund_approvals_shipkart_merchant_user_id", table_name="refund_approvals")
    op.drop_table("refund_approvals")
    op.drop_index("ix_refund_transactions_paypal_capture_id", table_name="refund_transactions")
    op.drop_index("ix_refund_transactions_refund_case_id", table_name="refund_transactions")
    op.drop_table("refund_transactions")
    op.drop_index("ix_refund_cases_sk_merchant_status_opened", table_name="refund_cases")
    op.drop_index("ix_refund_cases_customer_opened", table_name="refund_cases")
    op.drop_index("ix_refund_cases_merchant_status_opened", table_name="refund_cases")
    op.drop_index("ix_refund_cases_paypal_capture_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_paypal_order_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_shipkart_merchant_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_shipkart_customer_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_shipkart_order_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_shipkart_return_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_merchant_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_customer_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_order_id", table_name="refund_cases")
    op.drop_index("ix_refund_cases_return_case_id", table_name="refund_cases")
    op.drop_table("refund_cases")
    op.drop_index("ix_return_inspections_shipkart_inspector_id", table_name="return_inspections")
    op.drop_index("ix_return_inspections_return_case_id", table_name="return_inspections")
    op.drop_table("return_inspections")
    op.drop_index("ix_return_shipments_carrier_tracking", table_name="return_shipments")
    op.drop_index("ix_return_shipments_return_case_id", table_name="return_shipments")
    op.drop_table("return_shipments")
    op.drop_index("ix_return_case_items_shipkart_order_item_id", table_name="return_case_items")
    op.drop_index("ix_return_case_items_order_item_id", table_name="return_case_items")
    op.drop_index("ix_return_case_items_return_case_id", table_name="return_case_items")
    op.drop_table("return_case_items")
    op.drop_index("ix_return_cases_sk_merchant_status_created", table_name="return_cases")
    op.drop_index("ix_return_cases_customer_created", table_name="return_cases")
    op.drop_index("ix_return_cases_merchant_status_created", table_name="return_cases")
    op.drop_index("ix_return_cases_shipkart_merchant_id", table_name="return_cases")
    op.drop_index("ix_return_cases_shipkart_customer_id", table_name="return_cases")
    op.drop_index("ix_return_cases_shipkart_order_id", table_name="return_cases")
    op.drop_index("ix_return_cases_shipkart_return_id", table_name="return_cases")
    op.drop_index("ix_return_cases_merchant_id", table_name="return_cases")
    op.drop_index("ix_return_cases_customer_id", table_name="return_cases")
    op.drop_index("ix_return_cases_order_id", table_name="return_cases")
    op.drop_table("return_cases")

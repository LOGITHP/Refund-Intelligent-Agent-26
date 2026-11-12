"""Strict Pydantic v2 structured output contracts for the 3-agent pipeline."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DelayOwnerType = Literal[
    "MERCHANT",
    "CARRIER",
    "PAYPAL",
    "ISSUER_OR_BANK",
    "UNKNOWN",
    "NONE",
]

RecommendedActionType = Literal[
    "REQUEST_EVIDENCE",
    "QUEUE_MERCHANT_APPROVAL",
    "INITIATE_ISSUER_INQUIRY",
    "ESCALATE_COMPLIANCE_REVIEW",
    "MONITOR_PENDING_SETTLEMENT",
]

FINANCIAL_OR_REFUND_ACTIONS: frozenset[str] = frozenset(
    {
        "QUEUE_MERCHANT_APPROVAL",
        "INITIATE_ISSUER_INQUIRY",
        "ESCALATE_COMPLIANCE_REVIEW",
        "MONITOR_PENDING_SETTLEMENT",
    }
)


class IntakeResult(BaseModel):
    """Structured output contract for Node 1 (Intake & Evidence Agent)."""

    model_config = ConfigDict(extra="forbid")

    issue_type: str = Field(..., min_length=1, max_length=80)
    verified_facts: list[str] = Field(default_factory=list)
    customer_reported_claims: list[str] = Field(default_factory=list)
    evidence_inventory: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    duplicate_detected: bool = False
    vision_findings: list[dict[str, Any]] = Field(default_factory=list)
    prompt_injection_flags: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.7500"), ge=Decimal("0"), le=Decimal("1"))


class InvestigationResult(BaseModel):
    """Structured output contract for Node 2 (Investigation Agent)."""

    model_config = ConfigDict(extra="forbid")

    timeline_summary: list[dict[str, Any]] = Field(default_factory=list)
    delay_owner: DelayOwnerType = "NONE"
    detected_delay_rules: list[str] = Field(default_factory=list)
    eta_status: str = "NOT_ESTIMABLE"
    earliest_at: datetime | None = None
    latest_at: datetime | None = None
    eta_confidence: str = "LOW"
    eta_basis: list[dict[str, Any]] = Field(default_factory=list)
    paypal_capture_status: str = "UNKNOWN"
    paypal_refund_status: str = "UNKNOWN"
    issuer_status: str = "UNKNOWN"
    issuer_is_simulated: bool = True
    regulatory_status: str = "UNKNOWN"
    regulatory_is_simulated: bool = True
    unresolved_questions: list[str] = Field(default_factory=list)

    @field_validator("eta_basis", mode="before")
    @classmethod
    def _coerce_eta_basis(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            return [{"detail": str(value)}]
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"detail": str(item)})
        return normalized


class ResolutionRecommendation(BaseModel):
    """Structured output contract for Node 3 (Resolution Coordinator Agent)."""

    model_config = ConfigDict(extra="forbid")

    recommended_action: RecommendedActionType
    requires_approval: bool = True
    rationale: str = Field(..., min_length=1)
    customer_explanation: str = Field(..., min_length=1)
    merchant_brief: str = Field(..., min_length=1)
    evidence_references: list[str] = Field(default_factory=list)
    followup_action: str | None = None

    @model_validator(mode="after")
    def _enforce_approval_guardrail(self) -> "ResolutionRecommendation":
        if self.recommended_action in FINANCIAL_OR_REFUND_ACTIONS and not self.requires_approval:
            raise ValueError(
                "REF-001 guardrail violation: requires_approval must be True for any financial/refund action."
            )
        return self


class CustomerChatResponse(BaseModel):
    """Structured output contract for grounded /refunds/{id}/chat responses."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., min_length=1)
    evidence_references: list[str] = Field(default_factory=list)
    eta_status: str = "NOT_ESTIMABLE"
    delay_owner: DelayOwnerType = "UNKNOWN"
    requires_approval: bool = True

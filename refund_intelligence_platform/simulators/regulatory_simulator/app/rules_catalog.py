"""Versioned India & USA Regulatory Rule Catalog and deterministic evaluation engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

SIMULATION_DISCLAIMER = (
    "This is a software-based rules evaluation simulation, not regulatory approval or legal advice."
)
SIMULATION_LABEL = "SIMULATED"

SUPPORTED_COUNTRIES: list[dict[str, Any]] = [
    {
        "code": "IN",
        "name": "India",
        "currencies": ["INR", "USD"],
        "frameworks": ["RBI FEMA Cross-Border", "Consumer Protection (E-Commerce) Rules 2020"],
    },
    {
        "code": "US",
        "name": "United States",
        "currencies": ["USD"],
        "frameworks": ["CFPB Regulation E", "FTC Mail, Internet, or Telephone Order Rule"],
    },
]


@dataclass(frozen=True)
class RegulatoryRule:
    rule_id: str
    version: str
    jurisdiction: str
    title: str
    authority: str
    effective_date: date
    payment_routes: tuple[str, ...]
    entity_types: tuple[str, ...]
    max_refund_sla_hours: int
    obligation_summary: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "jurisdiction": self.jurisdiction,
            "title": self.title,
            "authority": self.authority,
            "effective_date": self.effective_date.isoformat(),
            "payment_routes": list(self.payment_routes),
            "entity_types": list(self.entity_types),
            "max_refund_sla_hours": self.max_refund_sla_hours,
            "obligation_summary": self.obligation_summary,
            "notes": self.notes,
        }


RULE_CATALOG: tuple[RegulatoryRule, ...] = (
    RegulatoryRule(
        rule_id="IN-RBI-FEMA-2026.1",
        version="2026.1",
        jurisdiction="IN",
        title="Cross-Border Export/Import Refund Settlement Traceability",
        authority="RBI / FEMA Cross-Border Payment Guidelines (Simulated)",
        effective_date=date(2026, 1, 1),
        payment_routes=("CROSS_BORDER",),
        entity_types=("BUSINESS", "MARKETPLACE", "ENTERPRISE"),
        max_refund_sla_hours=120,
        obligation_summary=(
            "Verify authorized settlement legal entity, original capture linkage, and FX/cross-border refund trail."
        ),
        notes="Applies to cross-border payment legs involving an Indian merchant or customer.",
    ),
    RegulatoryRule(
        rule_id="IN-CPA-ECOM-2020.1",
        version="2020.1",
        jurisdiction="IN",
        title="India E-Commerce Timely Refund & Transparency Obligation",
        authority="Consumer Protection (E-Commerce) Rules, 2020 (Simulated)",
        effective_date=date(2020, 7, 23),
        payment_routes=("DOMESTIC", "CROSS_BORDER"),
        entity_types=("BUSINESS", "MARKETPLACE", "ENTERPRISE"),
        max_refund_sla_hours=168,
        obligation_summary=(
            "Process approved e-commerce refunds within reasonable statutory timeline without misleading status claims."
        ),
        notes="Applies to Indian e-commerce consumer transactions and return refunds.",
    ),
    RegulatoryRule(
        rule_id="US-REG-E-2026.1",
        version="2026.1",
        jurisdiction="US",
        title="US Electronic Fund Transfer & Wallet Error/Refund Investigation Window",
        authority="CFPB Regulation E Reference Rules (Simulated)",
        effective_date=date(2026, 1, 1),
        payment_routes=("DOMESTIC", "CROSS_BORDER"),
        entity_types=("BUSINESS", "MARKETPLACE", "ENTERPRISE", "INDIVIDUAL"),
        max_refund_sla_hours=240,
        obligation_summary=(
            "Maintain verifiable electronic refund trace, ARN/provider reference, and timely consumer status disclosure."
        ),
        notes="Evaluates electronic payment/wallet refund traceability for US participants.",
    ),
    RegulatoryRule(
        rule_id="US-FTC-MAIL-2026.1",
        version="2026.1",
        jurisdiction="US",
        title="US Online Order Prompt Refund & Delay Notice Rule",
        authority="FTC Mail, Internet, or Telephone Order Rule (Simulated)",
        effective_date=date(2026, 1, 1),
        payment_routes=("DOMESTIC", "CROSS_BORDER"),
        entity_types=("BUSINESS", "MARKETPLACE", "ENTERPRISE"),
        max_refund_sla_hours=168,
        obligation_summary=(
            "Provide prompt refund upon cancellation/return approval and truthful delay notifications."
        ),
        notes="Applies to commercial online merchants transacting with US customers.",
    ),
)


def list_rules(
    *,
    jurisdiction: str | None = None,
    version: str | None = None,
) -> list[dict[str, Any]]:
    items = list(RULE_CATALOG)
    if jurisdiction:
        code = jurisdiction.strip().upper()
        items = [r for r in items if r.jurisdiction == code]
    if version:
        ver = version.strip()
        items = [r for r in items if r.version == ver]
    return [r.to_dict() for r in items]


def evaluate_transaction_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Deterministically evaluate IN/US regulatory rules without fabricating missing facts."""
    merchant_country = (ctx.get("merchant_country") or "").strip().upper() or None
    customer_country = (ctx.get("customer_country") or "").strip().upper() or None
    payment_route = (ctx.get("payment_route") or "").strip().upper() or None
    entity_type = (ctx.get("merchant_entity_type") or "").strip().upper() or None
    business_activity = (ctx.get("business_activity") or "").strip() or None
    settlement_confirmed = ctx.get("settlement_entity_confirmed")
    eval_date_raw = ctx.get("evaluation_date")
    eval_date = (
        date.fromisoformat(eval_date_raw)
        if isinstance(eval_date_raw, str) and eval_date_raw
        else (eval_date_raw if isinstance(eval_date_raw, date) else date(2026, 11, 12))
    )

    unresolved_questions: list[str] = []
    jurisdictions: list[str] = []
    for code in (merchant_country, customer_country):
        if code and code in ("IN", "US") and code not in jurisdictions:
            jurisdictions.append(code)

    # Missing core country context -> UNKNOWN
    if not merchant_country or not customer_country:
        if not merchant_country:
            unresolved_questions.append("Confirm merchant_country ISO-2 code.")
        if not customer_country:
            unresolved_questions.append("Confirm customer_country ISO-2 code.")
        return {
            "jurisdiction": jurisdictions,
            "status": "UNKNOWN",
            "matched_rules": [],
            "unresolved_questions": unresolved_questions,
            "obligations": [],
            "violations": [],
            "rule_versions": [],
        }

    # Neither country is IN or US -> NOT_APPLICABLE
    if not jurisdictions:
        return {
            "jurisdiction": [c for c in (merchant_country, customer_country) if c],
            "status": "NOT_APPLICABLE",
            "matched_rules": [],
            "unresolved_questions": [],
            "obligations": [],
            "violations": [],
            "rule_versions": [],
        }

    # Missing route, entity type, or unconfirmed settlement legal entity -> MANUAL_REVIEW_REQUIRED
    if not payment_route:
        unresolved_questions.append("Confirm payment_route (DOMESTIC or CROSS_BORDER).")
    if not entity_type:
        unresolved_questions.append("Confirm merchant_entity_type (e.g., BUSINESS, MARKETPLACE).")
    if payment_route == "CROSS_BORDER" and settlement_confirmed is not True:
        unresolved_questions.append("Confirm the legal entity receiving settlement.")
    elif settlement_confirmed is False:
        unresolved_questions.append("Confirm the legal entity receiving settlement.")

    if unresolved_questions:
        return {
            "jurisdiction": jurisdictions,
            "status": "MANUAL_REVIEW_REQUIRED",
            "matched_rules": [],
            "unresolved_questions": unresolved_questions,
            "obligations": [],
            "violations": [],
            "rule_versions": [],
        }

    matched: list[RegulatoryRule] = []
    for rule in RULE_CATALOG:
        if rule.jurisdiction not in jurisdictions:
            continue
        if eval_date < rule.effective_date:
            continue
        if payment_route not in rule.payment_routes:
            continue
        if entity_type not in rule.entity_types:
            continue
        matched.append(rule)

    if not matched:
        return {
            "jurisdiction": jurisdictions,
            "status": "NOT_APPLICABLE",
            "matched_rules": [],
            "unresolved_questions": [],
            "obligations": [],
            "violations": [],
            "rule_versions": [],
        }

    if not business_activity:
        status_result = "POTENTIALLY_APPLICABLE"
        unresolved_questions.append(
            "Confirm merchant business_activity category for final applicability scoping."
        )
    else:
        status_result = "APPLICABLE"

    obligations = [
        {
            "rule_id": rule.rule_id,
            "version": rule.version,
            "jurisdiction": rule.jurisdiction,
            "obligation": rule.obligation_summary,
            "max_refund_sla_hours": rule.max_refund_sla_hours,
        }
        for rule in matched
    ]

    violations: list[dict[str, Any]] = []
    delay_hours = ctx.get("refund_delay_hours")
    if isinstance(delay_hours, (int, float)) and delay_hours > 0:
        for rule in matched:
            if delay_hours > rule.max_refund_sla_hours:
                violations.append(
                    {
                        "rule_id": rule.rule_id,
                        "jurisdiction": rule.jurisdiction,
                        "severity": "HIGH" if delay_hours >= rule.max_refund_sla_hours * 1.5 else "MEDIUM",
                        "description": (
                            f"Simulated refund delay ({delay_hours}h) exceeds reference SLA threshold "
                            f"({rule.max_refund_sla_hours}h) under {rule.rule_id}."
                        ),
                        "observed_delay_hours": delay_hours,
                        "threshold_hours": rule.max_refund_sla_hours,
                    }
                )

    return {
        "jurisdiction": jurisdictions,
        "status": status_result,
        "matched_rules": [rule.to_dict() for rule in matched],
        "unresolved_questions": unresolved_questions,
        "obligations": obligations,
        "violations": violations,
        "rule_versions": sorted({f"{rule.rule_id}" for rule in matched}),
    }

"""LangGraph shared state, untrusted text isolation, and prompt-injection detection."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, TypedDict

from app.core.logging_redact import redact_sensitive_data

UNTRUSTED_START_DELIMITER = "<<<UNTRUSTED_CUSTOMER_TEXT>>>"
UNTRUSTED_END_DELIMITER = "<<<END_UNTRUSTED_TEXT>>>"

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_previous_instructions",
        re.compile(r"\b(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|system)\s+instructions?\b", re.IGNORECASE),
    ),
    (
        "override_requires_approval",
        re.compile(r"\b(override|disable|set|force|skip|bypass)\b.{0,30}\brequires_approval\b|\brequires_approval\s*[:=]\s*false\b", re.IGNORECASE),
    ),
    (
        "bypass_merchant_approval",
        re.compile(r"\b(bypass|skip|without)\b.{0,25}\bmerchant(\s+approval)?\b", re.IGNORECASE),
    ),
    (
        "direct_paypal_payout",
        re.compile(r"\b(execute|trigger|call|send)\b.{0,30}\b(paypal\s+)?refund\s+(directly|immediately|now)\b|\brefund\s+\$?\d+\s+immediately\b", re.IGNORECASE),
    ),
    (
        "system_prompt_exfiltration",
        re.compile(r"\b(reveal|print|dump|leak)\s+(your\s+)?(system\s+prompt|api[_\s]?key|secret)\b", re.IGNORECASE),
    ),
    (
        "delimiter_breakout_attempt",
        re.compile(r"<<<\s*(END_UNTRUSTED_TEXT|UNTRUSTED_CUSTOMER_TEXT)\s*>>>", re.IGNORECASE),
    ),
)


class RefundAgentState(TypedDict):
    """Typed LangGraph state passed across Intake, Investigation, and Resolution nodes."""

    refund_case_id: str
    return_case_id: str | None
    shipkart_order_id: int | None
    shipkart_customer_id: int | None
    shipkart_merchant_id: int | None
    customer_message: str
    untrusted_ocr_texts: list[str]
    evidence_items: list[dict[str, Any]]
    intake_result: dict[str, Any] | None
    investigation_result: dict[str, Any] | None
    resolution_result: dict[str, Any] | None
    execution_records: list[dict[str, Any]]
    errors: list[str]


def wrap_untrusted_text(text: str | None) -> str:
    """Isolate raw customer/OCR text inside explicit untrusted delimiters with secret redaction."""
    raw = str(text or "")
    # Neutralize any embedded delimiter tokens so untrusted data cannot break isolation.
    neutralized = (
        raw.replace(UNTRUSTED_START_DELIMITER, "[STRIPPED_START_DELIM]")
        .replace(UNTRUSTED_END_DELIMITER, "[STRIPPED_END_DELIM]")
    )
    redacted = redact_sensitive_data(neutralized)
    return f"{UNTRUSTED_START_DELIMITER}\n{redacted}\n{UNTRUSTED_END_DELIMITER}"


def detect_prompt_injections(texts: Iterable[str | None]) -> list[str]:
    """Scan untrusted customer/OCR strings for prompt-injection and guardrail-bypass attempts."""
    flags: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        candidate = str(text)
        for label, pattern in _INJECTION_PATTERNS:
            if pattern.search(candidate):
                flag = f"PROMPT_INJECTION:{label}"
                if flag not in seen:
                    seen.add(flag)
                    flags.append(flag)
    return flags


def sanitize_untrusted_payload(
    *,
    customer_message: str = "",
    customer_description: str = "",
    refund_reason: str = "",
    ocr_texts: Iterable[str] = (),
) -> dict[str, Any]:
    """Build an isolated, redacted payload for LLM prompts where customer/OCR inputs are fenced."""
    cleaned_ocrs = [wrap_untrusted_text(item) for item in ocr_texts if item and str(item).strip()]
    return {
        "untrusted_customer_message": wrap_untrusted_text(customer_message),
        "untrusted_return_description": wrap_untrusted_text(customer_description),
        "untrusted_refund_reason": wrap_untrusted_text(refund_reason),
        "untrusted_ocr_texts": cleaned_ocrs,
    }

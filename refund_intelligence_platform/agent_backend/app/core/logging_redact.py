"""Recursive secret/PII redaction utilities and safe log formatter."""

from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "secret",
    "password",
    "passwd",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "client_secret",
    "cvv",
    "card_number",
    "bearer",
    "cookie",
)

_PAN_KEY_RE = re.compile(r"(?:^|[_\-\s.])pan(?:$|[_\-\s.])", re.IGNORECASE)
_BEARER_TEXT_RE = re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_NVAPI_TEXT_RE = re.compile(r"\bnvapi-[A-Za-z0-9\-_]+", re.IGNORECASE)
_INLINE_SECRET_KV_RE = re.compile(
    r"(?i)\b(client_secret|api_key|apikey|password|access_token|refresh_token|secret|cvv|card_number)\s*([=:])\s*([^\s,;\"']+)"
)
_SPACED_CARD_PAN_RE = re.compile(r"\b\d{4}(?:[- ]\d{4}){3}\b")

_STANDARD_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if any(term in lowered for term in _SENSITIVE_KEY_SUBSTRINGS):
        return True
    return bool(_PAN_KEY_RE.search(lowered))


def _redact_string(value: str) -> str:
    redacted = _BEARER_TEXT_RE.sub("Bearer [REDACTED]", value)
    redacted = _NVAPI_TEXT_RE.sub(REDACTED, redacted)
    redacted = _INLINE_SECRET_KV_RE.sub(r"\1\2[REDACTED]", redacted)
    redacted = _SPACED_CARD_PAN_RE.sub(REDACTED, redacted)
    return redacted


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively redact sensitive keys, Bearer tokens, NVIDIA keys, and card fields."""
    if isinstance(obj, str):
        return _redact_string(obj)
    if isinstance(obj, Mapping):
        sanitized: dict[Any, Any] = {}
        for key, value in obj.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                sanitized[key] = REDACTED
            else:
                sanitized[key] = redact_sensitive_data(value)
        return sanitized
    if isinstance(obj, list):
        return [redact_sensitive_data(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_sensitive_data(item) for item in obj)
    if isinstance(obj, set):
        return {redact_sensitive_data(item) for item in obj}
    return obj


class RedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets and card data from messages, args, and extras."""

    def format(self, record: logging.LogRecord) -> str:
        record_copy = copy.copy(record)
        if isinstance(record_copy.msg, str):
            record_copy.msg = _redact_string(record_copy.msg)
        elif isinstance(record_copy.msg, (Mapping, list, tuple, set)):
            record_copy.msg = redact_sensitive_data(record_copy.msg)

        if record_copy.args:
            record_copy.args = redact_sensitive_data(record_copy.args)

        formatted = super().format(record_copy)

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            redacted_extras = redact_sensitive_data(extras)
            kv_pairs = []
            for key in sorted(redacted_extras):
                val = redacted_extras[key]
                serialized = val if isinstance(val, (str, int, float, bool)) or val is None else json.dumps(val, default=str)
                kv_pairs.append(f"{key}={serialized}")
            formatted = f"{formatted} | {' '.join(kv_pairs)}"

        return _redact_string(formatted)

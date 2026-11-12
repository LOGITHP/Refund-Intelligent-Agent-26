"""Authenticated PayPal REST API client for captures, refunds, and webhook verification."""

from __future__ import annotations

import logging
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging_redact import redact_sensitive_data

logger = logging.getLogger(__name__)


class PayPalAPIError(RuntimeError):
    """Raised when PayPal REST API calls fail or credentials are missing."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = redact_sensitive_data(detail) if detail is not None else None


class PayPalClient:
    """Synchronous PayPal v1/v2 REST client with injectable HTTPX transport/client."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        webhook_id: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or settings.PAYPAL_BASE_URL).rstrip("/")
        self._client_id = client_id if client_id is not None else settings.PAYPAL_CLIENT_ID
        self._client_secret = client_secret if client_secret is not None else settings.PAYPAL_CLIENT_SECRET
        self._webhook_id = webhook_id if webhook_id is not None else settings.PAYPAL_WEBHOOK_ID
        self.timeout = timeout
        self._transport = transport
        self._client = client
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _dispatch(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        data: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            if self._client is not None:
                url = path if self._client.base_url else f"{self.base_url}{path}"
                return self._client.request(
                    method,
                    url,
                    headers=headers,
                    auth=auth,
                    data=data,
                    json=json_payload,
                    timeout=self.timeout,
                )
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                return client.request(
                    method,
                    path,
                    headers=headers,
                    auth=auth,
                    data=data,
                    json=json_payload,
                )
        except httpx.HTTPError as exc:
            raise PayPalAPIError(
                f"PayPal network failure on {method} {path}: {exc}",
                status_code=None,
                detail=str(exc),
            ) from exc

    def _get_access_token(self) -> str:
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        if not self._client_id.strip() or not self._client_secret.strip():
            raise PayPalAPIError(
                "PayPal API credentials are not configured.",
                status_code=503,
            )

        response = self._dispatch(
            "POST",
            "/v1/oauth2/token",
            headers={"Accept": "application/json"},
            auth=(self._client_id, self._client_secret),
            data={"grant_type": "client_credentials"},
        )
        if response.status_code >= 400:
            raise PayPalAPIError(
                f"PayPal OAuth token request failed with HTTP {response.status_code}",
                status_code=response.status_code,
                detail=self._safe_json_or_text(response),
            )

        payload = self._safe_json_or_text(response)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise PayPalAPIError(
                "PayPal OAuth response missing access_token",
                status_code=response.status_code,
                detail=payload,
            )

        expires_in = int(payload.get("expires_in", 300))
        self._access_token = str(token)
        # Refresh 60 seconds early to avoid race with token expiry
        self._token_expires_at = now + max(1, expires_in - 60)
        return self._access_token

    @staticmethod
    def _safe_json_or_text(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = self._get_access_token()
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        response = self._dispatch(
            method,
            path,
            headers=headers,
            json_payload=json_payload,
        )
        parsed = self._safe_json_or_text(response)
        redacted = redact_sensitive_data(parsed)

        if response.status_code >= 400:
            logger.warning(
                "PayPal API error on %s %s: status=%s detail=%s",
                method,
                path,
                response.status_code,
                redacted,
            )
            raise PayPalAPIError(
                f"PayPal API {method} {path} failed with HTTP {response.status_code}",
                status_code=response.status_code,
                detail=redacted,
            )

        if not isinstance(redacted, dict):
            return {"raw": redacted}
        return redacted

    def get_capture(self, capture_id: str) -> dict[str, Any]:
        """Retrieve authoritative capture details from PayPal."""
        clean_id = (capture_id or "").strip()
        if not clean_id:
            raise PayPalAPIError("capture_id must not be empty", status_code=422)
        return self._request("GET", f"/v2/payments/captures/{clean_id}")

    def get_refund(self, refund_id: str) -> dict[str, Any]:
        """Retrieve authoritative refund details from PayPal."""
        clean_id = (refund_id or "").strip()
        if not clean_id:
            raise PayPalAPIError("refund_id must not be empty", status_code=422)
        return self._request("GET", f"/v2/payments/refunds/{clean_id}")

    def refund_capture(
        self,
        *,
        capture_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Execute an idempotent refund against a PayPal capture."""
        clean_capture = (capture_id or "").strip()
        clean_key = (idempotency_key or "").strip()
        if not clean_capture:
            raise PayPalAPIError("capture_id must not be empty", status_code=422)
        if not clean_key:
            raise PayPalAPIError("idempotency_key must not be empty", status_code=422)

        dec_amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if dec_amount <= Decimal("0.00"):
            raise PayPalAPIError("Refund amount must be positive", status_code=422)

        payload: dict[str, Any] = {
            "amount": {
                "value": f"{dec_amount:.2f}",
                "currency_code": (currency or "USD").strip().upper(),
            }
        }
        if note and note.strip():
            payload["note_to_payer"] = note.strip()[:255]

        return self._request(
            "POST",
            f"/v2/payments/captures/{clean_capture}/refund",
            json_payload=payload,
            extra_headers={"PayPal-Request-Id": clean_key},
        )

    def verify_webhook_signature(
        self,
        headers: dict[str, str],
        event_body: dict[str, Any],
    ) -> bool:
        """Verify PayPal webhook cryptographic signature via PayPal verification endpoint."""
        if not self._webhook_id.strip():
            raise PayPalAPIError("PAYPAL_WEBHOOK_ID is not configured", status_code=503)

        norm = {k.lower(): v for k, v in headers.items()}
        required = (
            "paypal-auth-algo",
            "paypal-cert-url",
            "paypal-transmission-id",
            "paypal-transmission-sig",
            "paypal-transmission-time",
        )
        if any(not norm.get(h) for h in required):
            return False

        verify_payload = {
            "auth_algo": norm["paypal-auth-algo"],
            "cert_url": norm["paypal-cert-url"],
            "transmission_id": norm["paypal-transmission-id"],
            "transmission_sig": norm["paypal-transmission-sig"],
            "transmission_time": norm["paypal-transmission-time"],
            "webhook_id": self._webhook_id,
            "webhook_event": event_body,
        }
        result = self._request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json_payload=verify_payload,
        )
        return str(result.get("verification_status", "")).upper() == "SUCCESS"

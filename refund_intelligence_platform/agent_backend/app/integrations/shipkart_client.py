"""Authenticated HTTPX connector for Shipkart (ecommerce_platform) bridge endpoints."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.security import compute_hmac_signature, create_service_jwt


class ShipkartBridgeError(RuntimeError):
    """Raised when a Shipkart bridge request fails due to HTTP 4xx/5xx or network errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class ShipkartBridgeClient:
    """Synchronous HTTPX client communicating with Shipkart using Service JWT + optional HMAC."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        token_factory: Callable[[], str] | None = None,
        bridge_secret: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.SHIPKART_API_URL).rstrip("/")
        self.timeout = timeout
        self._transport = transport
        self._client = client
        self._token_factory = token_factory or create_service_jwt
        self._bridge_secret = (
            bridge_secret if bridge_secret is not None else settings.BRIDGE_SHARED_SECRET
        )

    def _build_headers(
        self,
        *,
        body_bytes: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        token = self._token_factory()
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
        }
        if body_bytes is not None:
            headers["Content-Type"] = "application/json"
            if self._bridge_secret and self._bridge_secret.strip():
                sig = compute_hmac_signature(body_bytes, self._bridge_secret)
                headers["X-Bridge-Signature"] = f"sha256={sig}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        body_bytes: bytes | None = None
        if json_payload is not None:
            body_bytes = json.dumps(json_payload, separators=(",", ":"), default=str).encode("utf-8")

        headers = self._build_headers(body_bytes=body_bytes)

        try:
            if self._client is not None:
                response = self._client.request(
                    method,
                    f"{self.base_url}{path}" if not self._client.base_url else path,
                    params=clean_params or None,
                    content=body_bytes,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                with httpx.Client(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    transport=self._transport,
                ) as client:
                    response = client.request(
                        method,
                        path,
                        params=clean_params or None,
                        content=body_bytes,
                        headers=headers,
                    )
        except httpx.HTTPError as exc:
            raise ShipkartBridgeError(
                f"Shipkart bridge network failure on {method} {path}: {exc}",
                status_code=None,
                detail=str(exc),
            ) from exc

        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise ShipkartBridgeError(
                f"Shipkart bridge request {method} {path} failed with HTTP {response.status_code}",
                status_code=response.status_code,
                detail=detail,
            )

        return response

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> Any:
        response = self._send(method, path, params=params, json_payload=json_payload)
        try:
            return response.json()
        except ValueError as exc:
            raise ShipkartBridgeError(
                f"Shipkart bridge returned invalid JSON on {method} {path}",
                status_code=response.status_code,
                detail=response.text,
            ) from exc

    def fetch_order_context(self, order_id: int) -> dict[str, Any]:
        """Fetch verified Shipkart order, items, allocation, and PayPal capture context."""
        data = self._request_json("GET", f"/api/v1/orders/{order_id}/bridge-context")
        if not isinstance(data, dict):
            raise ShipkartBridgeError(
                "Unexpected order bridge context payload type",
                status_code=200,
                detail=data,
            )
        return data

    def fetch_paypal_capture_status(self, order_id: int) -> dict[str, Any]:
        """Fetch redacted PayPal capture status for an order via Shipkart's merchant bridge."""
        data = self._request_json("GET", f"/api/v1/orders/{order_id}/paypal-capture-status")
        if not isinstance(data, dict):
            raise ShipkartBridgeError(
                "Unexpected PayPal capture status payload type",
                status_code=200,
                detail=data,
            )
        return data

    def fetch_paypal_refund_status(self, return_id: int) -> dict[str, Any]:
        """Fetch redacted PayPal refund status for a return via Shipkart's merchant bridge."""
        data = self._request_json("GET", f"/api/v1/returns/{return_id}/paypal-refund-status")
        if not isinstance(data, dict):
            raise ShipkartBridgeError(
                "Unexpected PayPal refund status payload type",
                status_code=200,
                detail=data,
            )
        return data

    def fetch_pending_returns(self, merchant_id: int | None = None) -> list[dict[str, Any]]:
        """Fetch pending Shipkart returns optionally filtered by merchant_id."""
        data = self._request_json(
            "GET",
            "/api/v1/returns/bridge/pending",
            params={"merchant_id": merchant_id},
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "returns", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        raise ShipkartBridgeError(
            "Unexpected pending returns payload format",
            status_code=200,
            detail=data,
        )

    @staticmethod
    def _normalize_media_path(relative_path: str) -> str:
        raw = (relative_path or "").strip()
        if not raw:
            raise ShipkartBridgeError("Media relative_path must not be empty", status_code=400)

        parsed = urlparse(raw)
        if parsed.scheme or parsed.netloc:
            raise ShipkartBridgeError(
                "Media path must be relative to Shipkart API (absolute URLs rejected)",
                status_code=400,
                detail=relative_path,
            )

        segments = [seg for seg in raw.split("/") if seg]
        if any(seg in (".", "..") for seg in segments):
            raise ShipkartBridgeError(
                "Invalid path traversal in media relative_path",
                status_code=400,
                detail=relative_path,
            )

        if raw.startswith("/api/"):
            return raw
        if raw.startswith("api/"):
            return f"/{raw}"
        return f"/api/v1/media/files/{raw.lstrip('/')}"

    def fetch_media_bytes(self, relative_path: str) -> tuple[bytes, str]:
        """Stream raw invoice/evidence media bytes and content-type from Shipkart."""
        path = self._normalize_media_path(relative_path)
        response = self._send("GET", path)
        content_type = response.headers.get("content-type", "application/octet-stream")
        return response.content, content_type

    def post_agent_recommendation(self, return_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit an agent decision/recommendation to Shipkart for merchant review."""
        data = self._request_json(
            "POST",
            f"/api/v1/returns/{return_id}/agent-decision",
            json_payload=payload,
        )
        if not isinstance(data, dict):
            raise ShipkartBridgeError(
                "Unexpected agent recommendation response format",
                status_code=200,
                detail=data,
            )
        return data

    def submit_approved_refund_execution(
        self,
        return_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a merchant-approved refund execution request to Shipkart."""
        data = self._request_json(
            "POST",
            f"/api/v1/returns/{return_id}/execute-approved-refund",
            json_payload=payload,
        )
        if not isinstance(data, dict):
            raise ShipkartBridgeError(
                "Unexpected refund execution response format",
                status_code=200,
                detail=data,
            )
        return data

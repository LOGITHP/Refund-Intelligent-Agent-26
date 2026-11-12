"""Hardened PayPal REST v2 client with OAuth2 token caching, idempotency headers, and webhook verification."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import threading
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse
import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_secret, redact_sensitive_data
from app.db.models import MerchantPaymentPreference

logger = logging.getLogger(__name__)


def get_paypal_base_url(env: str) -> str:
    if (env or "SANDBOX").strip().upper() == "LIVE":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def merchant_paypal_aad(merchant_id: int) -> bytes:
    return f"merchant:{merchant_id}:paypal".encode("utf-8")


class PayPalAPIError(Exception):
    """Raised when PayPal REST API calls fail or return unexpected non-2xx responses."""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = redact_sensitive_data(details or {})


class PayPalService:
    """Client for PayPal Orders v2, Payments v2, and Webhook Signature Verification APIs."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        webhook_id: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._webhook_id = webhook_id
        self._base_url = base_url
        self._transport = transport
        self._http_client = http_client
        self._token_lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    @property
    def client_id(self) -> str:
        return (self._client_id if self._client_id is not None else settings.PAYPAL_CLIENT_ID).strip()

    @property
    def client_secret(self) -> str:
        return (self._client_secret if self._client_secret is not None else settings.PAYPAL_CLIENT_SECRET).strip()

    @property
    def webhook_id(self) -> str:
        return (self._webhook_id if self._webhook_id is not None else settings.PAYPAL_WEBHOOK_ID).strip()

    @property
    def base_url(self) -> str:
        return (self._base_url if self._base_url is not None else settings.PAYPAL_BASE_URL).rstrip("/")

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        if self._transport is not None:
            self._http_client = httpx.Client(transport=self._transport, timeout=15.0)
        else:
            self._http_client = httpx.Client(timeout=15.0)
        return self._http_client

    def clear_token_cache(self) -> None:
        with self._token_lock:
            self._access_token = None
            self._token_expires_at = None

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        if not self.client_id or not self.client_secret:
            raise PayPalAPIError("PayPal credentials are not configured", status_code=503)

        now = datetime.now(timezone.utc)
        with self._token_lock:
            if (
                not force_refresh
                and self._access_token
                and self._token_expires_at is not None
                and now < self._token_expires_at
            ):
                return self._access_token

            client = self._get_client()
            try:
                resp = client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                logger.error("PayPal OAuth2 transport error: %s", exc)
                raise PayPalAPIError("Failed connecting to PayPal OAuth2 endpoint", status_code=502) from exc

            if resp.status_code >= 400:
                safe_err = self._safe_json(resp)
                logger.error("PayPal OAuth2 failed (%s): %s", resp.status_code, safe_err)
                raise PayPalAPIError(
                    "PayPal OAuth2 authentication failed",
                    status_code=502,
                    details=safe_err,
                )

            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise PayPalAPIError("PayPal OAuth2 response missing access_token", status_code=502)

            expires_in = int(data.get("expires_in", 300))
            refresh_buffer = min(60, max(5, expires_in // 10))
            self._access_token = token
            self._token_expires_at = now + timedelta(seconds=max(10, expires_in - refresh_buffer))
            return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id

        client = self._get_client()
        url = f"{self.base_url}{path}"
        try:
            resp = client.request(method, url, json=json_body, headers=headers)
            if resp.status_code == 401:
                token = self.get_access_token(force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"
                resp = client.request(method, url, json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("PayPal API HTTP error on %s %s: %s", method, path, exc)
            raise PayPalAPIError(f"PayPal API communication failure on {path}", status_code=502) from exc

        if resp.status_code >= 400:
            safe_err = self._safe_json(resp)
            logger.warning("PayPal API error %s on %s %s: %s", resp.status_code, method, path, safe_err)
            raise PayPalAPIError(
                safe_err.get("message") or f"PayPal API returned {resp.status_code}",
                status_code=resp.status_code if 400 <= resp.status_code < 500 else 502,
                details=safe_err,
            )

        if not resp.content:
            return {}
        return resp.json()

    def _safe_json(self, resp: httpx.Response) -> Dict[str, Any]:
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                return redact_sensitive_data(parsed)
            return {"raw": redact_sensitive_data(parsed)}
        except Exception:
            return {"status_code": resp.status_code, "message": resp.text[:300]}

    def create_order(
        self,
        *,
        request_id: str,
        amount_usd: Decimal,
        currency_code: str = "USD",
        reference_id: str,
        description: str = "Shipkart Order",
        custom_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        quantized = Decimal(str(amount_usd)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "description": description[:127],
                    "custom_id": (custom_id or reference_id)[:127],
                    "amount": {
                        "currency_code": currency_code,
                        "value": f"{quantized:.2f}",
                    },
                }
            ],
        }
        return self._request("POST", "/v2/checkout/orders", json_body=payload, request_id=request_id)

    def capture_order(self, *, paypal_order_id: str, request_id: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/v2/checkout/orders/{paypal_order_id}/capture",
            json_body={},
            request_id=request_id,
        )

    def get_order(self, paypal_order_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v2/checkout/orders/{paypal_order_id}")

    def get_capture(self, capture_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v2/payments/captures/{capture_id}")

    def get_refund(self, refund_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v2/payments/refunds/{refund_id}")

    def refund_capture(
        self,
        *,
        capture_id: str,
        request_id: str,
        amount: Optional[Decimal] = None,
        currency_code: str = "USD",
        note_to_payer: str = "Refund processed by Shipkart",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"note_to_payer": note_to_payer[:255]}
        if amount is not None:
            quantized = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            payload["amount"] = {
                "value": f"{quantized:.2f}",
                "currency_code": currency_code,
            }
        return self._request(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            json_body=payload,
            request_id=request_id,
        )

    @staticmethod
    def validate_cert_url(cert_url: str) -> bool:
        """Strictly validates that PAYPAL-CERT-URL uses HTTPS on an official *.paypal.com domain."""
        if not cert_url or not isinstance(cert_url, str):
            return False
        if not cert_url.lower().startswith("https://"):
            return False
        parsed = urlparse(cert_url)
        if parsed.scheme.lower() != "https":
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.port not in (None, 443):
            return False
        host = (parsed.hostname or "").lower()
        return host.endswith(".paypal.com")

    def verify_webhook_signature(
        self,
        *,
        headers: Mapping[str, str],
        webhook_event: Dict[str, Any],
        webhook_id: Optional[str] = None,
    ) -> bool:
        lowered = {str(k).lower(): v for k, v in headers.items()}
        transmission_id = lowered.get("paypal-transmission-id", "").strip()
        transmission_time = lowered.get("paypal-transmission-time", "").strip()
        cert_url = lowered.get("paypal-cert-url", "").strip()
        auth_algo = lowered.get("paypal-auth-algo", "").strip()
        transmission_sig = lowered.get("paypal-transmission-sig", "").strip()

        if not all([transmission_id, transmission_time, cert_url, auth_algo, transmission_sig]):
            logger.warning("PayPal webhook missing required verification headers")
            return False

        if not self.validate_cert_url(cert_url):
            logger.warning("PayPal webhook rejected due to untrusted cert_url: %s", cert_url)
            return False

        effective_webhook_id = (webhook_id if webhook_id is not None else self.webhook_id).strip()
        if not effective_webhook_id:
            logger.warning("PAYPAL_WEBHOOK_ID is not configured; cannot verify webhook")
            return False

        payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": effective_webhook_id,
            "webhook_event": webhook_event,
        }
        try:
            res = self._request("POST", "/v1/notifications/verify-webhook-signature", json_body=payload)
        except PayPalAPIError as exc:
            logger.warning("PayPal webhook verification call failed: %s", exc)
            return False

        return res.get("verification_status") == "SUCCESS"


paypal_service = PayPalService()

_merchant_cache_lock = threading.Lock()
_merchant_service_cache: Dict[int, tuple[tuple[str, str, str, str], PayPalService]] = {}


def invalidate_merchant_paypal_cache(merchant_id: int) -> None:
    with _merchant_cache_lock:
        _merchant_service_cache.pop(merchant_id, None)


def get_paypal_service() -> PayPalService:
    return paypal_service


def resolve_paypal_service_for_merchant(
    db: Session,
    merchant_id: Optional[int],
    *,
    fallback_service: Optional[PayPalService] = None,
) -> PayPalService:
    """Resolves per-merchant PayPal REST client or platform fallback for starter catalog items (merchant_id=None)."""
    if merchant_id is None:
        return fallback_service if fallback_service is not None else get_paypal_service()

    pref = (
        db.query(MerchantPaymentPreference)
        .filter(MerchantPaymentPreference.merchant_id == merchant_id)
        .first()
    )
    env = (pref.paypal_environment if pref and pref.paypal_environment else "SANDBOX").strip().upper()
    base_url = get_paypal_base_url(env)

    client_id = (pref.paypal_client_id or "").strip() if pref else ""
    encrypted_secret = (pref.encrypted_paypal_client_secret or "").strip() if pref else ""

    # NEVER fall back to platform credentials for a merchant-owned item!
    if not client_id or not encrypted_secret:
        return PayPalService(
            client_id="",
            client_secret="",
            webhook_id="",
            base_url=base_url,
        )

    webhook_id = (pref.paypal_webhook_id or "").strip() if pref else ""
    custom_transport = fallback_service._transport if fallback_service is not None else None
    custom_http_client = fallback_service._http_client if fallback_service is not None else None
    fingerprint = (client_id, encrypted_secret, webhook_id, env)

    with _merchant_cache_lock:
        cached = _merchant_service_cache.get(merchant_id)
        if cached is not None:
            cached_fp, cached_svc = cached
            if (
                cached_fp == fingerprint
                and cached_svc._transport is custom_transport
                and cached_svc._http_client is custom_http_client
            ):
                return cached_svc

    try:
        plaintext_secret = decrypt_secret(
            encrypted_secret,
            associated_data=merchant_paypal_aad(merchant_id),
        )
    except Exception as exc:
        logger.error("Failed to decrypt PayPal client secret for merchant_id=%s: %s", merchant_id, type(exc).__name__)
        raise PayPalAPIError(
            "Merchant PayPal credentials could not be decrypted",
            status_code=503,
        ) from exc

    svc = PayPalService(
        client_id=client_id,
        client_secret=plaintext_secret,
        webhook_id=webhook_id,
        base_url=base_url,
        transport=custom_transport,
        http_client=custom_http_client,
    )
    with _merchant_cache_lock:
        _merchant_service_cache[merchant_id] = (fingerprint, svc)
    return svc

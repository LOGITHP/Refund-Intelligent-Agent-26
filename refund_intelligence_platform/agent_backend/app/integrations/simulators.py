"""HTTPX client adapters for Carrier (8203), Issuer (8201), and Regulatory (8202) simulators."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

REGULATORY_DISCLAIMER = (
    "This is a software-based rules evaluation simulation, not regulatory approval or legal advice."
)


class SimulatorClientError(RuntimeError):
    """Raised when a simulator returns an unexpected non-503 HTTP error."""

    def __init__(self, message: str, *, status_code: int, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _run_coro_sync(coro_factory: Any) -> Any:
    """Execute an async coroutine cleanly from synchronous code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


class _BaseSimulatorClient:
    """Shared HTTPX adapter supporting sync Client, sync BaseTransport, and ASGITransport."""

    service_name: str = "simulator"
    default_degraded_status: str = "UNAVAILABLE"

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        client: httpx.Client | None = None,
        async_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport
        self._client = client
        self._async_client = async_client

    def _degraded_payload(
        self,
        *,
        error_code: str,
        message: str,
        http_status: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "service": self.service_name,
            "status": self.default_degraded_status,
            "degraded": True,
            "error_code": error_code,
            "message": message,
            "http_status": http_status,
            "is_simulated": True,
            "simulation_label": "SIMULATED",
        }
        if extra:
            payload.update(extra)
            payload["degraded"] = True
            payload["is_simulated"] = True
        return payload

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 503:
            try:
                body = response.json()
            except ValueError:
                body = {}
            return self._degraded_payload(
                error_code=body.get("error_code", f"{self.service_name.upper()}_UNAVAILABLE"),
                message=body.get("message", f"{self.service_name} returned HTTP 503"),
                http_status=503,
                extra=body if isinstance(body, dict) else None,
            )

        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise SimulatorClientError(
                f"{self.service_name} request failed with HTTP {response.status_code}",
                status_code=response.status_code,
                detail=detail,
            )

        data = response.json()
        if isinstance(data, dict):
            data.setdefault("degraded", False)
            data.setdefault("is_simulated", True)
        return data

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        if isinstance(self._transport, httpx.AsyncBaseTransport) or self._async_client is not None:
            return _run_coro_sync(
                lambda: self._arequest(method, path, json=json, params=clean_params)
            )

        try:
            if self._client is not None:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    params=clean_params or None,
                )
            else:
                with httpx.Client(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    transport=self._transport,
                ) as sync_client:
                    response = sync_client.request(
                        method,
                        path,
                        json=json,
                        params=clean_params or None,
                    )
            return self._handle_response(response)
        except httpx.TimeoutException as exc:
            return self._degraded_payload(
                error_code="SIMULATOR_TIMEOUT",
                message=f"{self.service_name} timed out: {exc}",
            )
        except httpx.RequestError as exc:
            return self._degraded_payload(
                error_code="SIMULATOR_UNREACHABLE",
                message=f"{self.service_name} request error: {exc}",
            )

    async def _arequest(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            if self._async_client is not None:
                response = await self._async_client.request(
                    method,
                    path,
                    json=json,
                    params=clean_params or None,
                )
            else:
                async_transport = (
                    self._transport
                    if isinstance(self._transport, httpx.AsyncBaseTransport)
                    else None
                )
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    transport=async_transport,
                ) as client:
                    response = await client.request(
                        method,
                        path,
                        json=json,
                        params=clean_params or None,
                    )
            return self._handle_response(response)
        except httpx.TimeoutException as exc:
            return self._degraded_payload(
                error_code="SIMULATOR_TIMEOUT",
                message=f"{self.service_name} timed out: {exc}",
            )
        except httpx.RequestError as exc:
            return self._degraded_payload(
                error_code="SIMULATOR_UNREACHABLE",
                message=f"{self.service_name} request error: {exc}",
            )

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")


class CarrierSimulatorClient(_BaseSimulatorClient):
    """Client adapter for the Carrier Logistics Simulator (port 8203)."""

    service_name = "carrier_simulator"

    def __init__(self, base_url: str = "http://localhost:8203", **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)

    def create_shipment(
        self,
        *,
        return_case_id: str,
        shipkart_order_id: int | str,
        carrier_name: str = "BlueDart",
        tracking_number: str | None = None,
        scenario: str = "NORMAL_TRANSIT",
        origin_city: str = "Bengaluru",
        destination_city: str = "Mumbai",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "return_case_id": return_case_id,
            "shipkart_order_id": shipkart_order_id,
            "carrier_name": carrier_name,
            "scenario": scenario,
            "origin_city": origin_city,
            "destination_city": destination_city,
        }
        if tracking_number is not None:
            payload["tracking_number"] = tracking_number
        return self._request("POST", "/carrier/shipments", json=payload)

    def list_shipments(
        self,
        *,
        return_case_id: str | None = None,
        shipkart_order_id: int | str | None = None,
        carrier_name: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/carrier/shipments",
            params={
                "return_case_id": return_case_id,
                "shipkart_order_id": shipkart_order_id,
                "carrier_name": carrier_name,
                "status": status,
            },
        )

    def get_shipment(self, tracking_number: str) -> dict[str, Any]:
        return self._request("GET", f"/carrier/shipments/{tracking_number}")

    def advance_shipment(self, tracking_number: str) -> dict[str, Any]:
        return self._request("POST", f"/carrier/shipments/{tracking_number}/advance")

    def trigger_scenario(
        self,
        tracking_number: str,
        scenario: str,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"scenario": scenario}
        if note is not None:
            payload["note"] = note
        return self._request(
            "POST",
            f"/carrier/shipments/{tracking_number}/scenario",
            json=payload,
        )


class IssuerSimulatorClient(_BaseSimulatorClient):
    """Client adapter for the Issuer / Bank Simulator (port 8201)."""

    service_name = "issuer_simulator"

    def __init__(self, base_url: str = "http://localhost:8201", **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)

    def create_inquiry(
        self,
        *,
        refund_case_id: str,
        paypal_capture_id: str | None = None,
        paypal_refund_id: str | None = None,
        paypal_refund_status: str = "COMPLETED",
        institution_code: str = "HDFC_SIM",
        card_network: str = "VISA",
        card_last4: str = "4242",
        amount: str | None = None,
        currency: str = "USD",
        scenario: str = "NORMAL_POSTING",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/issuer/inquiries",
            json={
                "refund_case_id": refund_case_id,
                "paypal_capture_id": paypal_capture_id,
                "paypal_refund_id": paypal_refund_id,
                "paypal_refund_status": paypal_refund_status,
                "institution_code": institution_code,
                "card_network": card_network,
                "card_last4": card_last4,
                "amount": amount,
                "currency": currency,
                "scenario": scenario,
            },
        )

    def list_inquiries(
        self,
        *,
        refund_case_id: str | None = None,
        paypal_refund_id: str | None = None,
        paypal_capture_id: str | None = None,
        scenario: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/issuer/inquiries",
            params={
                "refund_case_id": refund_case_id,
                "paypal_refund_id": paypal_refund_id,
                "paypal_capture_id": paypal_capture_id,
                "scenario": scenario,
                "status": status,
            },
        )

    def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        return self._request("GET", f"/issuer/inquiries/{inquiry_id}")

    def get_timeline(self, inquiry_id: str) -> dict[str, Any]:
        return self._request("GET", f"/issuer/inquiries/{inquiry_id}/timeline")

    def advance_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        return self._request("POST", f"/issuer/inquiries/{inquiry_id}/advance")

    def trigger_scenario(
        self,
        inquiry_id: str,
        scenario: str,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"scenario": scenario}
        if note is not None:
            payload["note"] = note
        return self._request("POST", f"/issuer/scenarios/{inquiry_id}/trigger", json=payload)


class RegulatorySimulatorClient(_BaseSimulatorClient):
    """Client adapter for the India & USA Regulatory Rules Simulator (port 8202)."""

    service_name = "regulatory_simulator"
    default_degraded_status = "UNKNOWN"

    def __init__(self, base_url: str = "http://localhost:8202", **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)

    def _degraded_payload(
        self,
        *,
        error_code: str,
        message: str,
        http_status: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = super()._degraded_payload(
            error_code=error_code,
            message=message,
            http_status=http_status,
            extra=extra,
        )
        payload["disclaimer"] = REGULATORY_DISCLAIMER
        payload.setdefault("matched_rules", [])
        payload.setdefault(
            "unresolved_questions",
            ["Regulatory rules simulator unavailable; manual compliance check required."],
        )
        return payload

    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/regulatory/evaluate", json=context)

    def get_countries(self) -> dict[str, Any]:
        return self._request("GET", "/regulatory/countries")

    def get_rules(
        self,
        *,
        jurisdiction: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/regulatory/rules",
            params={"jurisdiction": jurisdiction, "version": version},
        )

    def get_transaction(self, transaction_or_eval_id: str) -> dict[str, Any]:
        return self._request("GET", f"/regulatory/transactions/{transaction_or_eval_id}")

    def get_obligations(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/regulatory/obligations/{case_id}")

    def get_violations(
        self,
        *,
        case_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/regulatory/violations",
            params={"case_id": case_id, "jurisdiction": jurisdiction},
        )

    def generate_report(
        self,
        *,
        case_id: str | None = None,
        evaluation_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/regulatory/reports/generate",
            json={"case_id": case_id, "evaluation_id": evaluation_id},
        )

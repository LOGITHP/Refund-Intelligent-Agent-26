"""Integration tests for Carrier, Issuer, and Regulatory simulators and HTTPX clients."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_BACKEND_ROOT = REPO_ROOT / "agent_backend"
if str(AGENT_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_BACKEND_ROOT))

EXPECTED_DISCLAIMER = (
    "This is a software-based rules evaluation simulation, not regulatory approval or legal advice."
)


def _load_simulator_app(simulator_dir_name: str):
    """Load a simulator FastAPI app cleanly in-process without module name clashes."""
    sim_root = REPO_ROOT / "simulators" / simulator_dir_name
    main_path = sim_root / "app" / "main.py"
    if not main_path.exists():
        raise ImportError(f"Simulator entrypoint missing: {main_path}")

    # Isolate each simulator's `app` package so importing all three in one process works cleanly.
    for mod_name in list(sys.modules):
        if mod_name == "sim_pkg" or mod_name.startswith(f"sim_{simulator_dir_name}"):
            del sys.modules[mod_name]

    sys.path.insert(0, str(sim_root))
    saved_app_modules = {
        key: val
        for key, val in sys.modules.items()
        if key == "app" or key.startswith("app.")
    }
    for key in list(saved_app_modules):
        del sys.modules[key]

    try:
        spec = importlib.util.spec_from_file_location(
            f"sim_{simulator_dir_name}.main",
            main_path,
            submodule_search_locations=[str(sim_root / "app")],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.app
    finally:
        for key in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
            del sys.modules[key]
        sys.modules.update(saved_app_modules)
        if str(sim_root) in sys.path:
            sys.path.remove(str(sim_root))


@pytest.fixture()
def carrier_app():
    return _load_simulator_app("carrier_simulator")


@pytest.fixture()
def issuer_app():
    return _load_simulator_app("issuer_simulator")


@pytest.fixture()
def regulatory_app():
    return _load_simulator_app("regulatory_simulator")


# ---------------------------------------------------------------------------
# 1. Carrier Simulator Tests (Port 8203)
# ---------------------------------------------------------------------------


def test_carrier_simulator_lifecycle_and_scenarios(carrier_app):
    client = TestClient(carrier_app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["is_simulated"] is True
    assert "SIMULATED" in health.json()["simulation_label"].upper()

    return_case_id = str(uuid.uuid4())
    create_resp = client.post(
        "/carrier/shipments",
        json={
            "return_case_id": return_case_id,
            "shipkart_order_id": 1042,
            "carrier_name": "BlueDart",
            "origin_city": "Bengaluru",
            "destination_city": "Mumbai",
        },
    )
    assert create_resp.status_code == 201
    shipment = create_resp.json()
    tracking_number = shipment["tracking_number"]
    assert tracking_number.startswith("TRK-SK-")
    assert shipment["return_case_id"] == return_case_id
    assert shipment["shipkart_order_id"] == 1042
    assert shipment["carrier_name"] == "BlueDart"
    assert shipment["current_status"] == "PICKUP_SCHEDULED"
    assert shipment["is_simulated"] is True
    assert len(shipment["events"]) == 1

    # List & filter
    list_resp = client.get("/carrier/shipments", params={"return_case_id": return_case_id})
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["is_simulated"] is True
    assert list_data["total"] == 1
    assert list_data["shipments"][0]["tracking_number"] == tracking_number

    # Advance through NORMAL_TRANSIT to DELIVERED_TO_MERCHANT
    expected_states = ["PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED_TO_MERCHANT"]
    for expected in expected_states:
        adv = client.post(f"/carrier/shipments/{tracking_number}/advance")
        assert adv.status_code == 200
        body = adv.json()
        assert body["is_simulated"] is True
        assert body["current_status"] == expected

    fetched = client.get(f"/carrier/shipments/{tracking_number}")
    assert fetched.status_code == 200
    fetched_data = fetched.json()
    assert fetched_data["is_simulated"] is True
    timestamps = [ev["occurred_at"] for ev in fetched_data["events"]]
    assert timestamps == sorted(timestamps)
    assert len(fetched_data["events"]) == 5

    # Test delay / fault scenarios on Delhivery & FedEx shipments
    for carrier_name, scenario_input, expected_status, expect_delay in [
        ("Delhivery", "pickup_overdue", "PICKUP_OVERDUE", True),
        ("FedEx", "CARRIER_STALLED", "CARRIER_STALLED", True),
        ("BlueDart", "LOST_PACKAGE", "LOST_PACKAGE", True),
        ("Delhivery", "delivered_to_merchant", "DELIVERED_TO_MERCHANT", False),
    ]:
        s_resp = client.post(
            "/carrier/shipments",
            json={
                "return_case_id": str(uuid.uuid4()),
                "shipkart_order_id": 2001,
                "carrier_name": carrier_name,
            },
        )
        assert s_resp.status_code == 201
        trk = s_resp.json()["tracking_number"]

        trig = client.post(
            f"/carrier/shipments/{trk}/scenario",
            json={"scenario": scenario_input},
        )
        assert trig.status_code == 200
        trig_data = trig.json()
        assert trig_data["is_simulated"] is True
        assert trig_data["current_status"] == expected_status
        assert trig_data["delay_detected"] is expect_delay


# ---------------------------------------------------------------------------
# 2. Issuer / Bank Simulator Tests (Port 8201, all 8 Blueprint scenarios)
# ---------------------------------------------------------------------------


def test_issuer_simulator_all_eight_scenarios_and_masked_metadata(issuer_app):
    client = TestClient(issuer_app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["is_simulated"] is True

    # Reject full PANs if accidentally sent as card_last4
    bad_pan = client.post(
        "/issuer/inquiries",
        json={
            "refund_case_id": str(uuid.uuid4()),
            "paypal_capture_id": "CAP-1",
            "paypal_refund_id": "REF-1",
            "card_network": "VISA",
            "card_last4": "4111111111114242",
        },
    )
    assert bad_pan.status_code == 422

    # 1. NORMAL_POSTING (~2 steps -> CREDIT_POSTED with ARN)
    r1 = client.post(
        "/issuer/inquiries",
        json={
            "refund_case_id": str(uuid.uuid4()),
            "paypal_capture_id": "CAP-NORM-1",
            "paypal_refund_id": "REF-NORM-1",
            "paypal_refund_status": "COMPLETED",
            "card_network": "VISA",
            "card_last4": "4242",
            "scenario": "NORMAL_POSTING",
        },
    )
    assert r1.status_code == 201
    inq1 = r1.json()
    assert inq1["is_simulated"] is True
    assert inq1["card_last4"] == "4242"
    inq1_id = inq1["inquiry_id"]

    step1 = client.post(f"/issuer/inquiries/{inq1_id}/advance")
    assert step1.status_code == 200
    assert step1.json()["is_simulated"] is True
    assert step1.json()["arn"] is not None

    step2 = client.post(f"/issuer/inquiries/{inq1_id}/advance")
    assert step2.status_code == 200
    s2 = step2.json()
    assert s2["is_simulated"] is True
    assert s2["status"] == "CREDIT_POSTED"
    assert s2["credit_posted"] is True

    tl1 = client.get(f"/issuer/inquiries/{inq1_id}/timeline")
    assert tl1.status_code == 200
    assert tl1.json()["is_simulated"] is True
    assert len(tl1.json()["events"]) >= 3

    # 2. DELAYED_POSTING (PayPal completed, issuer still pending T+5d, then posts on advance)
    r2 = client.post(
        "/issuer/inquiries",
        json={
            "refund_case_id": str(uuid.uuid4()),
            "paypal_capture_id": "CAP-DELAY-2",
            "paypal_refund_id": "REF-DELAY-2",
            "paypal_refund_status": "COMPLETED",
            "card_network": "MASTERCARD",
            "scenario": "DELAYED_POSTING",
        },
    )
    assert r2.status_code == 201
    d2 = r2.json()
    assert d2["is_simulated"] is True
    assert d2["card_last4"] == "4242"
    assert d2["credit_posted"] is False
    assert d2["posting_status"] == "ISSUER_CREDIT_PENDING"
    assert d2["delay_days"] >= 5

    # Advance once -> still delayed/pending T+5d; advance again -> finally posts
    d2_step1 = client.post(f"/issuer/inquiries/{d2['inquiry_id']}/advance").json()
    assert d2_step1["credit_posted"] is False
    assert d2_step1["posting_status"] == "ISSUER_CREDIT_PENDING"

    d2_step2 = client.post(f"/issuer/inquiries/{d2['inquiry_id']}/advance").json()
    assert d2_step2["credit_posted"] is True
    assert d2_step2["status"] == "CREDIT_POSTED"

    # 3..8 Trigger & verify remaining scenarios cleanly (including MISSING_REFERENCE alias)
    scenario_expectations = [
        ("REFERENCE_MISMATCH", "REFERENCE_MISMATCH", "ON_HOLD", False),
        ("MISSING_TRANSACTION_REFERENCE", "MISSING_TRANSACTION_REFERENCE", "UNTRACEABLE", False),
        ("MISSING_REFERENCE", "MISSING_TRANSACTION_REFERENCE", "UNTRACEABLE", False),
        ("DUPLICATE_CREDIT", "DUPLICATE_CREDIT", "DUPLICATE_DETECTED", True),
        ("REPLACED_CARD", "REPLACED_CARD", "REROUTING_TO_REPLACEMENT_CARD", False),
        ("ISSUER_UNAVAILABLE", "UNAVAILABLE", "UNKNOWN", False),
        ("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE", "AWAITING_EVIDENCE", False),
    ]
    for scenario_name, expected_status, expected_posting, expected_credit in scenario_expectations:
        base = client.post(
            "/issuer/inquiries",
            json={
                "refund_case_id": str(uuid.uuid4()),
                "paypal_capture_id": f"CAP-{scenario_name}",
                "paypal_refund_id": f"REF-{scenario_name}",
                "card_network": "RUPAY",
            },
        )
        assert base.status_code == 201
        iid = base.json()["inquiry_id"]

        trig = client.post(
            f"/issuer/scenarios/{iid}/trigger",
            json={"scenario": scenario_name},
        )
        assert trig.status_code == 200
        tdata = trig.json()
        assert tdata["is_simulated"] is True
        assert tdata["status"] == expected_status
        assert tdata["posting_status"] == expected_posting
        assert tdata["credit_posted"] is expected_credit

        if scenario_name == "ISSUER_UNAVAILABLE":
            adv_unavail = client.post(f"/issuer/inquiries/{iid}/advance")
            assert adv_unavail.status_code == 503
            assert adv_unavail.json()["is_simulated"] is True
            assert adv_unavail.json()["status"] == "UNAVAILABLE"

    # List endpoint
    listed = client.get("/issuer/inquiries")
    assert listed.status_code == 200
    assert listed.json()["is_simulated"] is True
    assert listed.json()["total"] >= 8


# ---------------------------------------------------------------------------
# 3. Regulatory Simulator Tests (Port 8202, IN & US)
# ---------------------------------------------------------------------------


def test_regulatory_simulator_versioned_rules_and_missing_context(regulatory_app):
    client = TestClient(regulatory_app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["is_simulated"] is True
    assert health.json()["disclaimer"] == EXPECTED_DISCLAIMER

    countries = client.get("/regulatory/countries").json()
    assert countries["is_simulated"] is True
    assert countries["disclaimer"] == EXPECTED_DISCLAIMER
    codes = {c["code"] for c in countries["countries"]}
    assert codes == {"IN", "US"}

    rules = client.get("/regulatory/rules").json()
    assert rules["is_simulated"] is True
    assert rules["disclaimer"] == EXPECTED_DISCLAIMER
    rule_ids = {r["rule_id"] for r in rules["rules"]}
    assert {
        "IN-RBI-FEMA-2026.1",
        "IN-CPA-ECOM-2020.1",
        "US-REG-E-2026.1",
        "US-FTC-MAIL-2026.1",
    }.issubset(rule_ids)

    # Missing countries -> UNKNOWN
    tx_unknown = str(uuid.uuid4())
    eval_unknown = client.post(
        "/regulatory/evaluate",
        json={"transaction_id": tx_unknown, "payment_provider": "PAYPAL"},
    )
    assert eval_unknown.status_code == 200
    u_data = eval_unknown.json()
    assert u_data["status"] == "UNKNOWN"
    assert len(u_data["unresolved_questions"]) >= 1
    assert u_data["is_simulated"] is True
    assert u_data["disclaimer"] == EXPECTED_DISCLAIMER

    # Countries present, missing payment_route / entity / unconfirmed settlement -> MANUAL_REVIEW_REQUIRED
    tx_manual = str(uuid.uuid4())
    eval_manual = client.post(
        "/regulatory/evaluate",
        json={
            "transaction_id": tx_manual,
            "merchant_country": "IN",
            "customer_country": "US",
            "payment_provider": "PAYPAL",
            "transaction_currency": "USD",
            "settlement_currency": "USD",
            "payment_route": "CROSS_BORDER",
            "merchant_entity_type": "BUSINESS",
            "transaction_type": "REFUND",
            "settlement_entity_confirmed": False,
        },
    )
    assert eval_manual.status_code == 200
    m_data = eval_manual.json()
    assert m_data["status"] == "MANUAL_REVIEW_REQUIRED"
    assert "IN" in m_data["jurisdiction"] and "US" in m_data["jurisdiction"]
    assert len(m_data["unresolved_questions"]) >= 1
    assert m_data["is_simulated"] is True
    assert m_data["disclaimer"] == EXPECTED_DISCLAIMER

    # Full context + excessive delay -> APPLICABLE + obligations + violations + report
    tx_full = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    eval_full = client.post(
        "/regulatory/evaluate",
        json={
            "transaction_id": tx_full,
            "refund_case_id": case_id,
            "merchant_country": "IN",
            "customer_country": "US",
            "payment_provider": "PAYPAL",
            "transaction_currency": "USD",
            "settlement_currency": "USD",
            "payment_route": "CROSS_BORDER",
            "merchant_entity_type": "BUSINESS",
            "transaction_type": "REFUND",
            "settlement_entity_confirmed": True,
            "business_activity": "ECOMMERCE_RETAIL",
            "refund_delay_hours": 240,
        },
    )
    assert eval_full.status_code == 200
    f_data = eval_full.json()
    assert f_data["status"] in ("APPLICABLE", "POTENTIALLY_APPLICABLE")
    matched_ids = {r["rule_id"] for r in f_data["matched_rules"]}
    assert "IN-RBI-FEMA-2026.1" in matched_ids
    assert "IN-CPA-ECOM-2020.1" in matched_ids
    assert "US-REG-E-2026.1" in matched_ids
    assert f_data["is_simulated"] is True
    assert f_data["disclaimer"] == EXPECTED_DISCLAIMER

    tx_lookup = client.get(f"/regulatory/transactions/{tx_full}").json()
    assert tx_lookup["is_simulated"] is True
    assert tx_lookup["disclaimer"] == EXPECTED_DISCLAIMER
    assert tx_lookup["transaction_id"] == tx_full

    obligations = client.get(f"/regulatory/obligations/{case_id}").json()
    assert obligations["is_simulated"] is True
    assert obligations["disclaimer"] == EXPECTED_DISCLAIMER
    assert len(obligations["obligations"]) >= 1

    violations = client.get("/regulatory/violations", params={"case_id": case_id}).json()
    assert violations["is_simulated"] is True
    assert violations["disclaimer"] == EXPECTED_DISCLAIMER
    assert len(violations["violations"]) >= 1

    report = client.post("/regulatory/reports/generate", json={"case_id": case_id}).json()
    assert report["is_simulated"] is True
    assert report["disclaimer"] == EXPECTED_DISCLAIMER
    assert report["case_id"] == case_id
    assert len(report["evaluations"]) == 1

    # Non-IN/US country pair -> NOT_APPLICABLE
    eval_na = client.post(
        "/regulatory/evaluate",
        json={
            "transaction_id": str(uuid.uuid4()),
            "merchant_country": "FR",
            "customer_country": "DE",
            "payment_provider": "PAYPAL",
            "payment_route": "CROSS_BORDER",
            "merchant_entity_type": "BUSINESS",
            "settlement_entity_confirmed": True,
        },
    ).json()
    assert eval_na["status"] == "NOT_APPLICABLE"
    assert eval_na["matched_rules"] == []
    assert eval_na["is_simulated"] is True
    assert eval_na["disclaimer"] == EXPECTED_DISCLAIMER

    # Filter rules by jurisdiction and test effective_date gating (2022 -> only 2020 rule matches)
    in_rules = client.get("/regulatory/rules", params={"jurisdiction": "IN"}).json()
    assert {r["rule_id"] for r in in_rules["rules"]} == {"IN-RBI-FEMA-2026.1", "IN-CPA-ECOM-2020.1"}

    eval_2022 = client.post(
        "/regulatory/evaluate",
        json={
            "transaction_id": str(uuid.uuid4()),
            "merchant_country": "IN",
            "customer_country": "IN",
            "payment_route": "DOMESTIC",
            "merchant_entity_type": "BUSINESS",
            "settlement_entity_confirmed": True,
            "business_activity": "ECOMMERCE_RETAIL",
            "evaluation_date": "2022-05-01",
        },
    ).json()
    assert eval_2022["status"] == "APPLICABLE"
    assert [r["rule_id"] for r in eval_2022["matched_rules"]] == ["IN-CPA-ECOM-2020.1"]


# ---------------------------------------------------------------------------
# 4. Python HTTPX Client Adapter Tests (ASGITransport + Graceful Degradation)
# ---------------------------------------------------------------------------


def test_httpx_simulator_clients_with_asgi_transport_and_degradation(
    carrier_app,
    issuer_app,
    regulatory_app,
):
    from app.integrations.simulators import (
        CarrierSimulatorClient,
        IssuerSimulatorClient,
        RegulatorySimulatorClient,
    )

    carrier_client = CarrierSimulatorClient(
        base_url="http://carrier.test",
        transport=httpx.ASGITransport(app=carrier_app),
    )
    issuer_client = IssuerSimulatorClient(
        base_url="http://issuer.test",
        transport=httpx.ASGITransport(app=issuer_app),
    )
    regulatory_client = RegulatorySimulatorClient(
        base_url="http://regulatory.test",
        transport=httpx.ASGITransport(app=regulatory_app),
    )

    # Carrier adapter roundtrip
    created_ship = carrier_client.create_shipment(
        return_case_id=str(uuid.uuid4()),
        shipkart_order_id=9001,
        carrier_name="FedEx",
    )
    assert created_ship["is_simulated"] is True
    trk = created_ship["tracking_number"]
    fetched_ship = carrier_client.get_shipment(trk)
    assert fetched_ship["tracking_number"] == trk
    stalled = carrier_client.trigger_scenario(trk, "CARRIER_STALLED")
    assert stalled["current_status"] == "CARRIER_STALLED"

    # Issuer adapter roundtrip including graceful 503 degradation
    inq = issuer_client.create_inquiry(
        refund_case_id=str(uuid.uuid4()),
        paypal_capture_id="CAP-ADP-1",
        paypal_refund_id="REF-ADP-1",
        scenario="ISSUER_UNAVAILABLE",
    )
    assert inq["is_simulated"] is True
    assert inq["status"] == "UNAVAILABLE"
    degraded_adv = issuer_client.advance_inquiry(inq["inquiry_id"])
    assert degraded_adv["degraded"] is True
    assert degraded_adv["status"] == "UNAVAILABLE"
    assert degraded_adv["is_simulated"] is True

    # Regulatory adapter roundtrip
    reg_res = regulatory_client.evaluate(
        {
            "transaction_id": str(uuid.uuid4()),
            "merchant_country": "US",
            "customer_country": "US",
            "payment_route": "DOMESTIC",
            "merchant_entity_type": "BUSINESS",
            "settlement_entity_confirmed": True,
            "business_activity": "ECOMMERCE_RETAIL",
        }
    )
    assert reg_res["is_simulated"] is True
    assert reg_res["disclaimer"] == EXPECTED_DISCLAIMER
    assert reg_res["status"] in ("APPLICABLE", "POTENTIALLY_APPLICABLE")

    # Timeout graceful degradation using MockTransport
    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated read timeout", request=request)

    timeout_transport = httpx.MockTransport(_raise_timeout)
    degraded_carrier = CarrierSimulatorClient(
        base_url="http://carrier.test",
        transport=timeout_transport,
    )
    degraded_issuer = IssuerSimulatorClient(
        base_url="http://issuer.test",
        transport=timeout_transport,
    )
    degraded_reg = RegulatorySimulatorClient(
        base_url="http://regulatory.test",
        transport=timeout_transport,
    )

    c_res = degraded_carrier.get_shipment("TRK-SK-TIMEOUT")
    assert c_res["degraded"] is True
    assert c_res["status"] == "UNAVAILABLE"
    assert c_res["is_simulated"] is True

    i_res = degraded_issuer.get_inquiry("INQ-TIMEOUT")
    assert i_res["degraded"] is True
    assert i_res["status"] == "UNAVAILABLE"
    assert i_res["is_simulated"] is True

    r_res = degraded_reg.evaluate({"transaction_id": "tx-timeout"})
    assert r_res["degraded"] is True
    assert r_res["status"] == "UNKNOWN"
    assert r_res["is_simulated"] is True
    assert r_res["disclaimer"] == EXPECTED_DISCLAIMER

    # Injectable TestClient + 404 SimulatorClientError
    from app.integrations.simulators import SimulatorClientError

    direct_carrier_client = CarrierSimulatorClient(client=TestClient(carrier_app))
    assert direct_carrier_client.health()["is_simulated"] is True
    with pytest.raises(SimulatorClientError) as exc_info:
        direct_carrier_client.get_shipment("TRK-SK-DOES-NOT-EXIST")
    assert exc_info.value.status_code == 404

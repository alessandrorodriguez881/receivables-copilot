"""Offline tests for the PayPal wrapper: a fake HTTP session, no network, no keys."""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rail_paypal import PayPalError, PayPalRail, money


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data if data is not None else {}
        self.ok = 200 <= status < 300
        self.content = json.dumps(self._data).encode() if data is not None else b""

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, script):
        self.script, self.calls, self.logins = list(script), [], 0

    def post(self, url, auth=None, data=None, timeout=None):
        assert url.endswith("/v1/oauth2/token")
        self.logins += 1
        return FakeResponse(200, {"access_token": f"t{self.logins}", "expires_in": 32400})

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "body": json, "params": params, "headers": headers})
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def rail(script, now=None):
    return PayPalRail("id", "secret", session=FakeSession(script), sleep=lambda s: None, clock=now or (lambda: 0.0))


def test_a_retried_reminder_resends_the_same_paypal_request_id():
    r = rail([FakeResponse(503), FakeResponse(204)])
    r.remind("INV2-1", "Friendly reminder", "Hi", request_id="remind-1")
    ids = [c["headers"]["PayPal-Request-Id"] for c in r._http.calls]
    assert ids == ["remind-1", "remind-1"]  # PayPal returns the first result: the customer gets one email


def test_a_write_without_request_id_is_never_retried():
    r = rail([requests.Timeout(), FakeResponse(200, {})])
    with pytest.raises(requests.Timeout):
        r.call("POST", "/v2/invoicing/invoices/INV2-1/payments", {"x": 1})
    assert len(r._http.calls) == 1


def test_recorded_payment_amount_is_a_two_decimal_string():
    r = rail([FakeResponse(200, {"payment_id": "P-1"})])
    r.record_payment("INV2-1", 1234.5, "2026-10-28", request_id="pay-1")
    assert r._http.calls[0]["body"]["amount"] == {"currency_code": "USD", "value": "1234.50"}


def test_expired_token_triggers_one_relogin():
    r = rail([FakeResponse(401), FakeResponse(200, {"items": []})])
    assert r.list_invoices() == []
    assert r._http.logins == 2


def test_validation_errors_name_the_field():
    body = {"name": "INVALID_REQUEST", "message": "Request is not well-formed",
            "details": [{"field": "/detail/payment_term", "issue": "INVALID_PARAMETER_VALUE"}]}
    r = rail([FakeResponse(400, body)])
    with pytest.raises(PayPalError) as e:
        r.create_draft({"detail": {}}, request_id="c-1")
    assert e.value.name == "INVALID_REQUEST" and "/detail/payment_term" in e.value.message


def test_update_is_a_full_put_with_notification_flags():
    r = rail([FakeResponse(200, {"id": "INV2-1"})])
    r.update({"id": "INV2-1", "detail": {}}, request_id="u-1")
    c = r._http.calls[0]
    assert c["method"] == "PUT" and c["params"] == {"send_to_recipient": "true", "send_to_invoicer": "false"}


def test_money_format():
    assert money(9) == {"currency_code": "USD", "value": "9.00"}

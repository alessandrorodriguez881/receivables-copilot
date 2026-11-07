"""Single wrapper for every PayPal call (Invoicing v2): token, retries and PayPal-Request-Id.

Rules:
- amounts are strings with two decimals ("100.00"), currency USD in the demo
- every POST that creates or changes something carries a PayPal-Request-Id; PayPal returns the first
  result for a repeated id, so a retry with the SAME id never sends, reminds or records a payment twice
- calls without that id are never retried
- sandbox only: from_env refuses anything else
Never logs keys or tokens.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import requests

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class PayPalError(Exception):
    def __init__(self, status: int, name: str | None, message: str | None, path: str):
        super().__init__(f"{path} -> HTTP {status} {name}: {message}")
        self.status, self.name, self.message, self.path = status, name, message, path


def read_env(path: Path) -> dict:
    values = {}
    if not path.exists():  # sin .env: modo demo con el simulador (modo.py)
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def money(value: float, currency: str = "USD") -> dict:
    return {"currency_code": currency, "value": f"{value:.2f}"}


class PayPalRail:
    def __init__(self, client_id: str, secret: str, base: str = SANDBOX_BASE, session=None,
                 max_retries: int = 3, sleep=time.sleep, clock=time.monotonic):
        self._client_id, self._secret = client_id, secret
        self.base, self.max_retries = base, max_retries
        self._http = session or requests.Session()
        self._sleep, self._clock = sleep, clock
        self._token, self._token_until = None, 0.0

    @classmethod
    def from_env(cls, path: Path, **kwargs) -> "PayPalRail":
        env = read_env(path)
        if env.get("PAYPAL_ENVIRONMENT", "SANDBOX").upper() != "SANDBOX":
            raise RuntimeError("This project only runs against the PayPal SANDBOX")
        if not (env.get("PAYPAL_CLIENT_ID") and env.get("PAYPAL_CLIENT_SECRET")):
            raise RuntimeError(f"PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are missing in {path.name}: this step needs "
                               "PayPal sandbox keys (the demo runs without them, against the simulated sandbox)")
        return cls(env["PAYPAL_CLIENT_ID"], env["PAYPAL_CLIENT_SECRET"], **kwargs)

    # ---------- plumbing ----------
    def _login(self) -> None:
        r = self._http.post(f"{self.base}/v1/oauth2/token", auth=(self._client_id, self._secret),
                            data={"grant_type": "client_credentials"}, timeout=30)
        if not r.ok:
            raise _error(r, "/v1/oauth2/token")
        data = r.json()
        self._token = data["access_token"]
        self._token_until = self._clock() + max(60, int(data.get("expires_in", 3600)) - 120)

    def _headers(self, request_id: str | None) -> dict:
        if self._token is None or self._clock() >= self._token_until:
            self._login()
        h = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json",
             "Prefer": "return=representation"}
        if request_id:
            h["PayPal-Request-Id"] = request_id
        return h

    def call(self, method: str, path: str, body: dict | None = None, params: dict | None = None,
             request_id: str | None = None):
        idempotent = method == "GET" or bool(request_id)
        relogged, attempt = False, 0
        while True:
            try:
                r = self._http.request(method, f"{self.base}{path}", json=body, params=params,
                                       headers=self._headers(request_id), timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if not idempotent or attempt >= self.max_retries:
                    raise
                attempt += 1
                self._sleep(0.5 * 2 ** attempt)
                continue
            if r.status_code == 401 and not relogged:
                self._token, relogged = None, True
                continue
            if r.status_code in RETRY_STATUSES and idempotent and attempt < self.max_retries:
                attempt += 1
                self._sleep(0.5 * 2 ** attempt)
                continue
            if not r.ok:
                raise _error(r, path)
            return r.json() if r.content else {}

    # ---------- invoices ----------
    def list_invoices(self, page_size: int = 100) -> list[dict]:
        return self.call("GET", "/v2/invoicing/invoices",
                         params={"page_size": page_size, "total_required": "true"}).get("items", [])

    def all_invoices(self, page_size: int = 100) -> list[dict]:
        """Every invoice of the account, page by page (list summaries; get_invoice has the payments)."""
        out, page = [], 1
        while True:
            data = self.call("GET", "/v2/invoicing/invoices",
                             params={"page": page, "page_size": page_size, "total_required": "true"})
            out += data.get("items", [])
            if page >= int(data.get("total_pages", 1) or 1):
                return out
            page += 1

    def get_invoice(self, invoice_id: str) -> dict:
        return self.call("GET", f"/v2/invoicing/invoices/{invoice_id}")

    def create_draft(self, invoice: dict, request_id: str | None = None) -> dict:
        return self.call("POST", "/v2/invoicing/invoices", invoice, request_id=request_id or str(uuid.uuid4()))

    def send(self, invoice_id: str, subject: str, note: str, request_id: str, notify: bool = True) -> dict:
        """notify=False sends the invoice without emailing the customer (used to load the payment history)."""
        return self.call("POST", f"/v2/invoicing/invoices/{invoice_id}/send",
                         {"subject": subject, "note": note, "send_to_recipient": notify, "send_to_invoicer": False},
                         request_id=request_id)

    def remind(self, invoice_id: str, subject: str, note: str, request_id: str) -> dict:
        return self.call("POST", f"/v2/invoicing/invoices/{invoice_id}/remind",
                         {"subject": subject, "note": note, "send_to_recipient": True, "send_to_invoicer": False},
                         request_id=request_id)

    def update(self, invoice: dict, request_id: str, notify: bool = True) -> dict:
        """Full update (PayPal does not patch invoices): used to add an early-payment discount or partial payments."""
        return self.call("PUT", f"/v2/invoicing/invoices/{invoice['id']}", invoice, request_id=request_id,
                         params={"send_to_recipient": str(notify).lower(), "send_to_invoicer": "false"})

    def cancel(self, invoice_id: str, request_id: str) -> dict:
        """Cancels a sent invoice without emailing anyone (used to tidy up an old demo round)."""
        return self.call("POST", f"/v2/invoicing/invoices/{invoice_id}/cancel",
                         {"send_to_recipient": False, "send_to_invoicer": False}, request_id=request_id)

    def record_payment(self, invoice_id: str, amount: float, payment_date: str, request_id: str,
                       method: str = "BANK_TRANSFER", note: str = "") -> dict:
        """Sandbox stand-in for the customer paying: records an external payment on the invoice."""
        return self.call("POST", f"/v2/invoicing/invoices/{invoice_id}/payments",
                         {"method": method, "payment_date": payment_date, "amount": money(amount), "note": note},
                         request_id=request_id)


def _error(r, path: str) -> PayPalError:
    try:
        data = r.json()
    except ValueError:
        data = {}
    message = data.get("message") or data.get("error_description")
    details = data.get("details")
    if details:
        message = f"{message} {[(d.get('field'), d.get('issue'), d.get('description')) for d in details]}"
    return PayPalError(r.status_code, data.get("name") or data.get("error"), message, path)

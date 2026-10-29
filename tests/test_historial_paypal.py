"""The payment history goes into PayPal once, without emailing anyone, and comes back exactly as it went in."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import historial_paypal as hp
from escenario import historial_escenario, historial_leido


class FakeRail:
    """Just enough of the Invoicing API: invoices are stored as PayPal returns them."""

    def __init__(self):
        self.invoices, self.calls = {}, []

    def all_invoices(self):
        return [{"id": i, "status": v["status"], "detail": v["detail"]} for i, v in self.invoices.items()]

    def create_draft(self, invoice, request_id=None):
        self.calls.append(("create", request_id))
        iid = f"INV2-{len(self.invoices):04d}"
        self.invoices[iid] = invoice | {"id": iid, "status": "DRAFT", "amount": {"value": "1000.00"}}
        return {"id": iid}

    def send(self, invoice_id, subject, note, request_id, notify=True):
        self.calls.append(("send", notify))
        self.invoices[invoice_id]["status"] = "SENT"

    def record_payment(self, invoice_id, amount, payment_date, request_id, note=""):
        self.calls.append(("pay", payment_date))
        inv = self.invoices[invoice_id]
        inv["status"] = "MARKED_AS_PAID"
        inv["payments"] = {"transactions": [{"payment_date": payment_date, "amount": {"value": f"{amount:.2f}"}}]}

    def get_invoice(self, invoice_id):
        return self.invoices[invoice_id]


def test_every_history_invoice_gets_a_fixed_number_paypal_accepts():
    numeros = [n for n, _ in hp.numerar(historial_escenario())]
    assert len(numeros) == len(set(numeros)) == 52 and max(map(len, numeros)) <= 25


def test_loading_the_history_emails_nobody_and_records_each_payment_on_its_real_date():
    rail = FakeRail()
    assert hp.subir(rail, log=lambda *_: None) == 52
    assert [c for c in rail.calls if c[0] == "send"] == [("send", False)] * 52
    assert sorted(c[1] for c in rail.calls if c[0] == "pay") == sorted(f.paid.isoformat() for f in historial_escenario())


def test_loading_it_again_changes_nothing():
    rail = FakeRail()
    hp.subir(rail, log=lambda *_: None)
    rail.calls.clear()
    assert hp.subir(rail, log=lambda *_: None) == 0 and rail.calls == []


def test_what_the_agent_reads_back_from_paypal_is_the_same_history():
    rail = FakeRail()
    hp.subir(rail, log=lambda *_: None)
    assert hp.leer(rail) == historial_escenario()


def test_the_saved_copy_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "HISTORIAL_PAYPAL", tmp_path / "historial_paypal.json")
    hp.guardar(historial_escenario())
    assert historial_leido(tmp_path / "historial_paypal.json") == historial_escenario()
    assert historial_leido(tmp_path / "missing.json") is None

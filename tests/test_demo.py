"""Executing the collections plan against a fake PayPal: approvals gate the big discount, nothing happens twice."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import demo
from escenario import FACTURAS, SENALES_ENSAYO
from rail_paypal import PayPalError
from triage_core.approvals import ApprovalBook
from triage_core.ledger import Ledger

IDS = {iid: f"PP-{iid}" for iid, *_ in FACTURAS}


class FakePayPal:
    def __init__(self, fail_reminders=0):
        self.invoices = {pid: {"id": pid, "status": "SENT", "detail": {"note": ""},
                               "amount": {"value": f"{a:.2f}"}, "due_amount": {"value": f"{a:.2f}"}}
                         for (iid, _, a, *_), pid in zip(FACTURAS, IDS.values())}
        self.reminders, self.updates, self.payments, self.fail = [], [], [], fail_reminders

    def get_invoice(self, pid):
        return self.invoices[pid]

    def remind(self, pid, subject, note, request_id):
        if self.fail:
            self.fail -= 1
            raise PayPalError(503, "SERVICE_UNAVAILABLE", "try later", "/remind")
        self.reminders.append((pid, request_id))

    def update(self, body, request_id):
        self.updates.append((body["id"], body["amount"]["breakdown"]["discount"], request_id))
        inv = self.invoices[body["id"]]
        inv["due_amount"] = {"value": f"{float(inv['amount']['value']) * 0.98:.2f}"}
        return inv

    def record_payment(self, pid, amount, payment_date, request_id, note=""):
        self.payments.append((pid, amount, request_id))
        self.invoices[pid].update(status="MARKED_AS_PAID", due_amount={"value": "0.00"})
        return {"payment_id": "EXTR-1"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "facturas_de", lambda ronda: IDS)
    return FakePayPal(), Ledger(tmp_path / "ledger.json"), ApprovalBook.load(tmp_path / "approvals.json")


def run(rail, libro, book):
    said = []
    s = demo.situacion(rail, "r1", SENALES_ENSAYO)
    demo.ejecutar(rail, libro, book, s, "r1", SENALES_ENSAYO, log=said.append)
    return said


def test_the_big_discount_waits_for_the_owner_and_then_goes_out_once(setup):
    rail, libro, book = setup
    said = run(rail, libro, book)
    assert rail.updates == [] and any("waits for approval" in m for m in said)
    assert len(rail.reminders) == 1  # the overdue Contoso invoice
    (fp, req), = book.pending.items()
    assert req.amount == 160.0 and "Fabrikam" in req.counterparty
    book.approve(fp, "owner")
    run(rail, libro, book)
    assert [(pid, disc["invoice_discount"]["percent"]) for pid, disc, _ in rail.updates] == [("PP-INV-103", "2")]
    run(rail, libro, book)
    assert len(rail.updates) == 1 and len(rail.reminders) == 1  # never twice


def test_a_rejected_discount_is_never_offered(setup):
    rail, libro, book = setup
    run(rail, libro, book)
    book.reject(next(iter(book.pending)), "owner")
    said = run(rail, libro, book)
    assert rail.updates == [] and any("rejected" in m for m in said)


def test_new_evidence_needs_a_new_approval(setup):
    rail, libro, book = setup
    run(rail, libro, book)
    book.approve(next(iter(book.pending)), "owner")
    s = demo.situacion(rail, "r1", SENALES_ENSAYO[:1])  # different evidence than what the owner saw
    demo.ejecutar(rail, libro, book, s, "r1", SENALES_ENSAYO[:1], log=lambda m: None)
    assert rail.updates == [] or all(pid != "PP-INV-103" for pid, *_ in rail.updates)


def test_a_failed_reminder_is_retried_with_the_same_request_id(setup):
    rail, libro, book = setup
    rail.fail = 1
    said = run(rail, libro, book)
    assert rail.reminders == [] and any("run again" in m for m in said)
    run(rail, libro, book)
    (pid, rid), = rail.reminders
    assert rid == libro.attempts("remind:r1:INV-104")[0].request_id  # same id: PayPal sends one email at most


def test_a_payment_is_recorded_once_and_the_plan_relaxes(setup):
    rail, libro, book = setup
    antes = demo.situacion(rail, "r1", SENALES_ENSAYO)
    assert demo.cobro(rail, libro, "r1", "INV-103", log=lambda m: None) == 8_000.0
    assert demo.cobro(rail, libro, "r1", "INV-103", log=lambda m: None) == 0.0
    despues = demo.situacion(rail, "r1", SENALES_ENSAYO)
    assert len(rail.payments) == 1 and despues.cobrado == 8_000.0
    assert despues.plan.p_short < antes.plan.p_short


def test_the_next_step_follows_the_order_of_the_demo(setup, monkeypatch):
    rail, libro, book = setup

    def toca(senales=SENALES_ENSAYO, pagada=False):
        return demo.paso_siguiente(demo.situacion(rail, "r1", senales or []), libro, book, "r1", senales, pagada)

    assert toca(senales=None) == "2"
    assert toca() == "3"
    run(rail, libro, book)  # the reminder goes out; the big discount waits for the owner
    assert toca() == "aprobar"
    book.approve(next(iter(book.pending)), "owner")
    assert toca() == "3 aprobado"
    run(rail, libro, book)
    assert toca() == "4"
    demo.cobro(rail, libro, "r1", "INV-103", log=lambda m: None)
    assert toca(pagada=True) is None
    monkeypatch.setattr(demo, "facturas_de", lambda ronda: {})
    assert toca() == "1"

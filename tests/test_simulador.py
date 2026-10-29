"""Modo demo sin claves: la demo entera contra el simulador de PayPal, y la repetición de la lectura de Claude."""
from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agente_ia
import escenario
import preparar_facturas
from agente_ia import Bandeja, guardar_grabacion, repetir_grabacion
from demo import cobro, ejecutar, situacion
from escenario import SENALES_ENSAYO
from rail_paypal import PayPalError, PayPalRail
from simulador_paypal import SandboxSimulado
from triage_core.approvals import ApprovalBook
from triage_core.collections_decision import DISCOUNT, ESCALATE, REMIND
from triage_core.ledger import Ledger

nada = lambda *a, **k: None


@pytest.fixture
def demo_sin_claves(tmp_path, monkeypatch):
    """Los ficheros de la ronda, en una carpeta aparte, y el simulador con las 5 facturas enviadas."""
    for nombre in ("RONDA", "REGISTRO", "SENALES", "NOTAS"):
        monkeypatch.setattr(escenario, nombre, tmp_path / getattr(escenario, nombre).name)
    monkeypatch.setattr(escenario, "DATA", tmp_path)
    rail = PayPalRail("simulated", "simulated", session=SandboxSimulado(tmp_path / "sim.json"), sleep=nada)
    return rail, preparar_facturas.main(nada, rail), tmp_path


def test_the_whole_demo_runs_without_keys(demo_sin_claves):
    rail, ronda, tmp = demo_sin_claves
    libro, book = Ledger(tmp / "ledger.json"), ApprovalBook.load(tmp / "aprobaciones.json")
    assert set(situacion(rail, ronda, []).estados.values()) == {"SENT"}

    s = situacion(rail, ronda, SENALES_ENSAYO)
    accion = {d.invoice_id: d.action for d in s.plan.decisions}
    assert accion["INV-105"] == ESCALATE and accion["INV-103"] == DISCOUNT and accion["INV-104"] == REMIND
    ejecutar(rail, libro, book, s, ronda, SENALES_ENSAYO, nada)
    assert len(book.pending) == 1  # el descuento de 160 $ espera al dueño

    book.approve(next(iter(book.pending)), "owner")
    ejecutar(rail, libro, book, situacion(rail, ronda, SENALES_ENSAYO), ronda, SENALES_ENSAYO, nada)
    assert cobro(rail, libro, ronda, "INV-103", nada) == pytest.approx(7_840)  # paga con el 2 % de descuento
    final = situacion(rail, ronda, SENALES_ENSAYO)
    assert final.estados["INV-103"] == "MARKED_AS_PAID" and final.plan.p_short == 0
    assert cobro(rail, libro, ronda, "INV-103", nada) == 0  # un cobro nunca se apunta dos veces


def test_it_behaves_like_the_sandbox_where_it_matters(demo_sin_claves):
    rail, ronda, _ = demo_sin_claves
    pid = escenario.facturas_de(ronda)["INV-101"]
    rail.remind(pid, "Reminder", "Hi", request_id="r-1")
    rail.remind(pid, "Reminder", "Hi", request_id="r-1")  # el mismo PayPal-Request-Id no manda otro correo
    assert len(rail._http.estado["facturas"][pid]["reminders"]) == 1
    rail.record_payment(pid, 1_000, "2026-10-29", request_id="p-1")
    assert rail.get_invoice(pid)["status"] == "PARTIALLY_PAID"
    with pytest.raises(PayPalError):
        rail.record_payment(pid, 9_999, "2026-10-29", request_id="p-2")  # más de lo que falta


def test_a_real_claude_run_is_replayed_and_checked_again_by_code(demo_sin_claves, monkeypatch):
    rail, ronda, tmp = demo_sin_claves
    monkeypatch.setattr(agente_ia, "GRABACION", tmp / "grabacion.json")
    recalcular = lambda ss: agente_ia.resumen(situacion(rail, ronda, ss))
    original = Bandeja(recalcular)
    for s in SENALES_ENSAYO:
        original.record_signal(s.message_id, s.customer, s.signal, s.quote)
    original.recompute_plan()
    original.draft_reminder("INV-104", "Invoice INV-104 is past due", "Hi Contoso team, a friendly reminder.")
    guardar_grabacion(original, "Briefing written by Claude", date.today())
    repetida = Bandeja(recalcular)
    assert repetir_grabacion(repetida) == "Briefing written by Claude"
    assert repetida.registro[0].startswith("Replay of a real Claude run")
    assert repetida.senales == original.senales and repetida.notas == original.notas


def test_a_customer_who_asks_for_time_gets_a_payment_plan_in_paypal(demo_sin_claves, monkeypatch):
    """Si Northwind pide más tiempo: plan de pagos (no recordatorio ni descuento), con el sí del dueño, y en PayPal la
    factura admite pagos parciales con un mínimo ya."""
    from triage_core.collections_decision import PLAN
    from triage_core.signals import Signal
    import demo
    from dataclasses import replace
    monkeypatch.setattr(demo, "POLICY", replace(demo.POLICY, payment_plans=True))  # apagados por defecto
    rail, ronda, tmp = demo_sin_claves
    libro, book = Ledger(tmp / "ledger.json"), ApprovalBook.load(tmp / "aprobaciones.json")
    senales = SENALES_ENSAYO + [Signal("msg-x", "Northwind", "asks_for_more_time", "Could we pay half now?")]
    s = situacion(rail, ronda, senales)
    assert s.plan.action_of("INV-101") == PLAN
    ejecutar(rail, libro, book, s, ronda, senales, nada)
    plan_card = [r for r in book.pending.values() if r.action == "payment_plan"]
    assert len(plan_card) == 1 and plan_card[0].amount == 1_250  # la mitad de 2.500 $
    book.approve(plan_card[0].fingerprint, "owner")
    ejecutar(rail, libro, book, situacion(rail, ronda, senales), ronda, senales, nada)
    pid = escenario.facturas_de(ronda)["INV-101"]
    parcial = rail.get_invoice(pid)["configuration"]["partial_payment"]
    assert parcial["allow_partial_payment"] and parcial["minimum_amount_due"]["value"] == "1250.00"

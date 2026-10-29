"""The PayPal 1,000-week simulator measures what it claims: known-answer weeks plus invariants on a small run."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulacion import AGENTES, Abierta, Semana, calendario_fijo, copilot, poblacion, resultado, resumir, simular
from triage_core.collections_decision import DISCOUNT, REMIND, CashNeed, Invoice, ReceivablesPolicy

POLICY = ReceivablesPolicy()


def week(luck=0.0):
    abiertas = [Abierta(Invoice("A", "C01", 5_000, 2), 0.9, 20, False, None),
                Abierta(Invoice("B", "C02", 3_000, 1), 0.9, 20, True, "disputes_invoice"),
                Abierta(Invoice("C", "C03", 2_000, 5), 0.9, 20, False, "confirms_payment")]
    return Semana(1_000, CashNeed("payroll", 6_500, 7), abiertas, np.full(3, luck))


def test_with_good_luck_everyone_pays_except_the_dispute():
    out = resultado(week(luck=0.0), {}, POLICY)  # u=0 < p for all but the disputed one (p=0.05 > 0 too)
    assert not out["corto"] and out["coste"] == 0.0


def test_a_discount_is_only_paid_when_the_money_arrives_in_the_window():
    out = resultado(week(luck=0.0), {"A": DISCOUNT}, POLICY)
    assert out["descuentos"] == 100.0  # 2% of 5,000


def test_bad_luck_means_short_on_payday_and_the_penalty():
    out = resultado(week(luck=0.99), {}, POLICY)
    assert out["corto"] and out["coste"] == POLICY.shortfall_penalty


def test_paypal_fixed_reminders_chase_everyone_due_soon_even_disputes_and_promises():
    acc = calendario_fijo(week(), POLICY)
    assert acc == {"A": REMIND, "B": REMIND}  # C is due in 5 days: too early for the fixed schedule
    out = resultado(week(), acc, POLICY)
    assert out["a_disputa"] == 1 and out["recordatorios"] == 2


def test_copilot_reading_replies_never_presses_a_dispute_or_a_promise():
    _, modelo = poblacion(np.random.default_rng(0))
    acc = copilot(week(), modelo, POLICY, leer=True, seed=1)
    assert acc["B"] not in (REMIND, DISCOUNT) and acc["C"] not in (REMIND, DISCOUNT)


def test_small_run_is_reproducible_and_complete():
    a, b = simular(6, semilla=3), simular(6, semilla=3)
    assert [r["coste"] for r in a[AGENTES[0]]] == [r["coste"] for r in b[AGENTES[0]]]
    res = resumir(a)
    # H8 y H15: pruebas de la demo; H13, H16-H20 y H21-H25 salieron con sus agentes de comparación
    esperadas = {f"H{i}" for i in range(1, 15)} - {"H8", "H13"} | {f"H{i}" for i in range(26, 31)}
    assert set(res["hipotesis"]) == esperadas and res["semanas"] == 6

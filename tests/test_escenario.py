"""The PayPal demo story, offline: what the agent does before and after reading the replies, and after a payment."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from escenario import (BANDEJA, CAJA_INICIAL, DOMINIOS, NECESIDADES, SENALES_ENSAYO, _afectadas,
                       facturas_abiertas, perfiles)
from triage_core.collections_decision import DISCOUNT, ESCALATE, REMIND, WAIT, ReceivablesPolicy, plan_collections
from triage_core.signals import Signal, SignalRejected, validate

LIMIT = ReceivablesPolicy().max_short_prob


def plan(senales, cobradas=frozenset(), extra=0.0):
    return plan_collections(facturas_abiertas(senales, cobradas), perfiles(senales), CAJA_INICIAL + extra,
                            NECESIDADES)


def test_doing_nothing_risks_the_payroll_and_the_plan_fixes_it():
    p = plan([])
    assert p.p_short_if_wait > LIMIT >= p.p_short and p.safe


def test_without_reading_replies_it_would_push_a_customer_who_disputes():
    assert plan([]).action_of("INV-105") == DISCOUNT  # the reason to read the inbox before acting


def test_after_the_replies_a_dispute_goes_to_a_person_and_a_promise_is_respected():
    p = plan(SENALES_ENSAYO)
    assert p.action_of("INV-105") == ESCALATE
    assert p.action_of("INV-102") == WAIT          # Contoso confirmed INV-102: no chasing
    assert p.action_of("INV-104") == REMIND        # their other, overdue invoice is still chased
    big = next(d for d in p.decisions if d.invoice_id == "INV-103")
    assert big.action == DISCOUNT and big.needs_approval  # 2% of 8,000 = 160 > 150: the owner approves
    assert p.safe and p.p_short_if_wait > plan([]).p_short_if_wait


def test_once_fabrikam_pays_nobody_needs_chasing():
    p = plan(SENALES_ENSAYO, cobradas={"INV-103"}, extra=7_840)
    assert p.p_short < 0.01
    assert all(d.action in (WAIT, ESCALATE) for d in p.decisions)


def test_each_reply_only_touches_the_invoices_it_names():
    dispute, promise = SENALES_ENSAYO
    assert _afectadas(dispute) == {"INV-105"}
    assert _afectadas(promise) == {"INV-102"}


def test_the_rehearsal_signals_pass_the_same_checks_as_claudes():
    correos = {m["id"]: m for m in BANDEJA}
    aceptadas = []
    for s in SENALES_ENSAYO:
        validate(s, correos, DOMINIOS, aceptadas)
        aceptadas.append(s)


def test_the_fake_fabrikam_email_cannot_mark_anything_or_count():
    correos = {m["id"]: m for m in BANDEJA}
    with pytest.raises(SignalRejected):  # sent from fabrikam-billing.example, not fabrikam.example
        validate(Signal("msg-203", "Fabrikam", "confirms_payment", "We already paid INV-103 by wire"),
                 correos, DOMINIOS, [])

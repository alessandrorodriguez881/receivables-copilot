"""Los pasos de la demo de Receivables Copilot, compartidos por la consola y la pantalla.

La verdad sobre cada factura (enviada, pagada, cuánto falta) se lee siempre de PayPal; el motor decide con eso.
Los mensajes van en inglés (son del producto). Nunca se escriben claves ni tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from escenario import (AUTOCONTROL, REVISION_RIESGO, CAJA_INICIAL, DATA, ESTUDIO, FACTURAS, NECESIDADES, facturas_abiertas,
                       facturas_de, perfiles)
from rail_paypal import PayPalError, PayPalRail, money
from triage_core.approvals import ApprovalBook, ApprovalRequest
from triage_core.collections_decision import (DISCOUNT, ESCALATE, PLAN, REMIND, CollectionsPlan, ReceivablesPolicy,
                                              plan_collections)
from triage_core.ledger import SUCCESS, DuplicatePaymentError, Ledger

ENV = Path(__file__).with_name(".env")
APROBACIONES = DATA / "aprobaciones.json"
COBRADA = {"PAID", "MARKED_AS_PAID"}
POLICY = AUTOCONTROL.policy(ReceivablesPolicy())  # sin trayectoria todavía: la política tal cual
CONCEPTO = {i: (c, a, concepto) for i, c, a, _, concepto in FACTURAS}


@dataclass
class Situacion:
    estados: dict[str, str]        # INV-xxx -> estado en PayPal
    cobrado: float                 # USD ya cobrado en esta ronda
    caja: float
    plan: CollectionsPlan
    cobrado_por: dict[str, float] | None = None  # INV-xxx -> USD cobrado de esa factura
    falta_por: dict[str, float] | None = None    # INV-xxx -> USD que PayPal aún espera (ya con el descuento, si lo hay)


def _falta(factura: dict) -> float:
    total = float(factura.get("amount", {}).get("value", 0))
    return round(float(factura.get("due_amount", {}).get("value", total)), 2)


def _cobrado(factura: dict) -> float:
    return round(float(factura.get("amount", {}).get("value", 0)) - _falta(factura), 2)


def cobrado_en_paypal(rail: PayPalRail, ronda: str) -> dict[str, float]:
    """Lo cobrado de cada factura de la ronda, leído de PayPal ahora mismo (sin recalcular el plan: es barato)."""
    return {iid: _cobrado(rail.get_invoice(pid)) for iid, pid in facturas_de(ronda).items()}


def situacion(rail: PayPalRail, ronda: str, senales: list, book: ApprovalBook | None = None) -> Situacion:
    """Con las aprobaciones (book), el plan se hace sin lo que el dueño ya rechazó en esta ronda."""
    estados, por, falta, cobradas = {}, {}, {}, set()
    for iid, pid in facturas_de(ronda).items():
        f = rail.get_invoice(pid)
        estados[iid], por[iid], falta[iid] = f.get("status", "?"), _cobrado(f), _falta(f)
        if estados[iid] in COBRADA:
            cobradas.add(iid)
    cobrado = sum(por.values())
    caja = CAJA_INICIAL + cobrado
    plan = plan_collections(facturas_abiertas(senales, cobradas, rechazadas(book, ronda, senales)), perfiles(senales),
                            caja, NECESIDADES, POLICY, risk_check=REVISION_RIESGO)
    return Situacion(estados, round(cobrado, 2), round(caja, 2), plan, por, falta)


def rechazadas(book: ApprovalBook | None, ronda: str, senales: list) -> dict[str, frozenset[str]]:
    """Lo que el dueño rechazó, factura a factura: la tarjeta de esta ronda, con estas pruebas. Su «no» vale para la
    ronda: el plan sigue sin ello (y la cuenta del riesgo ya no lo cuenta)."""
    if book is None or not book.rejected:
        return {}
    return {iid: no for iid, *_ in FACTURAS
            if (no := frozenset(a for a, tarjeta in ((DISCOUNT, tarjeta_descuento), (PLAN, tarjeta_plan))
                                if tarjeta(ronda, iid, senales).fingerprint in book.rejected))}


def evidencia(senales: list) -> tuple[str, ...]:
    return tuple(s.evidence for s in senales)


def tarjeta_descuento(ronda: str, iid: str, senales: list) -> ApprovalRequest:
    """Lo que aprueba el dueño: este descuento exacto, a este cliente, por esta factura, viendo estas pruebas."""
    cliente, importe, _ = CONCEPTO[iid]
    regalo = round(POLICY.discount_pct * importe, 2)
    return ApprovalRequest("early_payment_discount", regalo, "USD", f"{cliente}: {iid} for {importe:,.2f} USD",
                           f"{POLICY.discount_pct:.0%} off if paid within {POLICY.discount_window_days} days; above the "
                           f"{POLICY.autonomous_discount_limit:,.0f} USD the agent may give on its own",
                           (f"ronda:{ronda}", *evidencia(senales)))


def tarjeta_plan(ronda: str, iid: str, senales: list) -> ApprovalRequest:
    """Lo que aprueba el dueño: este plan de pagos exacto (lo que se paga ya), a este cliente, por esta factura."""
    cliente, importe, _ = CONCEPTO[iid]
    ya = round(POLICY.plan_first_pct * importe, 2)
    return ApprovalRequest("payment_plan", ya, "USD", f"{cliente}: {iid} for {importe:,.2f} USD",
                           f"the customer asked for more time: {ya:,.2f} USD within {POLICY.plan_first_days} days and "
                           f"the rest {POLICY.plan_rest_days} days later; changing an invoice's terms is the owner's call",
                           (f"ronda:{ronda}", *evidencia(senales)))


def nota_recordatorio(iid: str, vencida: bool) -> tuple[str, str]:
    cliente, importe, concepto = CONCEPTO[iid]
    asunto = f"{'Overdue' if vencida else 'Upcoming'}: invoice {iid} from {ESTUDIO}"
    nota = (f"Hi {cliente} team, a quick reminder about invoice {iid} ({concepto}, {importe:,.2f} USD)"
            + (", which is now past due." if vencida else ", due in the next few days.")
            + " You can pay it in one click from this email. Thank you!")
    return asunto, nota


def fecha_limite(dias: int) -> str:
    return (date.today() + timedelta(days=dias)).strftime("%b %d")


def nota_descuento() -> str:
    """La nota que lleva la factura con el descuento (la misma que enseña la pantalla antes de aprobarlo)."""
    return (f"Early-payment offer: {POLICY.discount_pct:.0%} off if paid by {fecha_limite(POLICY.discount_window_days)}. "
            f"Thank you for working with {ESTUDIO}.")


def nota_plan(ya: float) -> str:
    return (f"Payment plan: {ya:,.2f} USD by {fecha_limite(POLICY.plan_first_days)}, the rest within "
            f"{POLICY.plan_rest_days} days. Thank you for working with {ESTUDIO}.")


def ejecutar(rail: PayPalRail, libro: Ledger, book: ApprovalBook, s: Situacion, ronda: str, senales: list,
             log=print, notas: dict | None = None) -> None:
    """Hace en PayPal lo que dice el plan. Cada acción va al libro con su PayPal-Request-Id: nunca dos veces.

    notas: los recordatorios que escribió Claude (ya comprobados); si falta uno, se usa la plantilla."""
    libro.require_intact()  # con el libro o su registro tocados a mano, no se toca ninguna factura
    ids = facturas_de(ronda)
    vencimiento = {i: d for i, _, _, d, _ in FACTURAS}
    for d in s.plan.decisions:
        pid = ids.get(d.invoice_id)
        if not pid:  # la ronda no llegó a crear esta factura (paso 1 sin terminar)
            log(f"{d.invoice_id}: not in PayPal in this round; start a new round first")
            continue
        if d.action == ESCALATE:
            log(f"{d.invoice_id}: {d.reason}")
        elif d.action == REMIND:
            try:
                e = libro.begin(f"remind:{ronda}:{d.invoice_id}", "reminder", 0, "USD", CONCEPTO[d.invoice_id][0])
            except DuplicatePaymentError:
                log(f"{d.invoice_id}: already reminded in this round")
                continue
            asunto, nota = (notas or {}).get(d.invoice_id) or nota_recordatorio(d.invoice_id, vencimiento[d.invoice_id] < 0)
            try:
                rail.remind(pid, asunto, nota, request_id=e.request_id)
            except PayPalError as err:  # se queda sin cerrar: el reintento lleva el mismo id y PayPal no lo repite
                log(f"{d.invoice_id}: PayPal did not take the reminder ({err.name}); run again to retry it")
                continue
            libro.update(e, "COMPLETED", pid)
            log(f"{d.invoice_id}: reminder sent through PayPal ({d.reason})")
        elif d.action == DISCOUNT:
            aplicar_descuento(rail, libro, book, d, pid, ronda, senales, log)
        elif d.action == PLAN:
            aplicar_plan(rail, libro, book, d, pid, ronda, senales, log)


def aplicar_plan(rail: PayPalRail, libro: Ledger, book: ApprovalBook, d, pid: str, ronda: str,
                 senales: list, log=print) -> None:
    """Plan de pagos en PayPal: la factura admite pagos parciales con un mínimo ya. Siempre con el sí del dueño."""
    clave = f"plan:{ronda}:{d.invoice_id}"
    if any(e.status in SUCCESS for e in libro.attempts(clave)):
        log(f"{d.invoice_id}: payment plan already set up in this round")
        return
    req = tarjeta_plan(ronda, d.invoice_id, senales)
    if req.fingerprint in book.rejected:
        log(f"{d.invoice_id}: the owner rejected the payment plan: not offered")
        return
    if not book.is_approved(req):
        if req.fingerprint not in book.pending:
            book.request(req)
        log(f"{d.invoice_id}: payment plan waits for approval [{req.fingerprint[:8]}]: {req.counterparty}. "
            f"Why: {req.reason}")
        return
    cliente, importe, _ = CONCEPTO[d.invoice_id]
    e = libro.begin(clave, "payment_plan", req.amount, "USD", cliente)
    factura = rail.get_invoice(pid)
    cuerpo = {k: v for k, v in factura.items() if k not in ("links", "status", "due_amount", "payments", "refunds")}
    cuerpo.setdefault("configuration", {})["partial_payment"] = {"allow_partial_payment": True,
                                                                 "minimum_amount_due": money(req.amount)}
    hasta = fecha_limite(POLICY.plan_first_days)
    cuerpo["detail"]["note"] = nota_plan(req.amount)
    try:
        rail.update(cuerpo, request_id=e.request_id)
    except PayPalError as err:
        libro.update(e, "FAILED")
        log(f"{d.invoice_id}: PayPal refused the payment plan: {err}")
        return
    libro.update(e, "COMPLETED", pid)
    log(f"{d.invoice_id}: payment plan set up in PayPal: {req.amount:,.2f} USD by {hasta}, the rest later")


def aplicar_descuento(rail: PayPalRail, libro: Ledger, book: ApprovalBook, d, pid: str, ronda: str,
                      senales: list, log=print) -> None:
    clave = f"discount:{ronda}:{d.invoice_id}"
    if any(e.status in SUCCESS for e in libro.attempts(clave)):
        log(f"{d.invoice_id}: discount already offered in this round")
        return
    if d.needs_approval:
        req = tarjeta_descuento(ronda, d.invoice_id, senales)
        if req.fingerprint in book.rejected:
            log(f"{d.invoice_id}: the owner rejected this discount: not offered")
            return
        if not book.is_approved(req):
            if req.fingerprint not in book.pending:
                book.request(req)
            log(f"{d.invoice_id}: waits for approval [{req.fingerprint[:8]}]: {req.counterparty}, gives away "
                f"{req.amount:,.2f} USD. Why: {req.reason}")
            return
    cliente, importe, _ = CONCEPTO[d.invoice_id]
    e = libro.begin(clave, "discount", POLICY.discount_pct * importe, "USD", cliente)
    factura = rail.get_invoice(pid)
    cuerpo = {k: v for k, v in factura.items() if k not in ("links", "status", "due_amount", "payments", "refunds")}
    cuerpo.setdefault("amount", {}).setdefault("breakdown", {})["discount"] = {
        "invoice_discount": {"percent": f"{POLICY.discount_pct * 100:g}"}}
    hasta = fecha_limite(POLICY.discount_window_days)
    cuerpo["detail"]["note"] = nota_descuento()
    try:
        nueva = rail.update(cuerpo, request_id=e.request_id)
    except PayPalError as err:
        libro.update(e, "FAILED")
        log(f"{d.invoice_id}: PayPal refused the discount: {err}")
        return
    libro.update(e, "COMPLETED", pid)
    log(f"{d.invoice_id}: {POLICY.discount_pct:.0%} discount added in PayPal, now due "
        f"{float(nueva.get('due_amount', nueva.get('amount', {})).get('value', 0)):,.2f} USD (until {hasta})")


def cobro(rail: PayPalRail, libro: Ledger, ronda: str, iid: str, log=print) -> float:
    """Sandbox: hace de cliente que paga lo que debe hoy (un pago externo registrado en la factura)."""
    pid = facturas_de(ronda).get(iid)
    if not pid:
        log(f"{iid}: not in PayPal in this round; start a new round first")
        return 0.0
    debe = float(rail.get_invoice(pid).get("due_amount", {}).get("value", 0))
    try:
        e = libro.begin(f"payment:{ronda}:{iid}", "payment", debe, "USD", CONCEPTO[iid][0])
    except DuplicatePaymentError:
        log(f"{iid}: its payment was already recorded in this round")
        return 0.0
    r = rail.record_payment(pid, debe, date.today().isoformat(), request_id=e.request_id,
                            note="Paid within the early-payment window")
    libro.update(e, "COMPLETED", r.get("payment_id"))
    log(f"{iid}: {CONCEPTO[iid][0]} paid {debe:,.2f} USD ({rail.get_invoice(pid).get('status')})")
    return debe


PASO_3 = {REMIND: "remind", DISCOUNT: "discount", PLAN: "plan"}  # lo que hace el paso 3, con su clave en el libro


def paso_siguiente(s: Situacion, libro: Ledger, book: ApprovalBook, ronda: str, senales: list | None,
                   pagada: bool) -> str | None:
    """El paso de la demo que toca ahora, para resaltar su botón: "1" a "4", "aprobar" (una tarjeta espera al dueño),
    "3 aprobado" (el paso 3 aplica lo que aprobó), "3 otra vez" (al paso 3 aún le queda algo) o None (ya no queda nada).
    No llama a PayPal: usa la situación ya leída, el libro y las aprobaciones."""
    if len(facturas_de(ronda)) != len(FACTURAS):
        return "1"
    if senales is None:
        return "2"
    queda = aprobado = False
    for d in s.plan.decisions:
        clave = PASO_3.get(d.action)
        if clave is None or any(e.status in SUCCESS for e in libro.attempts(f"{clave}:{ronda}:{d.invoice_id}")):
            continue
        req = ((tarjeta_descuento if d.action == DISCOUNT else tarjeta_plan)(ronda, d.invoice_id, senales)
               if d.action in (DISCOUNT, PLAN) and d.needs_approval else None)
        if req is not None and req.fingerprint in book.pending:
            return "aprobar"
        if req is None or req.fingerprint not in book.rejected:
            queda, aprobado = True, aprobado or (req is not None and req.fingerprint in book.granted)
    if queda:
        hecho = any(e.status in SUCCESS and any(e.op_key.startswith(f"{c}:{ronda}:") for c in PASO_3.values())
                    for e in libro.entries)
        return "3 aprobado" if aprobado else "3 otra vez" if hecho else "3"
    return None if pagada else "4"


def cambios(antes: CollectionsPlan, despues: CollectionsPlan) -> list[tuple[str, str, str]]:
    previo = {d.invoice_id: d.action for d in antes.decisions}
    return [(d.invoice_id, previo[d.invoice_id], d.action) for d in despues.decisions
            if d.invoice_id in previo and previo[d.invoice_id] != d.action]


def mostrar(s: Situacion, log=print) -> None:
    need = NECESIDADES[0]
    log(f"Cash {s.caja:,.2f} USD (collected this round {s.cobrado:,.2f}); {need.what} {need.amount:,.0f} USD "
        f"in {need.day} days. Risk of being short: {s.plan.p_short:.1%} with the plan, "
        f"{s.plan.p_short_if_wait:.1%} if the agent does nothing")
    importe = {i: a for i, _, a, *_ in FACTURAS}
    for d in s.plan.decisions:
        log(f"   {d.invoice_id} {importe[d.invoice_id]:>9,.2f}  {s.estados.get(d.invoice_id, '?'):9} {d.action:9} "
            f"{d.reason}" + ("  -> NEEDS APPROVAL" if d.needs_approval else ""))
    for n in s.plan.notes:
        log(f"   note: {n}")

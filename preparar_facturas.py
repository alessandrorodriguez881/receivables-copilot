"""Deja el sandbox de PayPal listo para la demo: abre una ronda nueva y crea y envía las 5 facturas del escenario.

- Las facturas abiertas de la ronda anterior se cancelan sin avisar a nadie, para que la lista quede limpia
- Cada factura lleva en su número la ronda, así no choca con las de otras demos
- La factura vencida se crea con fecha de hace 30 días y vencimiento de hace 12
Solo sandbox. Nunca imprime claves ni tokens.

Uso:  python preparar_facturas.py
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import uuid

from escenario import CLIENTES, ESTUDIO, FACTURAS, facturas_de, guardar_facturas, nueva_ronda, ronda_actual
from modo import conectar
from rail_paypal import PayPalError, PayPalRail, money

ABIERTAS = {"DRAFT", "SENT", "UNPAID", "PARTIALLY_PAID", "SCHEDULED"}


def borrador(ronda: str, iid: str, cliente: str, importe: float, vence: int, concepto: str, hoy: date) -> dict:
    emitida = hoy + timedelta(days=min(0, vence - 18))  # la vencida se emitió hace 30 días
    return {
        "detail": {"currency_code": "USD", "invoice_number": f"{ronda[1:]}-{iid}",
                   "invoice_date": emitida.isoformat(), "reference": iid,
                   "note": f"Thank you for working with {ESTUDIO}.",
                   "payment_term": {"due_date": (hoy + timedelta(days=vence)).isoformat()}},
        "invoicer": {"name": {"given_name": ESTUDIO}},
        "primary_recipients": [{"billing_info": {"email_address": f"ap@{CLIENTES[cliente]['dominio']}",
                                                 "name": {"given_name": cliente, "surname": "Accounts"}}}],
        "items": [{"name": concepto, "quantity": "1", "unit_amount": money(importe)}],
    }


def main(log=print, rail: PayPalRail | None = None) -> str:
    rail = rail or conectar()
    anterior = ronda_actual()
    for iid, pid in facturas_de(anterior).items():
        try:
            if rail.get_invoice(pid).get("status") in ABIERTAS:
                rail.cancel(pid, request_id=f"cancel-{pid}")
                log(f"Round {anterior}: {iid} cancelled")
        except PayPalError as e:
            log(f"Round {anterior}: could not cancel {iid} ({e.name})")
    ronda, hoy, ids = nueva_ronda(), date.today(), {}
    for iid, cliente, importe, vence, concepto in FACTURAS:
        creada = rail.create_draft(borrador(ronda, iid, cliente, importe, vence, concepto, hoy))
        pid = creada.get("id") or creada["href"].rsplit("/", 1)[-1]
        rail.send(pid, f"Invoice {iid} from {ESTUDIO}", f"{concepto}. Thank you!", request_id=f"send-{ronda}-{iid}")
        ids[iid] = pid
        guardar_facturas(ronda, ids)
        log(f"{iid}: {importe:,.2f} USD to {cliente}, due in {vence} days -> sent ({pid})")
    log(f"New round {ronda}: {len(ids)} invoices open in the PayPal sandbox")
    return ronda


if __name__ == "__main__":
    try:
        main()
    except PayPalError as e:
        print(f"PayPal error: {e}")
        sys.exit(1)

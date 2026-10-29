"""Historial de pagos de los clientes, en PayPal: se sube una vez y el agente lo lee de vuelta con la API.

En la demo el historial es inventado (`escenario.historial_escenario`: 52 facturas de 1.000 $ de los 4 clientes).
`python historial_paypal.py` lo carga en el sandbox como facturas ya pagadas: crea cada una con su fecha, la envía
SIN avisar al cliente y registra el pago con la fecha en que llegó. Después lo lee de PayPal (vencimiento y fecha
de pago de cada factura pagada) y lo guarda en `data/historial_paypal.json`, que es lo que usa el modelo de pagos.
Repetirlo no duplica nada: cada factura lleva un número fijo y cada escritura su PayPal-Request-Id.
Solo sandbox. Nunca imprime claves ni tokens.

Uso:  python historial_paypal.py               (sube lo que falte, lee y guarda)
      python historial_paypal.py --solo-leer
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

from escenario import CLIENTES, ESTUDIO, HISTORIAL_PAYPAL, historial_escenario
from rail_paypal import PayPalError, PayPalRail, money
from triage_core.collections_model import PaidInvoice

PREFIJO = "NB-HIST-"
PAGADAS = {"PAID", "MARKED_AS_PAID"}


def numerar(historial: list[PaidInvoice]) -> list[tuple[str, PaidInvoice]]:
    """Número fijo de cada factura del historial (NB-HIST-Contoso-03): así se reconoce al volver a subirlo."""
    cuenta, out = {}, []
    for f in historial:
        cuenta[f.customer] = cuenta.get(f.customer, 0) + 1
        out.append((f"{PREFIJO}{f.customer}-{cuenta[f.customer]:02d}", f))
    return out


def borrador(numero: str, f: PaidInvoice) -> dict:
    return {
        "detail": {"currency_code": "USD", "invoice_number": numero,
                   "invoice_date": (f.due - timedelta(days=30)).isoformat(),
                   "note": f"Thank you for working with {ESTUDIO}.",
                   "payment_term": {"due_date": f.due.isoformat()}},
        "invoicer": {"name": {"given_name": ESTUDIO}},
        "primary_recipients": [{"billing_info": {"email_address": f"ap@{CLIENTES[f.customer]['dominio']}",
                                                 "name": {"given_name": f.customer, "surname": "Accounts"}}}],
        "items": [{"name": "Design work", "quantity": "1", "unit_amount": money(f.amount)}],
    }


def _del_historial(rail: PayPalRail) -> dict[str, dict]:
    return {i["detail"]["invoice_number"]: i for i in rail.all_invoices()
            if i.get("detail", {}).get("invoice_number", "").startswith(PREFIJO)}


def subir(rail: PayPalRail, log=print) -> int:
    """Crea, envía sin avisar y marca como pagadas las facturas del historial que falten. Devuelve cuántas."""
    existentes, hechas = _del_historial(rail), 0
    for numero, f in numerar(historial_escenario()):
        inv = existentes.get(numero)
        if inv and inv.get("status") in PAGADAS:
            continue
        if inv is None:
            creada = rail.create_draft(borrador(numero, f), request_id=f"hist-create-{numero}")
            pid, estado = creada.get("id") or creada["href"].rsplit("/", 1)[-1], "DRAFT"
        else:
            pid, estado = inv["id"], inv.get("status")
        if estado == "DRAFT":
            rail.send(pid, f"Invoice {numero} from {ESTUDIO}", "Design work.", request_id=f"hist-send-{numero}",
                      notify=False)
        rail.record_payment(pid, f.amount, f.paid.isoformat(), request_id=f"hist-pay-{numero}",
                            note="Earlier payment (demo history)")
        hechas += 1
        log(f"{numero}: due {f.due}, paid {f.paid} -> in PayPal")
    return hechas


def de_factura(inv: dict) -> PaidInvoice | None:
    """Una factura de PayPal ya pagada, como la ve el modelo: cliente, vencimiento, día en que se pagó, importe."""
    if inv.get("status") not in PAGADAS:
        return None
    pagos = [t.get("payment_date") for t in inv.get("payments", {}).get("transactions", []) if t.get("payment_date")]
    if not pagos:
        return None
    cliente = inv["primary_recipients"][0]["billing_info"]["name"]["given_name"]
    return PaidInvoice(cliente, date.fromisoformat(inv["detail"]["payment_term"]["due_date"]),
                       date.fromisoformat(max(pagos)[:10]), float(inv["amount"]["value"]))


def leer(rail: PayPalRail) -> list[PaidInvoice]:
    """El historial tal como está en PayPal (el detalle de cada factura trae sus pagos)."""
    filas = [de_factura(rail.get_invoice(i["id"])) for i in _del_historial(rail).values()]
    return sorted((f for f in filas if f), key=lambda f: (list(CLIENTES).index(f.customer), f.due))


def guardar(historial: list[PaidInvoice]) -> None:
    HISTORIAL_PAYPAL.parent.mkdir(exist_ok=True)
    HISTORIAL_PAYPAL.write_text(json.dumps(
        [{"customer": f.customer, "due": f.due.isoformat(), "paid": f.paid.isoformat(), "amount": f.amount}
         for f in historial], indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-leer", action="store_true")
    args = ap.parse_args()
    rail = PayPalRail.from_env(Path(__file__).with_name(".env"))
    if not args.solo_leer:
        print(f"Loaded into PayPal: {subir(rail)} invoices (the rest were already there)")
    leido = leer(rail)
    guardar(leido)
    igual = leido == historial_escenario()
    print(f"Read from PayPal: {len(leido)} paid invoices -> {HISTORIAL_PAYPAL.name}. "
          f"Same as the scenario: {'yes' if igual else 'NO'}")
    return 0 if igual else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PayPalError as e:
        print(f"PayPal error: {e}")
        sys.exit(1)

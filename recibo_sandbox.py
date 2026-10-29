"""Recibo de una ronda de la demo en el sandbox de PayPal: cada acción con su factura de PayPal, vuelta a pedir.

Lee del libro las acciones de la ronda (recordatorios, descuentos, cobros), vuelve a pedir a PayPal cada factura
(solo lectura) y escribe `evidencia/recibo_<ronda>.md`, en inglés (es para el jurado). Así se ve que la demo actuó
de verdad en el sandbox, con ids que PayPal puede confirmar. Solo con el sandbox de verdad.

Uso:  python recibo_sandbox.py [--ronda R]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from escenario import DATA, facturas_de, ronda_actual
from modo import SIMULADO, conectar
from rail_paypal import PayPalError
from triage_core.ledger import Ledger

EVIDENCIA = Path(__file__).with_name("evidencia")
QUE = {"remind": "Reminder sent", "discount": "Early-payment discount", "payment": "Payment recorded"}


def fila(rail, ids: dict, e) -> str:
    tipo, _, iid = e.op_key.split(":", 2)
    pid = ids.get(iid, "")
    ahora, detalle = "—", ""
    try:
        f = rail.get_invoice(pid)
        ahora = f"{f.get('status')}, due {float(f.get('due_amount', {}).get('value', 0)):,.2f}"
        if tipo == "discount":
            pct = f.get("amount", {}).get("breakdown", {}).get("discount", {}).get("invoice_discount", {})
            detalle = f"discount on the invoice: {pct.get('percent', '?')}%"
        elif tipo == "payment":
            pagos = f.get("payments", {}).get("transactions", [])
            detalle = "payment found on the invoice" if any(p.get("payment_id") == e.provider_id for p in pagos) \
                else "payment id not on the invoice"
    except PayPalError as err:
        ahora = f"lookup failed ({err.status})"
    return (f"| {QUE.get(tipo, tipo)} | {iid} | {e.amount:,.2f} {e.currency} | {e.counterparty} | `{pid}` | "
            f"`{e.request_id}` | {e.status} | {ahora} | {detalle} |")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ronda", default=ronda_actual())
    args = ap.parse_args()
    if SIMULADO:
        print("Receipts are for the real PayPal sandbox: add the sandbox keys to .env")
        return 1
    rail, libro, ids = conectar(), Ledger(DATA / "ledger.json"), facturas_de(args.ronda)
    entradas = [e for e in libro.entries if f":{args.ronda}:" in e.op_key]
    if not entradas:
        print(f"Nothing done in round {args.ronda}")
        return 1
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lineas = [f"# PayPal sandbox receipt: demo round `{args.ronda}`", "",
              "Every action the agent took in PayPal in this demo round, from its ledger, with the PayPal invoice "
              f"it acted on. *Ledger status* is what our ledger recorded; *Invoice now* is what PayPal answers when "
              f"asked again (read-only, on {ahora}, by `recibo_sandbox.py`). Each action carried its "
              "PayPal-Request-Id: repeating it never sends a second email or records a second payment. Invoices "
              "still open when the next demo round started were cancelled then, without emailing anyone.", "",
              "| Action | Invoice | Amount | Customer | PayPal invoice id | PayPal-Request-Id | Ledger status | "
              "Invoice now | Detail |",
              "|---|---|---|---|---|---|---|---|---|"]
    lineas += [fila(rail, ids, e) for e in entradas]
    lineas += ["", "The five invoices of the round in PayPal now:", "",
               "| Invoice | PayPal invoice id | Status | Amount | Due |", "|---|---|---|---|---|"]
    for iid, pid in ids.items():
        try:
            f = rail.get_invoice(pid)
            lineas.append(f"| {iid} | `{pid}` | {f.get('status')} | {float(f['amount']['value']):,.2f} | "
                          f"{float(f.get('due_amount', {}).get('value', 0)):,.2f} |")
        except PayPalError as err:
            lineas.append(f"| {iid} | `{pid}` | lookup failed ({err.status}) | | |")
    chequeo = libro.verify()
    if chequeo.events or not chequeo.ok:
        lineas += ["", f"Audit trail: {'verified' if chequeo.ok else 'PROBLEM: ' + chequeo.problem} "
                       f"({chequeo.events} hash-chained events; check it with `python verificar_auditoria.py`)."]
    EVIDENCIA.mkdir(exist_ok=True)
    salida = EVIDENCIA / f"recibo_{args.ronda}.md"
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Written {salida.name}: {len(entradas)} actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Ejecuta en el sandbox de PayPal el plan de Receivables Copilot para la ronda de la demo (versión de consola).

1. Lee de PayPal el estado de cada factura y lo cobrado
2. El motor decide, factura a factura: esperar, recordar, descuento por pronto pago o una persona
3. Manda los recordatorios y aplica los descuentos que el agente puede dar solo. Un descuento de más de
   150 $ sale como tarjeta de aprobación (`aprobar.py`) y se aplica en la siguiente ejecución si está aprobado

--correo registra las respuestas de los clientes (de momento, las del ensayo; con Claude, cuando haya clave).
--paga INV-xxx hace de cliente que paga (sandbox) y vuelve a calcular el plan, enseñando solo lo que cambia.
Todo va al libro de movimientos con su PayPal-Request-Id: repetir no manda ni cobra dos veces.

Uso:  python ejecutar_plan.py [--solo-plan] [--correo] [--paga INV-103]
"""
import argparse
from datetime import date
import sys

from demo import (APROBACIONES, ENV, cambios, cobro, ejecutar, mostrar, situacion)
from escenario import DATA, SENALES_ENSAYO, guardar_notas, guardar_senales, notas_de, ronda_actual, senales_de
from modo import SIMULADO, conectar
from rail_paypal import PayPalError
from triage_core.approvals import ApprovalBook
from triage_core.ledger import Ledger


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--solo-plan", action="store_true")
    p.add_argument("--correo", action="store_true", help="registra las respuestas de los clientes (ensayo)")
    p.add_argument("--paga", help="sandbox: este cliente paga su factura (p. ej. INV-103)")
    args = p.parse_args()

    rail, ronda = conectar(), ronda_actual()
    DATA.mkdir(exist_ok=True)
    libro, book = Ledger(DATA / "ledger.json"), ApprovalBook.load(APROBACIONES)
    print(f"Round {ronda}" + (" (demo mode: simulated PayPal sandbox, no keys)" if SIMULADO else ""))
    senales = senales_de(ronda)
    if args.correo and senales is None:
        try:
            from agente_ia import GRABAR, Bandeja, SinClave, cliente, guardar_grabacion, leer_bandeja, resumen
            bandeja = Bandeja(lambda ss: resumen(situacion(rail, ronda, ss)))
            explicacion = leer_bandeja(cliente(ENV), bandeja)
            if GRABAR:
                guardar_grabacion(bandeja, explicacion, date.today())
            senales = bandeja.senales
            guardar_notas(ronda, bandeja.notas)
            for paso in bandeja.registro:
                print(f"Claude: {paso}")
            print("Claude's briefing:\n" + explicacion)
        except SinClave:
            senales = SENALES_ENSAYO
            for s in senales:
                print(f"Inbox (rehearsal without Claude): recorded {s.evidence}")
        guardar_senales(ronda, senales)
    senales = senales or []

    s = situacion(rail, ronda, senales)
    if args.paga:
        cobro(rail, libro, ronda, args.paga)
        antes, s = s, situacion(rail, ronda, senales)
        print("Re-planned with the new cash. What changed: "
              + ("; ".join(f"{i} {a} -> {b}" for i, a, b in cambios(antes.plan, s.plan)) or "nothing"))
    mostrar(s)
    if not args.solo_plan:
        ejecutar(rail, libro, book, s, ronda, senales, notas=notas_de(ronda))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PayPalError, RuntimeError) as e:
        print(f"⛔ {e}")
        sys.exit(1)

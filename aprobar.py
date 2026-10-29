"""Tarjetas de aprobación de Receivables Copilot: ver las pendientes y aprobar o rechazar una.

Uso:
  python aprobar.py                         lista las pendientes
  python aprobar.py a1b2c3d4                aprueba la tarjeta (el código sale en la tarjeta)
  python aprobar.py a1b2c3d4 --rechazar     la rechaza

Solo cambia el archivo de aprobaciones: el descuento se aplica en la siguiente ejecución de ejecutar_plan.py.
"""
import argparse
import sys

from demo import APROBACIONES
from triage_core.approvals import ApprovalBook


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("codigo", nargs="?")
    p.add_argument("--rechazar", action="store_true")
    p.add_argument("--quien", default="owner")
    args = p.parse_args()
    book = ApprovalBook.load(APROBACIONES)
    if not args.codigo:
        for fp, r in book.pending.items():
            print(f"🟡 [{fp[:8]}] {r.counterparty}: gives away {r.amount:,.2f} {r.currency}. Why: {r.reason}")
            for e in r.evidence[1:]:
                print(f"   Evidence: {e}")
        if not book.pending:
            print("No approvals pending")
        return 0
    encontradas = [fp for fp in book.pending if fp.startswith(args.codigo)]
    if len(encontradas) != 1:
        print(f"No single pending card with code {args.codigo}")
        return 1
    r = book.pending[encontradas[0]]
    (book.reject if args.rechazar else book.approve)(encontradas[0], args.quien)
    print(f"{'❌ Rejected' if args.rechazar else '✅ Approved'} by {args.quien}: {r.counterparty} "
          f"({r.amount:,.2f} {r.currency})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""¿El sandbox de PayPal de verdad o el simulador?

Sin claves de PayPal en `.env` (o con RC_SIMULATED=1), todo corre contra `simulador_paypal.py`, que responde como
el sandbox a las mismas llamadas de Facturas v2: así el jurado prueba la demo sin crear cuentas. Cada modo guarda lo
suyo en su carpeta (`data/` el sandbox, `data_simulada/` el simulador), para no mezclar los libros de movimientos.
"""
from __future__ import annotations

import os
from pathlib import Path

from rail_paypal import PayPalRail, read_env

APP = Path(__file__).parent
ENV = APP / ".env"
SIMULADO = os.environ.get("RC_SIMULATED") == "1" or not read_env(ENV).get("PAYPAL_CLIENT_SECRET")
DATA = APP / ("data_simulada" if SIMULADO else "data")


def conectar() -> PayPalRail:
    """La capa de PayPal del modo actual. En el simulador, cada llamada relee el estado guardado en disco."""
    if SIMULADO:
        from simulador_paypal import SandboxSimulado
        return PayPalRail("simulated", "simulated", session=SandboxSimulado(DATA / "sandbox_simulado.json"),
                          sleep=lambda segundos: None)
    return PayPalRail.from_env(ENV)

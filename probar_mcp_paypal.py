"""¿Funciona ya el servidor MCP oficial de PayPal? Prueba de solo lectura, sin cambiar nada.

Claude se conecta al servidor oficial de PayPal (sandbox) con el conector MCP de la API y solo puede usar las
herramientas de leer facturas (lista blanca). El 29-oct, las dos respondían con un error de PayPal: «Unsupported cache
mode: default». Si un día funciona, Claude podría leer cada factura con la herramienta oficial antes de escribir el
recordatorio. Nunca imprime claves ni tokens.

Uso:  python probar_mcp_paypal.py
"""
from pathlib import Path
import sys

import anthropic

from agente_ia import cliente
from escenario import facturas_de, ronda_actual
from rail_paypal import PayPalRail

APP = Path(__file__).parent
SERVIDOR = "https://mcp.sandbox.paypal.com/sse"  # con /http, el conector no llega a conectar (29-oct)
LEER = ("list_invoices", "get_invoice")


def main() -> int:
    rail = PayPalRail.from_env(APP / ".env")
    rail._login()  # token del sandbox (dura unas horas); no se imprime
    una = next(iter(facturas_de(ronda_actual()).values()), None)
    pedido = (f"Using the PayPal tools, get invoice {una} and tell me its status, total and amount due." if una else
              "Using the PayPal tools, list my most recent invoices and tell me how many are SENT.")
    try:
        r = cliente(APP / ".env").beta.messages.create(
            model="claude-opus-5-5", max_tokens=4000, betas=["mcp-client-2025-11-20"],
            mcp_servers=[{"type": "url", "url": SERVIDOR, "name": "paypal", "authorization_token": rail._token}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "paypal", "default_config": {"enabled": False},
                    "configs": {n: {"enabled": True} for n in LEER}}],
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": pedido + " Do not change anything."}])
    except anthropic.APIStatusError as e:
        print("API error:", e.status_code, str(e.message)[:300])
        return 1
    errores = 0
    for b in r.content:
        if b.type == "mcp_tool_use":
            print("TOOL CALL:", b.name)
        elif b.type == "mcp_tool_result":
            texto = " ".join(getattr(c, "text", "") for c in (b.content or []))
            fallo = b.is_error or '"ok":false' in texto.replace(" ", "")
            errores += fallo
            print("TOOL RESULT:", "ERROR" if fallo else "ok", "-", texto[:200].replace("\n", " "))
    print("WORKS" if errores == 0 else "STILL FAILING")
    return 0 if errores == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

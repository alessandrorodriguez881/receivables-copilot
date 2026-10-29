"""Prueba de conexión con el sandbox de PayPal (facturas v2).

Lee las claves de .env, pide un token, lista las facturas y crea una factura
en borrador. Nunca imprime claves ni tokens.

Uso:  python probar_paypal.py
"""
from pathlib import Path
import sys
import uuid

import requests

BASES = {"SANDBOX": "https://api-m.sandbox.paypal.com", "PRODUCTION": "https://api-m.paypal.com"}


def leer_env(ruta: Path) -> dict:
    valores = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip()
    return valores


def main() -> int:
    env = leer_env(Path(__file__).with_name(".env"))
    entorno = env.get("PAYPAL_ENVIRONMENT", "SANDBOX").upper()
    if entorno != "SANDBOX":
        print("Parado: esta prueba solo se ejecuta contra el SANDBOX.")
        return 1
    cliente, secreto = env.get("PAYPAL_CLIENT_ID", ""), env.get("PAYPAL_CLIENT_SECRET", "")
    if not cliente or not secreto:
        print("Faltan PAYPAL_CLIENT_ID o PAYPAL_CLIENT_SECRET en .env")
        return 1
    base = BASES[entorno]

    r = requests.post(f"{base}/v1/oauth2/token", auth=(cliente, secreto),
                      data={"grant_type": "client_credentials"}, timeout=30)
    print(f"1. Token: HTTP {r.status_code}")
    if r.status_code != 200:
        print("   Las claves no valen (¿son las del Sandbox y no las de Live?)")
        return 1
    token = r.json()["access_token"]
    cab = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.get(f"{base}/v2/invoicing/invoices", headers=cab,
                     params={"page_size": 5, "total_required": "true"}, timeout=30)
    total = r.json().get("total_items", "?") if r.ok else "?"
    print(f"2. Listar facturas: HTTP {r.status_code} (facturas existentes: {total})")

    factura = {
        "detail": {"currency_code": "USD", "note": "Factura de prueba (sandbox)",
                   "payment_term": {"term_type": "NET_10"}},
        "primary_recipients": [{"billing_info": {"email_address": "cliente.prueba@example.com",
                                                 "name": {"given_name": "Cliente", "surname": "Prueba"}}}],
        "items": [{"name": "Consultoría (prueba)", "quantity": "1",
                   "unit_amount": {"currency_code": "USD", "value": "100.00"}}],
        "configuration": {"partial_payment": {"allow_partial_payment": True,
                                              "minimum_amount_due": {"currency_code": "USD", "value": "50.00"}}},
    }
    r = requests.post(f"{base}/v2/invoicing/invoices", json=factura, timeout=30,
                      headers={**cab, "PayPal-Request-Id": str(uuid.uuid4()), "Prefer": "return=representation"})
    print(f"3. Crear factura en borrador: HTTP {r.status_code}")
    if r.ok:
        datos = r.json()
        print(f"   id={datos.get('id')} estado={datos.get('status')}")
    else:
        print(f"   Error: {r.text[:300]}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())

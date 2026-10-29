"""Simulador del sandbox de PayPal (Facturas v2) para el modo demo: las mismas llamadas REST, sin red.

Hace de «sesión HTTP» debajo de `PayPalRail`, así que la demo pasa por el mismo código que con el sandbox de
verdad (token, reintentos, PayPal-Request-Id, libro, aprobaciones). Lo que imita, visto en el sandbox el 27-oct:
- Factura en DRAFT -> SENT al enviarla; recordatorio solo de facturas abiertas
- Descuento por pronto pago con un PUT completo: el importe y lo que falta por pagar se recalculan
- Un pago registrado baja lo que falta; pagada del todo queda MARKED_AS_PAID (si no, PARTIALLY_PAID)
- Un PayPal-Request-Id repetido devuelve el primer resultado y no vuelve a hacer nada
El estado se guarda en un JSON tras cada escritura y se relee en cada llamada: la pantalla y la consola ven lo mismo.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import string
from urllib.parse import urlparse

ABIERTAS = {"SENT", "UNPAID", "PARTIALLY_PAID", "SCHEDULED"}
RAIZ = "v2/invoicing/invoices"


class _Error(Exception):
    def __init__(self, status: int, name: str, message: str):
        super().__init__(message)
        self.status, self.name, self.message = status, name, message


class _Respuesta:
    """Lo poco de `requests.Response` que usa la capa."""

    def __init__(self, status: int, data=None):
        self.status_code, self._data = status, data
        self.ok = 200 <= status < 300
        self.content = b"" if data is None else json.dumps(data).encode()
        self.text = self.content.decode()

    def json(self):
        return self._data


def _dinero(valor: float) -> dict:
    return {"currency_code": "USD", "value": f"{valor:.2f}"}


def _nuevo_id() -> str:
    return "INV2-" + "-".join("".join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(4))


class SandboxSimulado:
    def __init__(self, ruta: Path | None = None):
        self.ruta = ruta
        self.estado = {"facturas": {}, "respuestas": {}}

    # ---------- la parte de requests.Session que usa PayPalRail ----------
    def post(self, url, auth=None, data=None, timeout=None, **kw):  # solo el token
        return _Respuesta(200, {"access_token": "simulated-token", "token_type": "Bearer", "expires_in": 32400})

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        self._cargar()
        ruta = urlparse(url).path.strip("/")
        id_peticion = (headers or {}).get("PayPal-Request-Id")
        clave = f"{method} {ruta} {id_peticion}"
        if id_peticion and clave in self.estado["respuestas"]:  # PayPal devuelve el primer resultado
            status, datos = self.estado["respuestas"][clave]
            return _Respuesta(status, datos)
        try:
            status, datos = 200, self._despachar(method, ruta, json or {}, params or {})
        except _Error as e:
            status, datos = e.status, {"name": e.name, "message": e.message}
        if status == 200 and datos is None:
            status = 204
        if method != "GET":
            if id_peticion and status < 500:
                self.estado["respuestas"][clave] = [status, datos]
            self._guardar()
        return _Respuesta(status, datos)

    # ---------- estado en disco ----------
    def _cargar(self) -> None:
        if self.ruta and self.ruta.exists():
            self.estado = json.loads(self.ruta.read_text(encoding="utf-8"))

    def _guardar(self) -> None:
        if self.ruta:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.ruta.write_text(json.dumps(self.estado, indent=1), encoding="utf-8")

    # ---------- los endpoints ----------
    def _despachar(self, method: str, ruta: str, body: dict, params: dict):
        facturas = self.estado["facturas"]
        if ruta == RAIZ and method == "GET":
            todas = list(facturas.values())
            tam, pag = int(params.get("page_size", 100)), int(params.get("page", 1))
            paginas = max(1, -(-len(todas) // tam))
            return {"items": todas[(pag - 1) * tam: pag * tam], "total_items": len(todas), "total_pages": paginas}
        if ruta == RAIZ and method == "POST":
            return self._crear(body)
        if not ruta.startswith(RAIZ + "/"):
            raise _Error(404, "RESOURCE_NOT_FOUND", f"the simulator does not implement {method} /{ruta}")
        id_, _, accion = ruta.removeprefix(RAIZ + "/").partition("/")
        if id_ not in facturas:
            raise _Error(404, "RESOURCE_NOT_FOUND", f"invoice {id_} not found")
        f = facturas[id_]
        if method == "GET" and not accion:
            return f
        if method == "PUT" and not accion:
            return self._actualizar(f, body)
        if method == "POST" and accion == "send":
            if f["status"] != "DRAFT":
                raise _Error(422, "UNPROCESSABLE_ENTITY", "only a draft invoice can be sent")
            f["status"] = "SENT"
            return {"links": [{"href": f"https://www.sandbox.paypal.com/invoice/p/#{id_}", "rel": "payer-view"}]}
        if method == "POST" and accion == "remind":
            if f["status"] not in ABIERTAS:
                raise _Error(422, "UNPROCESSABLE_ENTITY", f"a {f['status']} invoice cannot be reminded")
            f.setdefault("reminders", []).append(body.get("subject", ""))
            return None
        if method == "POST" and accion == "cancel":
            if f["status"] not in ABIERTAS:
                raise _Error(422, "UNPROCESSABLE_ENTITY", f"a {f['status']} invoice cannot be cancelled")
            f["status"] = "CANCELLED"
            return None
        if method == "POST" and accion == "payments":
            return self._pago(f, body)
        raise _Error(404, "RESOURCE_NOT_FOUND", f"the simulator does not implement {method} /{ruta}")

    @staticmethod
    def _importes(f: dict) -> None:
        """Como PayPal: el importe sale de las líneas menos el descuento, y lo que falta, del importe menos lo pagado."""
        lineas = sum(float(i["unit_amount"]["value"]) * float(i.get("quantity", 1)) for i in f.get("items", []))
        pct = float(f.get("amount", {}).get("breakdown", {}).get("discount", {}).get("invoice_discount", {})
                    .get("percent", 0) or 0)
        total = round(lineas * (1 - pct / 100), 2)
        pagado = round(sum(float(t["amount"]["value"]) for t in f["payments"]["transactions"]), 2)
        breakdown = {"item_total": _dinero(lineas)}
        if pct:
            breakdown["discount"] = {"invoice_discount": {"percent": f"{pct:g}", "amount": _dinero(lineas - total)}}
        f["amount"] = {**_dinero(total), "breakdown": breakdown}
        f["payments"]["paid_amount"] = _dinero(pagado)
        f["due_amount"] = _dinero(max(0.0, total - pagado))

    def _crear(self, body: dict) -> dict:
        id_ = _nuevo_id()
        f = {**body, "id": id_, "status": "DRAFT", "payments": {"transactions": []},
             "links": [{"href": f"https://api-m.sandbox.paypal.com/{RAIZ}/{id_}", "rel": "self"}]}
        self._importes(f)
        self.estado["facturas"][id_] = f
        return f

    def _actualizar(self, f: dict, body: dict) -> dict:
        for k, v in body.items():
            if k not in ("id", "status", "payments", "due_amount", "links"):
                f[k] = v
        self._importes(f)
        return f

    def _pago(self, f: dict, body: dict) -> dict:
        if f["status"] not in ABIERTAS:
            raise _Error(422, "UNPROCESSABLE_ENTITY", f"a {f['status']} invoice cannot take a payment")
        importe = float(body["amount"]["value"])
        if importe > float(f["due_amount"]["value"]) + 0.005:
            raise _Error(422, "UNPROCESSABLE_ENTITY", "the payment is larger than the amount due")
        pago_id = "EXTR-" + "".join(random.choices(string.digits, k=12))
        f["payments"]["transactions"].append({"payment_id": pago_id, "payment_date": body.get("payment_date"),
                                              "method": body.get("method", "BANK_TRANSFER"),
                                              "amount": body["amount"], "note": body.get("note", ""),
                                              "type": "EXTERNAL"})
        self._importes(f)
        f["status"] = "MARKED_AS_PAID" if float(f["due_amount"]["value"]) <= 0.005 else "PARTIALLY_PAID"
        f["payments"]["last_recorded_at"] = datetime.now(timezone.utc).isoformat()
        return {"payment_id": pago_id}

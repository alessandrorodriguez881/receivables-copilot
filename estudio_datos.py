"""Los datos y el informe inicial del panel de AG Studio (la pestaña «Dashboard» de la pantalla).

Todo sale de lo mismo que ve el resto de la pantalla: la situación leída de PayPal (`demo.situacion`), el plan del
motor y el historial de pagos. Aquí solo se ordena en tablas para AG Studio, que filtra, agrega y cruza en el
navegador. Nada de esto cambia facturas: son vistas.

Tablas (los textos van en inglés, los ve el jurado):
- `customers`: un cliente por fila; une las demás tablas (filtrar por cliente filtra todo).
- `invoices`: las 5 facturas abiertas, lo cobrado, lo que falta, la decisión del agente y la probabilidad de
  cobrar a tiempo antes y después de actuar.
- `history`: las facturas ya pagadas de cada cliente y sus días de retraso (lo que aprende el modelo).
- `payroll`: una fila con la nómina, la caja y el riesgo de quedarse corto (con el plan, sin hacer nada y el que
  acepta la política).
- `cash`: la caja prevista cada día hasta la nómina, con el plan y sin hacer nada (mediana y caso malo).
- `evaluation`: nuestra medición de 1.000 semanas simuladas frente a los recordatorios fijos, en las dos semillas
  nuevas de la sexta tanda (las mismas cifras que el vídeo y `RESULTADOS_SIMULACION.md`).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from demo import POLICY
from escenario import CAJA_INICIAL, CLIENTES, FACTURAS, HISTORIAL_MODELO, NECESIDADES, POR_CLIENTE
from historial_paypal import numerar
from triage_core.cash_simulation import cash_bands

PAGADA = ("PAID", "MARKED_AS_PAID")
ESTADO = {"PAID": "Paid", "MARKED_AS_PAID": "Paid", "PARTIALLY_PAID": "Partly paid", "SENT": "Sent",
          "UNPAID": "Unpaid", "SCHEDULED": "Scheduled", "DRAFT": "Draft", "CANCELLED": "Cancelled"}


def _campo(id_: str, nombre: str, formato: str, descripcion: str = "", oculto: bool = False) -> dict:
    c = {"id": id_, "name": nombre, "format": formato}
    if descripcion:
        c["description"] = descripcion
    if oculto:
        c["hide"] = True
    return c


def filas_facturas(s, etiquetas: Mapping[str, str], pendientes: set[str]) -> list[dict]:
    """Una fila por factura abierta de la demo. `etiquetas`: acción del motor -> texto de la pantalla.
    `pendientes`: las facturas cuya tarjeta espera el sí del dueño."""
    decision = {d.invoice_id: d for d in s.plan.decisions}
    cobrado_por, falta_por = s.cobrado_por or {}, s.falta_por or {}
    filas = []
    for iid, cliente, importe, vence, concepto in FACTURAS:
        estado, d = s.estados.get(iid), decision.get(iid)
        pagada = estado in PAGADA
        cobrado = round(cobrado_por.get(iid, 0.0), 2)
        # lo que PayPal aún espera: con un descuento aplicado, menos que el importe de la factura
        falta = falta_por.get(iid, importe - cobrado)
        filas.append({
            "id": iid, "customer": cliente, "work": concepto, "amount": float(importe), "collected": cobrado,
            "outstanding": 0.0 if pagada else round(falta, 2),
            "due_in_days": vence, "days_overdue": max(0, -vence),
            "status": ESTADO.get(estado, estado.title()) if estado else "Not sent",
            "agent_call": etiquetas[d.action] if d else ("Paid: nothing to do" if pagada else "No call yet"),
            "needs_owner": "Waiting for you" if iid in pendientes else "No",
            "odds_before": round(d.p_before, 4) if d else None,
            "odds_after": round(d.p_after, 4) if d else None,
            "reason": d.reason if d else "",
        })
    return filas


def filas_clientes() -> list[dict]:
    filas = []
    for cliente in CLIENTES:
        pagadas, tarde = POR_CLIENTE[cliente]
        retrasos = [f.days_late for f in HISTORIAL_MODELO if f.customer == cliente and f.days_late > 0]
        filas.append({"name": cliente, "paid_invoices": pagadas, "late_invoices": tarde,
                      "late_share": round(tarde / pagadas, 4) if pagadas else 0.0,
                      "avg_days_late_when_late": round(sum(retrasos) / len(retrasos), 1) if retrasos else 0.0})
    return filas


def filas_historial() -> list[dict]:
    return [{"invoice": numero, "customer": f.customer, "amount": float(f.amount), "due": f.due.isoformat(),
             "paid": f.paid.isoformat() if f.paid else None, "due_month": f.due.strftime("%Y-%m"),
             "days_late": f.days_late, "timeliness": "Paid late" if f.days_late > 0 else "On time"}
            for numero, f in numerar(HISTORIAL_MODELO)]


def fila_nomina(s) -> dict:
    need = NECESIDADES[0]
    return {"what": need.what.capitalize(), "payroll": float(need.amount), "payday_in_days": need.day,
            "bank_cash": CAJA_INICIAL, "collected": round(s.cobrado, 2), "cash": round(s.caja, 2),
            "gap": round(max(0.0, need.amount - s.caja), 2),
            "chance_short": round(s.plan.p_short, 4), "chance_short_if_nothing": round(s.plan.p_short_if_wait, 4),
            "risk_limit": POLICY.max_short_prob}


RESULTADOS = Path(__file__).parent / "resultados"
SEMILLAS = (2040, 2041)  # la sexta tanda, con semillas nuevas: las cifras del vídeo y de RESULTADOS_SIMULACION.md
ESTRATEGIAS = {"Receivables Copilot": "Receivables Copilot", "PayPal fixed reminders": "PayPal-style fixed reminders"}


@lru_cache(maxsize=1)
def _evaluacion() -> tuple[dict, ...]:
    filas = []
    for semilla in SEMILLAS:
        agentes = json.loads((RESULTADOS / f"simulacion_1000_semilla{semilla}.json").read_text(encoding="utf-8"))
        for clave, nombre in ESTRATEGIAS.items():
            a = agentes["agentes"][clave]
            filas.append({"id": f"{semilla}-{clave}", "seed": str(semilla), "strategy": nombre,
                          "weeks_short": round(a["corto_pct"] / 100, 4),
                          "reminders_per_week": round(a["recordatorios_por_semana"], 2),
                          "weeks_chasing_disputed": int(a["semanas_presionando_disputa"])})
    return tuple(filas)


def filas_evaluacion() -> list[dict]:
    """Copilot frente a los recordatorios fijos, por semilla (vacío si faltan los resultados: el panel sigue)."""
    try:
        return [dict(f) for f in _evaluacion()]
    except (OSError, ValueError, KeyError):
        return []


def filas_caja(s) -> list[dict]:
    """La caja de cada día hasta la nómina (mediana y caso malo, 1 de cada 20), con el plan y sin hacer nada:
    lo mismo que dibuja la gráfica de la pestaña Invoices, en tabla."""
    need = NECESIDADES[0]
    salidas = [(n.day, n.amount) for n in NECESIDADES]
    etiquetas = ["Day 0 (today)"] + [f"Day {i}" for i in range(1, need.day)] + [f"Day {need.day} ({need.what})"]
    filas = []
    for escenario, recibos in (("Agent's plan", s.plan.receipts), ("Doing nothing", s.plan.receipts_if_wait)):
        b = cash_bands(s.caja, recibos, salidas, need.day)
        filas += [{"id": f"{escenario}-{i}", "day": etiquetas[i], "scenario": escenario, "median": round(me, 2),
                   "bad_case": round(lo, 2)} for i, (lo, me) in enumerate(zip(b[5], b[50]))]
    return filas


def fuentes(s, etiquetas: Mapping[str, str], pendientes: set[str]) -> dict:
    """Las fuentes de datos de AG Studio (`AgDataSourcesDefinition`) para la situación `s`."""
    need = NECESIDADES[0]
    return {
        "description": ("Receivables of Northbeam Studio, a small design studio that bills its customers with "
                        f"PayPal invoices. Payroll of ${need.amount:,.0f} is due in {need.day} days. Amounts are "
                        "USD. The collections agent picks one action per open invoice; this dashboard only shows "
                        "data, it cannot change invoices."),
        "sources": [
            {"id": "customers", "name": "Customers", "description": "One row per customer.",
             "data": filas_clientes(),
             "fields": [_campo("name", "Customer", "textFormat"),
                        _campo("paid_invoices", "Paid invoices", "integerFormat",
                               "Earlier invoices this customer has paid"),
                        _campo("late_invoices", "Paid late", "integerFormat", "How many of them were paid late"),
                        _campo("late_share", "Share paid late", "percentageFormat"),
                        _campo("avg_days_late_when_late", "Avg days late (when late)", "decimalFormat")]},
            {"id": "invoices", "name": "Open invoices",
             "description": ("The invoices of this round. outstanding is what the customer still owes (0 once "
                             "paid). odds_before/odds_after: chance the invoice is paid on time before and after "
                             "the agent's action."),
             "data": filas_facturas(s, etiquetas, pendientes),
             "fields": [_campo("id", "Invoice", "textFormat"),
                        _campo("customer", "Customer", "textFormat", oculto=True),
                        _campo("work", "Work", "textFormat"),
                        _campo("amount", "Amount", "currencyFormat"),
                        _campo("collected", "Collected", "currencyFormat", "Paid so far through PayPal"),
                        _campo("outstanding", "Still owed", "currencyFormat", "What the customer still owes"),
                        _campo("due_in_days", "Due in (days)", "integerFormat", "Negative means overdue"),
                        _campo("days_overdue", "Days overdue", "integerFormat"),
                        _campo("status", "Status in PayPal", "textFormat"),
                        _campo("agent_call", "Agent's call", "textFormat"),
                        _campo("needs_owner", "Needs the owner", "textFormat",
                               "Waiting for you: the call needs the owner's approval first"),
                        _campo("odds_before", "On-time odds without it", "percentageFormat",
                               "Chance it is paid on time if the agent does nothing"),
                        _campo("odds_after", "On-time odds with the call", "percentageFormat",
                               "Chance it is paid on time after the agent's call"),
                        _campo("reason", "Why", "textFormat")]},
            {"id": "history", "name": "Payment history",
             "description": "Earlier invoices each customer has already paid, with how many days late.",
             "data": filas_historial(),
             "fields": [_campo("invoice", "Paid invoice", "textFormat"),
                        _campo("customer", "Customer", "textFormat", oculto=True),
                        _campo("amount", "Amount", "currencyFormat"),
                        _campo("due", "Due date", "dateFormat"),
                        _campo("paid", "Paid date", "dateFormat"),
                        _campo("due_month", "Due month", "textFormat"),
                        _campo("days_late", "Days late", "integerFormat"),
                        _campo("timeliness", "On time or late", "textFormat")]},
            {"id": "payroll", "name": "Payroll", "description": "One row: the payroll and the cash to pay it.",
             "data": [fila_nomina(s)],
             "fields": [_campo("what", "Cash need", "textFormat"),
                        _campo("payroll", "Payroll", "currencyFormat"),
                        _campo("payday_in_days", "Payday in (days)", "integerFormat"),
                        _campo("bank_cash", "Cash in the bank", "currencyFormat"),
                        _campo("collected", "Collected this round", "currencyFormat"),
                        _campo("cash", "Cash available", "currencyFormat", "Bank cash plus what PayPal collected"),
                        _campo("gap", "Still missing for payroll", "currencyFormat"),
                        _campo("chance_short", "Chance of being short", "percentageFormat",
                               "With the agent's plan, over 5,000 simulated scenarios"),
                        _campo("chance_short_if_nothing", "Chance of being short if it does nothing",
                               "percentageFormat"),
                        _campo("risk_limit", "Risk the policy accepts", "percentageFormat",
                               "The plan must keep the chance of being short under this")]},
            {"id": "evaluation", "name": "1,000 simulated weeks",
             "description": ("Our evaluation: 1,000 simulated weeks on each of two fresh seeds, the same weeks and "
                             "the same luck for both strategies, with hypotheses written before running "
                             "(RESULTADOS_SIMULACION.md). weeks_short is the share of weeks short of cash on "
                             "payday. The Copilot is not cheaper than fixed reminders: about the same cost a week."),
             "data": filas_evaluacion(),
             "fields": [_campo("id", "Row", "textFormat", oculto=True),
                        _campo("seed", "Seed", "textFormat"),
                        _campo("strategy", "Strategy", "textFormat"),
                        _campo("weeks_short", "Weeks short on payday", "percentageFormat"),
                        _campo("reminders_per_week", "Reminders per week", "decimalFormat"),
                        _campo("weeks_chasing_disputed", "Weeks chasing a disputed invoice", "integerFormat")]},
            {"id": "cash", "name": "Cash until payroll",
             "description": "Simulated cash each day until payroll: median and a bad case (1 in 20).",
             "data": filas_caja(s),
             "fields": [_campo("id", "Row", "textFormat", oculto=True),
                        _campo("day", "Day", "textFormat"),
                        _campo("scenario", "Scenario", "textFormat"),
                        _campo("median", "Expected cash (median)", "currencyFormat"),
                        _campo("bad_case", "Cash on a bad day (1 in 20)", "currencyFormat")]},
        ],
        "relationships": [
            {"id": "invoice-customer", "type": "many-to-one", "source": {"tableId": "invoices", "fieldId": "customer"},
             "target": {"tableId": "customers", "fieldId": "name"}},
            {"id": "history-customer", "type": "many-to-one", "source": {"tableId": "history", "fieldId": "customer"},
             "target": {"tableId": "customers", "fieldId": "name"}},
        ],
    }


# ---------- el informe que se abre al entrar (estado de AG Studio guardado en código) ----------
def _sitio(x: int, y: int, ancho: int, alto: int) -> dict:
    return {"xTrack": x, "yTrack": y, "xSpan": ancho, "ySpan": alto}


def _titulo(texto: str, subtitulo: str = "") -> dict:
    t = {"title": {"enabled": True, "text": texto}}
    if subtitulo:
        t["subtitle"] = {"enabled": True, "text": subtitulo}
    return t


def _suma(id_: str) -> dict:
    return {"id": id_, "aggregation": "sum"}


def _media(id_: str) -> dict:
    return {"id": id_, "aggregation": "avg"}


def _kpi(texto: str, valor: dict) -> dict:
    return {"type": "value", "dataMapping": {"value": [valor]}, "format": _titulo(texto)}


MARCADOR = "rc-who-owes"     # widget propio: quién debe qué, como un marcador amable
NOMINA = "rc-payroll-meter"  # widget propio: cuánto de la nómina está cubierto
RIESGO = "rc-payroll-risk"   # widget propio: el riesgo de no llegar a la nómina, con el plan y sin hacer nada
FRENTE = "rc-vs-fixed"       # widget propio: 1.000 semanas simuladas frente a los recordatorios fijos

INFORME = {
    "selectedPageId": "collections",
    # editando, los filtros y la lista de campos empiezan plegados: el lienzo y el asistente tienen sitio
    "panels": {"filters": {"collapsed": True}, "data": {"collapsed": True}},
    "pages": [{
        "id": "collections",
        "widgets": {
            "kpi-owed": _kpi("Still owed to us", _suma("invoices.outstanding")),
            "kpi-collected": _kpi("Collected so far", _suma("invoices.collected")),
            "payroll-risk": {
                "type": RIESGO,
                "dataMapping": {"plan": [_suma("payroll.chance_short")],
                                "nothing": [_suma("payroll.chance_short_if_nothing")],
                                "limit": [_suma("payroll.risk_limit")]},
                "format": _titulo("Risk of missing payroll", "Over 5,000 simulated scenarios"),
            },
            "payroll-meter": {
                "type": NOMINA,
                "dataMapping": {"cash": [_suma("payroll.cash")], "target": [_suma("payroll.payroll")]},
                "format": _titulo("Payroll covered", "Cash available against payroll"),
            },
            "who-owes": {
                "type": MARCADOR,
                "dataMapping": {"who": [{"id": "customers.name"}], "owes": [_suma("invoices.outstanding")],
                                "paid": [_suma("invoices.collected")]},
                "format": _titulo("Who still owes what", "Click a customer to filter the whole page"),
            },
            "odds": {
                "type": "column-chart-grouped",
                "dataMapping": {"categoryKey": [{"id": "invoices.id"}],
                                "valueKey": [_media("invoices.odds_after"), _media("invoices.odds_before")]},
                # sin etiquetas en las barras: con dos barras por factura se pisaban (el valor sale al pasar el ratón)
                "format": {**_titulo("On-time odds: with the agent's call vs without it", "Per open invoice"),
                           "style": {"theme": {"common": {"legend": {"enabled": True}}}}},
            },
            "calls": {
                "type": "grid",
                # lo que cabe sin cortar columnas: las probabilidades están en la gráfica de al lado, y el porqué de
                # cada decisión, en la pestaña Invoices (un texto largo se comía el ancho de la tabla)
                "dataMapping": {"cols": [{"id": "invoices.id"}, {"id": "customers.name"},
                                         {"id": "invoices.agent_call"}, {"id": "invoices.status"},
                                         {"id": "invoices.due_in_days"}, _suma("invoices.amount"),
                                         _suma("invoices.outstanding")]},
                "sort": [{"field": {"id": "invoices.due_in_days"}, "direction": "asc"}],
                "format": {**_titulo("The agent's call on each invoice", "One row per open invoice"),
                           "style": {"columnAutoSize": True}},
            },
            "days-late": {
                "type": "bar-chart-grouped",
                "dataMapping": {"categoryKey": [{"id": "customers.name"}],
                                "valueKey": [_media("history.days_late")]},
                "format": _titulo("Average days late", "Across each customer's paid invoices"),
            },
            "on-time": {
                "type": "column-chart-stacked",
                "dataMapping": {"categoryKey": [{"id": "customers.name"}],
                                "valueKey": [{"id": "history.invoice", "aggregation": "count"}],
                                "legendKey": [{"id": "history.timeliness"}]},
                "format": {**_titulo("Paid on time or late", "Earlier invoices, read from PayPal"),
                           "style": {"theme": {"common": {"legend": {"enabled": True}}}}},
            },
            "cash": {
                "type": "line-chart",
                "dataMapping": {"categoryKey": [{"id": "cash.day"}], "valueKey": [_suma("cash.bad_case")],
                                "legendKey": [{"id": "cash.scenario"}]},
                "format": {**_titulo("Cash on a bad day until payroll", "1-in-20 worst case, with the plan and "
                                                                         "doing nothing"),
                           "style": {"theme": {"common": {"legend": {"enabled": True}}}}},
            },
            "vs-fixed": {
                "type": FRENTE,
                "dataMapping": {"who": [{"id": "evaluation.strategy"}],
                                "short": [_media("evaluation.weeks_short")],
                                "reminders": [_media("evaluation.reminders_per_week")],
                                "disputed": [_media("evaluation.weeks_chasing_disputed")]},
                "format": _titulo("Receivables Copilot vs fixed reminders",
                                  "1,000 simulated weeks on two fresh seeds, the same weeks and luck for both "
                                  "(averages). Lower is better"),
            },
        },
        "widgetLayout": {
            "kpi-owed": _sitio(0, 0, 5, 8),
            "kpi-collected": _sitio(5, 0, 5, 8),
            "payroll-risk": _sitio(10, 0, 6, 8),
            "payroll-meter": _sitio(16, 0, 8, 8),
            "who-owes": _sitio(0, 8, 10, 20),
            "odds": _sitio(10, 8, 14, 20),
            "calls": _sitio(0, 28, 24, 19),
            "days-late": _sitio(0, 47, 8, 16),
            "on-time": _sitio(8, 47, 8, 16),
            "cash": _sitio(16, 47, 8, 16),
            "vs-fixed": _sitio(0, 63, 24, 12),
        },
    }],
}


def campos_usados(informe: dict = INFORME) -> set[str]:
    """Los ids de campo (`tabla.campo`) que usa el informe, para comprobar que existen."""
    usados = set()
    for pagina in informe["pages"]:
        for w in pagina["widgets"].values():
            for lista in w.get("dataMapping", {}).values():
                usados |= {c["id"] for c in lista}
            usados |= {o["field"]["id"] for o in w.get("sort", [])}
    return usados

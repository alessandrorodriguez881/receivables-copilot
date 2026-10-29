"""El techo: ¿cuánto ganaría un agente que supiera la verdad? (semillas YA USADAS; no cuenta como prueba)

El «oráculo» sabe lo que ningún agente puede saber: la probabilidad verdadera de cada cliente, el efecto real de un
recordatorio y de un descuento, lo que resta estar vencida y cómo se reparten los retrasos. Lee las respuestas como
Copilot y las usa bien (con las probabilidades con que la simulación las genera). No sabe la suerte de la semana.
Decide con la misma regla que Copilot: el plan más barato que deja el riesgo de quedarse corto por debajo del 5 %;
si ninguno lo deja, el más barato contando el riesgo.

Si el oráculo tampoco es más barato que los recordatorios fijos, «no es más barato» es un límite del escenario
(semanas que ninguna acción salva), no de nuestra previsión.

Uso:  python techo_oraculo.py [--semilla 2038] [--semanas 1000]
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import product
import json

import numpy as np

from simulacion import (LIFT_DESCUENTO, LIFT_RECORDATORIO, P_DISPUTA_PAGA, P_VENCIDA, RESULTADOS, calendario_fijo,
                        poblacion, resultado, semana)
from triage_core.cash_simulation import ExpectedReceipt, simulate
from triage_core.collections_decision import DISCOUNT, ESCALATE, REMIND, WAIT, ReceivablesPolicy, _options
from triage_core.collections_model import CustomerProfile

# Cómo genera la simulación las respuestas (sin disputa): P(respuesta | pagaría a tiempo), P(respuesta | tarde)
P_RESPUESTA = {"confirms_payment": (0.30, 0.05), "asks_for_more_time": (0.70 * 0.10, 0.95 * 0.40),
               None: (0.70 * 0.90, 0.95 * 0.60)}


def p_verdadera(abierta, accion: str) -> float:
    """Probabilidad de pagar a tiempo con esa acción, sabiendo la respuesta (la suerte de la semana, no)."""
    if abierta.disputa:
        return P_DISPUTA_PAGA
    vencida = abierta.factura.due_day < 0
    q = abierta.p_real * (P_VENCIDA if vencida else 1.0)              # pagaría a tiempo sin que nadie empuje
    odds = abierta.p_real / (1 - abierta.p_real) * {REMIND: LIFT_RECORDATORIO, DISCOUNT: LIFT_DESCUENTO}.get(accion, 1.0)
    pa = odds / (1 + odds) * (P_VENCIDA if vencida else 1.0)          # con la acción (como en `resultado`)
    si, no = P_RESPUESTA[abierta.respuesta]
    return (q * si + max(pa - q, 0.0) * no) / (q * si + (1 - q) * no)


def plan_oraculo(s, retrasos: dict[str, np.ndarray], policy: ReceivablesPolicy, seed: int) -> dict[str, str]:
    menu = []
    for a in s.abiertas:
        inv = replace(a.factura, disputed=a.disputa, promised=a.respuesta == "confirms_payment")
        menu.append(_options(inv, policy))
    mejor_seguro = mejor = None
    for acciones in product(*menu):
        recibos, coste = [], 0.0
        for a, acc in zip(s.abiertas, acciones):
            p = p_verdadera(a, WAIT if acc == ESCALATE else acc)
            vence, importe = max(a.factura.due_day, 0), a.factura.amount
            if acc == REMIND:
                coste += policy.reminder_cost
            elif acc == DISCOUNT:
                vence = min(vence, policy.discount_window_days)
                coste += policy.discount_pct * importe * p
                importe *= 1 - policy.discount_pct
            prof = CustomerProfile(a.factura.customer, 0, p, retrasos[a.factura.customer])
            recibos.append((ExpectedReceipt(a.factura.customer, importe, vence), prof))
        riesgo = simulate(s.caja, recibos, [(s.nominas.day, s.nominas.amount)], reserve=0.0,
                          horizon_days=s.nominas.day, seed=seed).p_breach
        total = coste + policy.shortfall_penalty * riesgo
        clave = (round(total, 2), sum(x not in (WAIT, ESCALATE) for x in acciones))
        if riesgo <= policy.max_short_prob and (mejor_seguro is None or clave < mejor_seguro[0]):
            mejor_seguro = (clave, acciones)
        if mejor is None or clave < mejor[0]:
            mejor = (clave, acciones)
    elegido = (mejor_seguro or mejor)[1]
    return {a.factura.id: acc for a, acc in zip(s.abiertas, elegido)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semilla", type=int, default=2038)
    ap.add_argument("--semanas", type=int, default=1000)
    args = ap.parse_args()
    policy = ReceivablesPolicy()
    rng = np.random.default_rng(args.semilla)
    clientes, _ = poblacion(rng)
    sorteo = np.random.default_rng(7)  # solo para la forma de los retrasos que conoce el oráculo
    retrasos = {c.nombre: 1 + sorteo.poisson(c.retraso_medio, 400) for c in clientes}
    filas = {"oraculo": [], "fijos": []}
    for i in range(args.semanas):
        s = semana(rng, clientes, i)
        filas["oraculo"].append(resultado(s, plan_oraculo(s, retrasos, policy, i), policy))
        filas["fijos"].append(resultado(s, calendario_fijo(s, policy), policy))
    out = {}
    for a, f in filas.items():
        out[a] = {"corto_pct": 100 * float(np.mean([r["corto"] for r in f])),
                  "coste_medio": float(np.mean([r["coste"] for r in f])),
                  "descuentos_medios": float(np.mean([r["descuentos"] for r in f])),
                  "recordatorios_por_semana": float(np.mean([r["recordatorios"] for r in f]))}
    d = np.array([x["coste"] - y["coste"] for x, y in zip(filas["oraculo"], filas["fijos"])])
    e = d.std(ddof=1) / np.sqrt(len(d))
    out["coste: oráculo - fijos (USD)"] = [float(d.mean()), float(d.mean() - 1.96 * e), float(d.mean() + 1.96 * e)]
    RESULTADOS.mkdir(exist_ok=True)
    (RESULTADOS / f"techo_oraculo_{args.semanas}_semilla{args.semilla}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

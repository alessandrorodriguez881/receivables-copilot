"""Diagnóstico (28-oct): ¿de dónde sale el coste de más de Copilot frente a los recordatorios fijos?

Solo con semillas YA usadas (2030 y 2031), para no gastar las nuevas. Para cada semana guarda si el plan del
motor era «seguro» (riesgo por debajo del 5 %), cuánto descuento dio de verdad y si faltó dinero. Compara además
variantes del motor: sin descuentos (lift 1: un descuento no ayuda y nunca se elige) y sin el tope del 5 %
(solo el coste esperado, con la penalización de 1.500 $).

Uso:  python diagnostico_descuentos.py --semilla 2030 [--semanas 1000]
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json

import numpy as np

from simulacion import (RESULTADOS, CollectionsModel, ReceivablesPolicy, SIGNAL_LIKELIHOOD, DISCOUNT,
                        calendario_fijo, plan_collections, poblacion, resultado, semana)

VARIANTES = {"actual": {}, "sin descuentos": {"discount_lift": 1.0}, "sin tope del 5 %": {"max_short_prob": 0.0}}


def plan_copilot(s, modelo, policy, seed):
    perfiles, facturas = {}, []
    for a in s.abiertas:
        p = perfiles.get(a.factura.customer, modelo.profile(a.factura.customer))
        inv = a.factura
        if a.respuesta:
            if a.respuesta == "disputes_invoice":
                inv = replace(inv, disputed=True)
            elif a.respuesta == "confirms_payment":
                inv = replace(inv, promised=True)
            p = CollectionsModel.apply_signal(p, SIGNAL_LIKELIHOOD[a.respuesta], a.respuesta)
        perfiles[a.factura.customer] = p
        facturas.append(inv)
    return plan_collections(facturas, perfiles, s.caja, [s.nominas], policy, seed=seed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semilla", type=int, required=True)
    ap.add_argument("--semanas", type=int, default=1000)
    args = ap.parse_args()
    base = ReceivablesPolicy()
    rng = np.random.default_rng(args.semilla)
    clientes, modelo = poblacion(rng)
    filas = {v: [] for v in VARIANTES} | {"fijo": []}
    for i in range(args.semanas):
        s = semana(rng, clientes, i)
        filas["fijo"].append(resultado(s, calendario_fijo(s, base), base))
        for v, cambios in VARIANTES.items():
            plan = plan_copilot(s, modelo, replace(base, **cambios), i)
            r = resultado(s, {d.invoice_id: d.action for d in plan.decisions}, base)
            r.update(seguro=plan.safe, n_desc=sum(d.action == DISCOUNT for d in plan.decisions),
                     p_plan=plan.p_short, p_esperar=plan.p_short_if_wait)
            filas[v].append(r)
    out = {}
    for v, f in filas.items():
        coste = np.array([r["coste"] for r in f])
        out[v] = {"corto_pct": 100 * np.mean([r["corto"] for r in f]), "coste": float(coste.mean()),
                  "descuentos": float(np.mean([r["descuentos"] for r in f])),
                  "recordatorios": float(np.mean([r["recordatorios"] for r in f]))}
        if v != "fijo":
            seg = [r for r in f if r["seguro"]]
            ins = [r for r in f if not r["seguro"]]
            out[v] |= {"semanas_seguras": len(seg),
                       "descuento_en_seguras": float(sum(r["descuentos"] for r in seg)) / len(f),
                       "descuento_en_inseguras": float(sum(r["descuentos"] for r in ins)) / len(f),
                       "riesgo_previsto_medio": float(np.mean([r["p_plan"] for r in f])) * 100}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    (RESULTADOS / f"diagnostico_descuentos_{args.semilla}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

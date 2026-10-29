"""Diagnóstico de la H9 con las semillas YA USADAS (2030 y 2031): ¿por qué prevé menos riesgo del que corre?

Copilot (el que aprende) prevé quedarse corto en ~19 % de las semanas y se queda corto en ~24 %. Aquí se mira,
por grupos de semanas, el riesgo previsto frente al real, y, por factura, la probabilidad de cobrar antes de las
nóminas que creía el agente frente a lo que pasó: con disputa o sin ella, vencida o no, y según la acción.
No cuenta como prueba: sirve para elegir el cambio. Las hipótesis se fijan después y se miden con semillas nuevas.

Uso:  python diagnostico_riesgo.py [--semillas 2030 2031] [--semanas 1000]
"""
from __future__ import annotations

import argparse
from dataclasses import replace

import numpy as np

from simulacion import (APRENDER_CADA, P_DISPUTA_PAGA, P_VENCIDA, _p_con_accion, copilot_plan, poblacion,
                        resultado, semana)
from triage_core.collections_model import CollectionsModel
from triage_core.collections_calibration import Outcome, fit
from triage_core.collections_decision import WAIT, ReceivablesPolicy, _receipt
from triage_core.policy import SIGNAL_LIKELIHOOD

AGENTE = "Receivables Copilot"


def p_antes_de_nominas(rec, prof, dia: int, rng=np.random.default_rng(7)) -> float:
    """Lo que el agente cree: probabilidad de que esa factura llegue antes del día de las nóminas (como `simulate`)."""
    return float(np.mean(rec.due_day + CollectionsModel.sample_arrival_offsets(prof, 4000, rng) <= dia))


def diagnostico(semilla: int, n: int, policy: ReceivablesPolicy = ReceivablesPolicy()) -> None:
    rng = np.random.default_rng(semilla)
    clientes, modelo = poblacion(rng)
    calib, vistos = fit([], policy), []
    semanas, facturas = [], []
    for i in range(n):
        s = semana(rng, clientes, i)
        plan, creia = copilot_plan(s, modelo, policy, True, i, calib)
        acciones = {d.invoice_id: d.action for d in plan.decisions}
        r = resultado(s, acciones, policy)
        semanas.append((plan.p_short, r["corto"], any(a.disputa for a in s.abiertas)))
        pol = calib.policy(policy)
        for a, u in zip(s.abiertas, s.sorteo):
            inv = a.factura if not a.disputa else replace(a.factura, disputed=True)
            # el perfil que usó el plan: el del cliente con su respuesta y el autocontrol
            base = modelo.profile(inv.customer)
            if a.respuesta:
                base = modelo.apply_signal(base, SIGNAL_LIKELIHOOD[a.respuesta], a.respuesta)
            prof = calib.profile(base, a.respuesta)
            acc = acciones.get(inv.id, WAIT)
            partes, prof_acc, _ = _receipt(inv, prof, acc, pol)
            rec = partes[0][0]  # la primera parte (un plan de pagos tiene dos)
            creido = p_antes_de_nominas(rec, prof_acc, s.nominas.day)
            # lo que pasó de verdad, con el mismo número aleatorio (como en `resultado`)
            p = P_DISPUTA_PAGA if a.disputa else _p_con_accion(a.p_real, acc)
            if inv.due_day < 0 and not a.disputa:
                p *= P_VENCIDA
            vence = max(inv.due_day, 0)
            if acc == "DISCOUNT":
                vence = min(vence, policy.discount_window_days)
            llega = vence if u < p else vence + a.retraso
            facturas.append((creido, llega <= s.nominas.day, a.disputa, inv.due_day < 0, acc))
        paso = r["a_tiempo"]
        vistos += [Outcome(creia[a.factura.id], a.factura.due_day < 0, acciones.get(a.factura.id, WAIT),
                           paso[a.factura.id], a.respuesta) for a in s.abiertas if a.factura.id in paso]
        if (i + 1) % APRENDER_CADA == 0:
            calib = fit(vistos, policy)

    sem = np.array(semanas, dtype=float)
    print(f"\nSemilla {semilla}: riesgo previsto {sem[:, 0].mean():.1%} y real {sem[:, 1].mean():.1%}")
    for nombre, en in (("semanas con alguna disputa", sem[:, 2] == 1), ("semanas sin disputa", sem[:, 2] == 0)):
        print(f"  {nombre:<28} {en.mean():5.1%} de las semanas: previsto {sem[en, 0].mean():.1%}, real {sem[en, 1].mean():.1%}")
    f = np.array([(c, l, d, v) for c, l, d, v, _ in facturas], dtype=float)
    acc = np.array([x[4] for x in facturas])
    print("  Por factura, llega antes de las nóminas (creído / real):")
    grupos = [("en disputa", f[:, 2] == 1), ("sin disputa, vencida", (f[:, 2] == 0) & (f[:, 3] == 1)),
              ("sin disputa, sin vencer", (f[:, 2] == 0) & (f[:, 3] == 0))]
    grupos += [(f"sin disputa, acción {a}", (f[:, 2] == 0) & (acc == a)) for a in ("WAIT", "REMIND", "DISCOUNT")]
    for nombre, en in grupos:
        if en.sum():
            print(f"    {nombre:<28} n={int(en.sum()):5d}  {f[en, 0].mean():.1%} / {f[en, 1].mean():.1%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semillas", type=int, nargs="+", default=[2030, 2031])
    ap.add_argument("--semanas", type=int, default=1000)
    args = ap.parse_args()
    for s in args.semillas:
        diagnostico(s, args.semanas)


if __name__ == "__main__":
    main()

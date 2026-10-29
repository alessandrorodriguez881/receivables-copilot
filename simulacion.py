"""Simulación de 1.000 semanas: ¿cobra mejor Receivables Copilot que los recordatorios de calendario fijo de PayPal?

Cada semana sintética: un estudio con algo de caja, unas nóminas dentro de 7 días y 3-5 facturas abiertas de
30 clientes. Cada cliente tiene una probabilidad VERDADERA de pagar a tiempo que nadie ve; el motor solo ve su
historial. Algunos clientes responden: disputan la factura (8 %), confirman el pago o piden más tiempo, y lo
que dicen se parece a lo que de verdad harán.

Efectos VERDADEROS de las acciones, iguales para todos los agentes y algo más flojos que lo que supone la política
(para no jugar en casa): un recordatorio multiplica las probabilidades de pagar a tiempo por 1,4 (la política
supone 1,5) y un descuento del 2 % por 2,5 (la política supone 3). Una factura en disputa casi nunca se paga
dentro de la semana (5 %), haga lo que haga el agente.

Agentes (todos con las mismas semanas):
1. Receivables Copilot: el motor, con las respuestas de los clientes (comprobadas)
2. Copilot sin leer respuestas: el mismo motor, sin las respuestas (lo que aporta la capa de IA)
3. Recordatorios fijos de PayPal: recuerda todas las facturas a 3 días del vencimiento o ya vencidas, a todos igual
4. Descuento a todos: un 2 % por pronto pago en todas las facturas
5. No hacer nada

Hipótesis fijadas ANTES de ejecutar (27-oct-2026). Si alguna no se cumple, se cuenta tal cual:
H1. Copilot se queda corto el día de las nóminas en menos semanas que los recordatorios fijos de PayPal
H2. Copilot manda menos recordatorios que el calendario fijo (molesta menos a los clientes)
H3. Copilot cuesta menos que «descuento a todos» (descuentos + recordatorios + 1.500 $ cada vez que falta dinero)
H4. Copilot nunca ofrece descuento ni manda recordatorio a un cliente que disputa la factura; sin leer las
    respuestas, sí lo haría en alguna semana

Primera tanda (semillas 2030 y 2031): H2, H3 y H4 se cumplen; H1 no, y Copilot costaba más que el calendario fijo.

Segunda tanda, fijada ANTES de medir (27-oct-2026, noche), con semillas nuevas (2032 y 2033): cuando ningún plan
deja el riesgo por debajo del límite, el motor elige el de MENOR COSTE ESPERADO (descuentos + recordatorios +
1.500 $ × probabilidad de quedarse corto) en vez del más seguro a cualquier precio. La regla antigua sigue como
agente de comparación («Copilot, old rule»).
H5. Con el arreglo, Copilot cuesta menos por semana que los recordatorios fijos de PayPal (IC 95 % por debajo de 0)
H6. Con el arreglo, Copilot no se queda corto más de 1 punto por encima de los recordatorios fijos (IC por debajo de +1)
H7. El arreglo mantiene H2 y H4: menos recordatorios que el calendario fijo y nunca presiona a quien disputa
H8. La historia de la demo no cambia (lo comprueban las pruebas de `tests/test_escenario.py`)

Tercera tanda (28-oct-2026). Dos cambios, contados tal cual:
1. FALLO ARREGLADO EN ESTA SIMULACIÓN: las respuestas de los clientes se sorteaban aparte de lo que luego hacían,
   así que no avisaban de nada (contra lo que decía este texto). Ahora la respuesta depende de lo que el cliente
   haría sin que nadie le empuje (el mismo número aleatorio que decide si paga a tiempo). Las tandas 1 y 2 tenían
   el fallo: «leer las respuestas no ayuda» salía en parte de ahí
2. EL AGENTE APRENDE DE SUS RESULTADOS (`triage_core/collections_calibration.py`): compara lo que predijo con lo
   que pasó en las semanas anteriores y corrige su previsión, lo que resta estar vencida y lo que suman un
   recordatorio y un descuento, y cuánto fiarse de cada tipo de respuesta. Empieza con lo que supone la política
   y se ajusta cada 20 semanas.
   «Copilot, no learning» es el motor de la tanda 2, para comparar. La regla antigua ya no se repite
Hipótesis de la tercera tanda: en `HIPOTESIS_TANDA3` (más abajo), escritas antes de ejecutar las semillas nuevas.

Cuarta tanda (28-oct-2026, noche). `diagnostico_riesgo.py` (semillas ya usadas) encontró por qué la H9 fallaba:
el autocontrol dejaba fuera las facturas en disputa, y el agente creía que llegaban antes de las nóminas en el
54-67 % de los casos frente al 30-40 % de verdad. En las semanas con disputa preveía 8-12 puntos menos de riesgo.
Ahora el autocontrol aprende también de ellas (cuánto bajan de verdad las probabilidades). «Copilot, disputes
ignored» es el Copilot de la tanda 3, para comparar. Sale «Copilot, cost only»: la H13 ya dio su respuesta (no).
Hipótesis en `HIPOTESIS_TANDA4`, escritas antes de ejecutar las semillas nuevas 2036 y 2037.
Resultado: las disputas se prevén bien, pero el riesgo de la semana seguía desviado (2,0 y 7,4 puntos) y las
decisiones no cambiaron.

Quinta tanda (28-oct-2026, noche). Acertar más o menos con cada factura no basta: los errores pequeños de muchas
facturas se suman en la cola. Ahora el agente revisa también su riesgo SEMANAL (`collections_calibration.fit_risk`):
compara la probabilidad de quedarse corto que preveía para el plan elegido con si se quedó corto, y corrige con eso
el riesgo de todos los planes que compara (cada 20 semanas, solo con semanas pasadas). «Copilot, no risk check» es
el Copilot de la tanda 4, para comparar; sale «Copilot, disputes ignored» (sus decisiones eran iguales).
Hipótesis en `HIPOTESIS_TANDA5`, escritas antes de ejecutar las semillas nuevas 2038 y 2039.

Sexta tanda (28-oct-2026, noche). El historial de cada cliente se quedaba fijo las 1.000 semanas: el autocontrol
corregía errores de todos a la vez, pero no los de cada cliente. Ahora cada factura que el cliente paga sin que el
agente haga nada (ni recordatorio ni descuento), sin disputa y sin estar ya vencida, entra en su historial
RETRASO_HISTORIAL semanas después (cuando ya han llegado hasta las tardías). Así el historial mide cómo paga el
cliente por sí mismo. Es lo que más mejoró la previsión de Airwallex. «Copilot, history fixed» es el Copilot de la
tanda 5, para comparar; sale «Copilot, no risk check». Hipótesis en `HIPOTESIS_TANDA6`, escritas antes de ejecutar
las semillas nuevas 2040 y 2041.

Uso:  python simulacion.py [--semanas 1000] [--semilla 2032]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import date, timedelta
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

# el motor común: junto a la app (repositorio publicado) o dos carpetas más arriba (carpeta de trabajo)
sys.path.insert(0, str(next(p / "motor_comun" for p in Path(__file__).resolve().parents
                            if (p / "motor_comun" / "triage_core").exists())))

from triage_core.collections_calibration import Calibration, Outcome, RiskCalibration, fit, fit_risk
from triage_core.collections_decision import (DISCOUNT, REMIND, WAIT, CashNeed, Invoice, ReceivablesPolicy,
                                              plan_collections)
from triage_core.collections_model import CollectionsModel, PaidInvoice
from triage_core.policy import SIGNAL_LIKELIHOOD

LIFT_RECORDATORIO, LIFT_DESCUENTO, P_DISPUTA_PAGA = 1.4, 2.5, 0.05
P_VENCIDA = 0.6          # ya vencida: le cuesta más pagar ahora (la política supone algo parecido, odds x0,5)
APRENDER_CADA = 20       # semanas entre reajustes de lo aprendido
RETRASO_HISTORIAL = 5    # semanas hasta que una factura pagada entra en el historial (ya han llegado las tardías)
INICIO = date(2026, 1, 1)  # fecha de la semana 0 (solo para fechar las facturas que entran en el historial)
AGENTES = ("Receivables Copilot", "Copilot without replies", "PayPal fixed reminders", "Discount everyone",
           "Do nothing", "Copilot, no learning", "Copilot, history fixed")
# Agentes que aprenden: ¿leen las respuestas?, qué cambia en su política, ¿aprenden también de las disputas?,
# ¿revisan su riesgo semanal? y ¿crece el historial de cada cliente?
APRENDEN = {"Receivables Copilot": (True, {}, True, True, True), "Copilot without replies": (False, {}, True, True, True),
            "Copilot, history fixed": (True, {}, True, True, False)}
RESULTADOS = Path(__file__).with_name("resultados")

# Fijadas el 28-oct-2026 por la tarde, DESPUÉS de desarrollar con las semillas ya usadas (2030 y 2031) y ANTES de
# ejecutar las semillas nuevas 2034 y 2035. Si alguna no se cumple, se cuenta tal cual
HIPOTESIS_TANDA3 = {
    "H9": "Con aprendizaje, el riesgo medio que prevé Copilot queda a menos de 2 puntos del real; sin aprender, a más de 5",
    "H10": "Copilot no se queda corto más que los recordatorios fijos (IC 95 % de la diferencia por debajo de +1 punto)",
    "H11": "Leer las respuestas ya ayuda: Copilot cuesta menos que el mismo motor sin leerlas (IC por debajo de 0)",
    "H12": "Copilot cuesta menos que los recordatorios fijos (IC por debajo de 0)",
    "H13": "«Solo coste» (sin el tope del 5 %) cuesta menos que los recordatorios fijos (IC por debajo de 0)",
    "H14": "Se mantienen H2 y H4: menos recordatorios que el calendario fijo y nunca presiona a quien disputa",
    "H15": "La historia de la demo no cambia (lo comprueban las pruebas de tests/test_escenario.py)",
}

# Fijadas el 28-oct-2026 por la noche, DESPUÉS del diagnóstico con las semillas ya usadas (2030, 2031, 2034 y 2035)
# y ANTES de ejecutar las semillas nuevas 2036 y 2037. Cada una tiene que cumplirse en las dos
HIPOTESIS_TANDA4 = {
    "H16": "Aprendiendo también de las disputas, el riesgo medio que prevé Copilot queda a menos de 2 puntos del real",
    "H17": "Ese hueco es menor que el del Copilot que deja fuera las disputas (el de la tanda 3)",
    "H18": "Copilot no se queda corto más que los recordatorios fijos (IC 95 % de la diferencia por debajo de +1 punto)",
    "H19": "Copilot cuesta menos que los recordatorios fijos (IC por debajo de 0)",
    "H20": "Se mantienen H2 y H4: menos recordatorios que el calendario fijo y nunca presiona a quien disputa",
}

# Fijadas el 28-oct-2026 por la noche, DESPUÉS de ver la cuarta tanda (semillas 2036 y 2037, ya usadas) y ANTES de
# ejecutar las semillas nuevas 2038 y 2039. Cada una tiene que cumplirse en las dos. El criterio de «cuadra» deja
# de ser «a menos de 2 puntos»: con 1.000 semanas, lo que de verdad pasa ya tiene un margen de ±2,6 puntos
HIPOTESIS_TANDA5 = {
    "H21": "El riesgo que prevé Copilot cuadra con el real: el IC 95 % de la diferencia media semana a semana "
           "(previsto - se quedó corto) incluye el 0",
    "H22": "Esa diferencia es menor, en valor absoluto, que la del Copilot sin revisión semanal (el de la tanda 4)",
    "H23": "Copilot no se queda corto más que los recordatorios fijos (IC 95 % de la diferencia por debajo de +1 punto)",
    "H24": "Copilot cuesta menos por semana que el Copilot sin revisión semanal (IC por debajo de 0)",
    "H25": "Se mantienen H2 y H4: menos recordatorios que el calendario fijo y nunca presiona a quien disputa",
}

# Fijadas el 28-oct-2026 por la noche, DESPUÉS de una comprobación con una semilla ya usada (2038) y ANTES de
# ejecutar las semillas nuevas 2040 y 2041. Cada una tiene que cumplirse en las dos
HIPOTESIS_TANDA6 = {
    "H26": "Conoce mejor a cada cliente: el error de su previsión base frente a la probabilidad verdadera es menor que "
           "con el historial fijo (diferencia emparejada por factura, IC 95 % por debajo de 0)",
    "H27": "Cuesta menos por semana que el Copilot con el historial fijo (IC por debajo de 0)",
    "H28": "Cuesta menos por semana que los recordatorios fijos (IC por debajo de 0)",
    "H29": "El riesgo que prevé cuadra con el real (el IC 95 % de previsto - se quedó corto incluye el 0)",
    "H30": "Se mantienen H2 y H4: menos recordatorios que el calendario fijo y nunca presiona a quien disputa",
}


@dataclass(frozen=True)
class Cliente:
    nombre: str
    p_real: float
    retraso_medio: float


@dataclass
class Abierta:
    factura: Invoice
    p_real: float
    retraso: int            # días de retraso si llega tarde (de verdad)
    disputa: bool
    respuesta: str | None   # disputes_invoice / confirms_payment / asks_for_more_time / None


@dataclass
class Semana:
    caja: float
    nominas: CashNeed
    abiertas: list[Abierta]
    sorteo: np.ndarray      # números aleatorios fijos de la semana: todos los agentes juegan con la misma suerte


def poblacion(rng: np.random.Generator, n: int = 30) -> tuple[list[Cliente], CollectionsModel]:
    clientes = [Cliente(f"C{i:02d}", float(rng.beta(6, 2)), float(rng.uniform(3, 12))) for i in range(n)]
    historia, d0 = [], date(2025, 1, 1)
    for c in clientes:
        for k in range(int(rng.integers(3, 25))):
            vence = d0 + timedelta(days=10 * k)
            tarde = 0 if rng.random() < c.p_real else 1 + int(rng.poisson(c.retraso_medio))
            historia.append(PaidInvoice(c.nombre, vence, vence + timedelta(days=tarde), 1000))
    return clientes, CollectionsModel(historia)


def semana(rng: np.random.Generator, clientes: list[Cliente], i: int) -> Semana:
    abiertas, sorteo = [], []
    for j in rng.choice(len(clientes), size=int(rng.integers(3, 6)), replace=False):
        c = clientes[int(j)]
        inv = Invoice(f"{i}-{j}", c.nombre, round(float(rng.uniform(800, 9_000)), 2), int(rng.integers(-15, 7)))
        disputa = bool(rng.random() < 0.08)
        u = float(rng.random())  # decide si paga a tiempo (en `resultado`); las acciones mueven el umbral
        a_tiempo = u < c.p_real * (P_VENCIDA if inv.due_day < 0 else 1.0)  # lo que haría sin empujarle
        sorteo.append(u)
        if disputa:
            resp = "disputes_invoice"
        elif rng.random() < (0.30 if a_tiempo else 0.05):
            resp = "confirms_payment"
        elif rng.random() < (0.10 if a_tiempo else 0.40):
            resp = "asks_for_more_time"
        else:
            resp = None
        abiertas.append(Abierta(inv, c.p_real, 1 + int(rng.poisson(c.retraso_medio)), disputa, resp))
    total = sum(a.factura.amount for a in abiertas)
    caja = round(float(rng.uniform(0.1, 0.4)) * total, 2)
    nominas = CashNeed("payroll", round(caja + float(rng.uniform(0.3, 0.7)) * total, 2), 7)
    return Semana(caja, nominas, abiertas, np.array(sorteo))


def _p_con_accion(p: float, accion: str) -> float:
    odds = p / (1 - p) * {REMIND: LIFT_RECORDATORIO, DISCOUNT: LIFT_DESCUENTO}.get(accion, 1.0)
    return odds / (1 + odds)


def resultado(s: Semana, acciones: dict[str, str], policy: ReceivablesPolicy) -> dict:
    """Lo que pasa DE VERDAD: quién paga antes de las nóminas, con los mismos números aleatorios para todos."""
    caja, descuentos, recordatorios, a_disputa, a_prometida, a_tiempo = s.caja, 0.0, 0, 0, 0, {}
    for a, u in zip(s.abiertas, s.sorteo):
        acc = acciones.get(a.factura.id, WAIT)
        recordatorios += acc == REMIND
        a_disputa += a.disputa and acc in (REMIND, DISCOUNT)
        a_prometida += a.respuesta == "confirms_payment" and acc in (REMIND, DISCOUNT)
        p = P_DISPUTA_PAGA if a.disputa else _p_con_accion(a.p_real, acc)
        if a.factura.due_day < 0 and not a.disputa:
            p *= P_VENCIDA
        a_tiempo[a.factura.id] = bool(u < p)  # lo que el agente puede ver después: pagó a tiempo o no (también
        # en disputa: desde la cuarta tanda el autocontrol aprende de ellas)
        vence = max(a.factura.due_day, 0)
        if acc == DISCOUNT:
            vence = min(vence, policy.discount_window_days)
        llega = vence if u < p else vence + a.retraso
        if llega <= s.nominas.day:
            cobro = a.factura.amount
            if acc == DISCOUNT and llega <= policy.discount_window_days:
                descuentos += policy.discount_pct * cobro
                cobro *= 1 - policy.discount_pct
            caja += cobro
    corto = caja < s.nominas.amount
    coste = descuentos + policy.reminder_cost * recordatorios + (policy.shortfall_penalty if corto else 0.0)
    return {"corto": bool(corto), "coste": round(coste, 2), "descuentos": round(descuentos, 2),
            "recordatorios": int(recordatorios), "a_disputa": int(a_disputa), "a_prometida": int(a_prometida),
            "a_tiempo": a_tiempo}


def copilot_plan(s: Semana, modelo: CollectionsModel, policy: ReceivablesPolicy, leer: bool, seed: int,
                 calibracion: Calibration | None = None, riesgo: RiskCalibration | None = None):
    """El plan del motor y, por factura, la probabilidad que creía (antes de corregirla), para aprender después."""
    perfiles, crudos, facturas, creia = {}, {}, [], {}
    for a in s.abiertas:
        p = crudos.get(a.factura.customer, modelo.profile(a.factura.customer))
        inv = a.factura
        if leer and a.respuesta:
            if a.respuesta == "disputes_invoice":
                inv = replace(inv, disputed=True)
            elif a.respuesta == "confirms_payment":
                inv = replace(inv, promised=True)
            p = CollectionsModel.apply_signal(p, SIGNAL_LIKELIHOOD[a.respuesta], a.respuesta)
        crudos[a.factura.customer] = p
        respuesta = a.respuesta if leer else None
        perfiles[a.factura.customer] = calibracion.profile(p, respuesta) if calibracion else p
        creia[inv.id] = p.p_on_time
        facturas.append(inv)
    pol = calibracion.policy(policy) if calibracion else policy
    return plan_collections(facturas, perfiles, s.caja, [s.nominas], pol, seed=seed, risk_check=riesgo), creia


def copilot(s: Semana, modelo: CollectionsModel, policy: ReceivablesPolicy, leer: bool, seed: int,
            calibracion: Calibration | None = None) -> dict[str, str]:
    plan, _ = copilot_plan(s, modelo, policy, leer, seed, calibracion)
    return {d.invoice_id: d.action for d in plan.decisions}


def calendario_fijo(s: Semana, policy: ReceivablesPolicy) -> dict[str, str]:
    return {a.factura.id: REMIND for a in s.abiertas if a.factura.due_day <= policy.remind_from_days_before_due}


def simular(n: int, semilla: int, policy: ReceivablesPolicy = ReceivablesPolicy()) -> dict:
    rng = np.random.default_rng(semilla)
    clientes, modelo = poblacion(rng)
    p_real = {c.nombre: c.p_real for c in clientes}
    modelos = {a: modelo for a in APRENDEN}                # cada agente, con su historial
    pendientes = {a: [] for a in APRENDEN}                 # (semana en que entra, factura pagada)
    filas = {a: [] for a in AGENTES}
    vistos = {a: [] for a in APRENDEN}                     # lo que cada agente que aprende ha visto pasar
    calib = {a: fit([], policy) for a in APRENDEN}
    semanas_vistas = {a: [] for a in APRENDEN}             # (riesgo que preveía el modelo, se quedó corto)
    revision = {a: fit_risk([]) for a in APRENDEN}
    for i in range(n):
        s = semana(rng, clientes, i)
        for a in APRENDEN:  # entra en el historial lo que ya se sabe
            llegan = [f for w, f in pendientes[a] if w <= i]
            if llegan:
                modelos[a] = CollectionsModel(modelos[a].history + llegan)
                pendientes[a] = [(w, f) for w, f in pendientes[a] if w > i]
        planes = {a: copilot_plan(s, modelos[a], replace(policy, **cambios), leer, i, calib[a],
                                  revision[a] if revisa else None)
                  for a, (leer, cambios, _, revisa, _) in APRENDEN.items()}
        planes["Copilot, no learning"] = copilot_plan(s, modelo, policy, True, i)
        decisiones = {a: {d.invoice_id: d.action for d in plan.decisions} for a, (plan, _) in planes.items()}
        decisiones |= {"PayPal fixed reminders": calendario_fijo(s, policy),
                       "Discount everyone": {a.factura.id: DISCOUNT for a in s.abiertas},
                       "Do nothing": {}}
        for agente in AGENTES:
            r = resultado(s, decisiones[agente], policy)
            if agente in planes:
                r["riesgo_previsto"] = planes[agente][0].p_short
            filas[agente].append(r)
        for agente in APRENDEN:
            creia, acciones, paso = planes[agente][1], decisiones[agente], filas[agente][-1]["a_tiempo"]
            leer, _, con_disputas, revisa, crece = APRENDEN[agente]
            vistos[agente] += [Outcome(creia[a.factura.id], a.factura.due_day < 0, acciones.get(a.factura.id, WAIT),
                                       paso[a.factura.id], a.respuesta if leer else None)
                               for a in s.abiertas if con_disputas or not a.disputa]
            semanas_vistas[agente].append((planes[agente][0].p_short_model, filas[agente][-1]["corto"]))
            # ¿conoce a cada cliente? su previsión base (con el autocontrol, sin respuestas) frente a la verdad
            filas[agente][-1]["error_cliente"] = [
                (calib[agente].profile(modelos[agente].profile(a.factura.customer)).p_on_time
                 - p_real[a.factura.customer]) ** 2 for a in s.abiertas]
            if crece:  # lo que el cliente paga por sí mismo entra en su historial más tarde
                for a in s.abiertas:
                    if acciones.get(a.factura.id, WAIT) == WAIT and not a.disputa and a.factura.due_day >= 0:
                        vence = INICIO + timedelta(days=7 * i + a.factura.due_day)
                        tarde = 0 if paso[a.factura.id] else a.retraso
                        pendientes[agente].append((i + RETRASO_HISTORIAL, PaidInvoice(
                            a.factura.customer, vence, vence + timedelta(days=tarde), a.factura.amount)))
            if (i + 1) % APRENDER_CADA == 0:
                calib[agente] = fit(vistos[agente], policy)
                if revisa:
                    revision[agente] = fit_risk(semanas_vistas[agente])
    for agente, (_, _, _, revisa, _) in APRENDEN.items():
        filas[agente][-1]["aprendido"] = calib[agente].describe() + (f"; {revision[agente].describe()}" if revisa else "")
    return filas


def _ic_media(x: np.ndarray) -> list[float]:
    m, e = float(x.mean()), float(x.std(ddof=1) / math.sqrt(len(x)))
    return [m, m - 1.96 * e, m + 1.96 * e]


def resumir(filas: dict) -> dict:
    n = len(filas[AGENTES[0]])
    out = {"semanas": n, "agentes": {}}
    for a in AGENTES:
        f = filas[a]
        out["agentes"][a] = {
            "corto_pct": 100 * sum(r["corto"] for r in f) / n,
            "coste_medio": float(np.mean([r["coste"] for r in f])),
            "descuentos_medios": float(np.mean([r["descuentos"] for r in f])),
            "recordatorios_por_semana": float(np.mean([r["recordatorios"] for r in f])),
            "semanas_presionando_disputa": sum(r["a_disputa"] > 0 for r in f),
            "semanas_presionando_promesa": sum(r["a_prometida"] > 0 for r in f),
        }
        if "riesgo_previsto" in f[0]:  # lo que el motor creía, para ver si acierta
            out["agentes"][a]["riesgo_previsto_pct"] = 100 * float(np.mean([r["riesgo_previsto"] for r in f]))
        if "aprendido" in f[-1]:
            out["agentes"][a]["aprendido"] = f[-1]["aprendido"]
        if "error_cliente" in f[0]:  # raíz del error cuadrático medio, en puntos
            out["agentes"][a]["error_cliente_puntos"] = 100 * math.sqrt(float(np.mean(
                [e for r in f for e in r["error_cliente"]])))
    dif = lambda a, b, k: _ic_media(np.array([float(x[k]) - float(y[k]) for x, y in zip(filas[a], filas[b])]))
    d = {"H1 corto: Copilot - PayPal fijo (puntos)": [100 * v for v in dif(AGENTES[0], AGENTES[2], "corto")],
         "H2 recordatorios: Copilot - PayPal fijo": dif(AGENTES[0], AGENTES[2], "recordatorios"),
         "H3 coste: Copilot - descuento a todos (USD)": dif(AGENTES[0], AGENTES[3], "coste"),
         "H5 coste: Copilot - PayPal fijo (USD)": dif(AGENTES[0], AGENTES[2], "coste"),
         "coste: Copilot - sin aprender (USD)": dif(AGENTES[0], AGENTES[5], "coste"),
         "corto: Copilot - sin aprender (puntos)": [100 * v for v in dif(AGENTES[0], AGENTES[5], "corto")],
         "coste: Copilot - sin leer respuestas (USD)": dif(AGENTES[0], AGENTES[1], "coste"),
         "corto: Copilot - sin leer respuestas (puntos)": [100 * v for v in dif(AGENTES[0], AGENTES[1], "corto")],
         "coste: Copilot - historial fijo (USD)": dif(AGENTES[0], AGENTES[6], "coste"),
         "corto: Copilot - historial fijo (puntos)": [100 * v for v in dif(AGENTES[0], AGENTES[6], "corto")],
         "error cuadrático por factura: Copilot - historial fijo (x1000)": [1000 * v for v in _ic_media(np.array(
             [x - y for r0, r6 in zip(filas[AGENTES[0]], filas[AGENTES[6]])
              for x, y in zip(r0["error_cliente"], r6["error_cliente"])]))]}
    for a in (AGENTES[0], AGENTES[6]):  # ¿cuadra lo que prevé? semana a semana, previsto - se quedó corto
        d[f"riesgo previsto - real: {a} (puntos)"] = [100 * v for v in _ic_media(
            np.array([r["riesgo_previsto"] - float(r["corto"]) for r in filas[a]]))]
    out["diferencias"] = d
    ag = out["agentes"]
    out["hipotesis"] = {
        "H1": d["H1 corto: Copilot - PayPal fijo (puntos)"][2] < 0,
        "H2": d["H2 recordatorios: Copilot - PayPal fijo"][2] < 0,
        "H3": d["H3 coste: Copilot - descuento a todos (USD)"][2] < 0,
        "H4": ag[AGENTES[0]]["semanas_presionando_disputa"] == 0 and ag[AGENTES[1]]["semanas_presionando_disputa"] > 0,
        "H5": d["H5 coste: Copilot - PayPal fijo (USD)"][2] < 0,
        "H6": d["H1 corto: Copilot - PayPal fijo (puntos)"][2] < 1,
    }
    out["hipotesis"]["H7"] = out["hipotesis"]["H2"] and out["hipotesis"]["H4"]
    hueco = lambda a: abs(ag[a]["riesgo_previsto_pct"] - ag[a]["corto_pct"])
    out["hipotesis"] |= {
        "H9": hueco(AGENTES[0]) < 2 and hueco(AGENTES[5]) > 5,
        "H10": d["H1 corto: Copilot - PayPal fijo (puntos)"][2] < 1,
        "H11": d["coste: Copilot - sin leer respuestas (USD)"][2] < 0,
        "H12": d["H5 coste: Copilot - PayPal fijo (USD)"][2] < 0,
        "H14": out["hipotesis"]["H7"],
    }
    r0 = d[f"riesgo previsto - real: {AGENTES[0]} (puntos)"]
    out["hipotesis"] |= {
        "H26": d["error cuadrático por factura: Copilot - historial fijo (x1000)"][2] < 0,
        "H27": d["coste: Copilot - historial fijo (USD)"][2] < 0,
        "H28": d["H5 coste: Copilot - PayPal fijo (USD)"][2] < 0,
        "H29": r0[1] <= 0 <= r0[2],
        "H30": out["hipotesis"]["H7"],
    }
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--semanas", type=int, default=1000)
    p.add_argument("--semilla", type=int, default=2032)
    p.add_argument("--prefijo", default="simulacion", help="nombre del archivo de resultados (p. ej. desarrollo)")
    args = p.parse_args()
    t0 = time.time()
    res = resumir(simular(args.semanas, args.semilla))
    res.update(semilla=args.semilla, segundos=round(time.time() - t0, 1))
    RESULTADOS.mkdir(exist_ok=True)
    (RESULTADOS / f"{args.prefijo}_{args.semanas}_semilla{args.semilla}.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

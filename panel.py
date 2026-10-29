"""Pantalla de la demo de Receivables Copilot (Streamlit). En inglés: es lo que ve el jurado en el vídeo.

Cada botón de la barra lateral llama a los mismos pasos que la consola (`demo.py`) y actúa de verdad en el
sandbox de PayPal. Sin claves, corre contra el simulador (`modo.py`), y sin clave de Claude repite la última
lectura de Claude de verdad. Nunca enseña claves ni tokens.

Uso (desde la carpeta app/):  python -m streamlit run panel.py
"""
import contextlib
from datetime import date, datetime
import io
import os
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

import preparar_facturas
from demo import (APROBACIONES, CONCEPTO, ENV, POLICY, cambios, cobrado_en_paypal, cobro, ejecutar, situacion,
                  tarjeta_descuento,
                  tarjeta_plan)
from escenario import (BANDEJA, CAJA_INICIAL, DATA, DOMINIOS, ESTUDIO, FACTURAS, NECESIDADES, ORIGEN_HISTORIAL,
                       HISTORIAL_MODELO, POR_CLIENTE, SENALES_ENSAYO, facturas_de, guardar_notas, guardar_senales,
                       notas_de,
                       ronda_actual, senales_de)
from agente_ia import GRABACION
from agente_ia import resumen as plan_para_claude
from historial_paypal import numerar
from modo import SIMULADO, conectar
from rail_paypal import PayPalError, PayPalRail, read_env
from tabla_aggrid import tabla
from triage_core.approvals import ApprovalBook
from triage_core.cash_simulation import cash_bands
from triage_core.collections_decision import DISCOUNT, ESCALATE, PLAN, REMIND, WAIT
from triage_core.ledger import Ledger

st.set_page_config(page_title="Receivables Copilot", page_icon=":material/request_quote:", layout="wide")

ACCION = {  # etiqueta, color e icono de cada decisión
    WAIT: ("Wait", "gray", ":material/hourglass_empty:"),
    REMIND: ("Send a reminder", "blue", ":material/notifications:"),
    DISCOUNT: (f"Offer {POLICY.discount_pct:.0%} early-payment discount", "orange", ":material/sell:"),
    ESCALATE: ("A person decides", "red", ":material/front_hand:"),
    PLAN: (f"Offer a payment plan: {POLICY.plan_first_pct:.0%} now", "violet", ":material/calendar_month:"),
}
NEED = NECESIDADES[0]
TEAL, GRIS, ROJO = "#0F766E", "#A1A1AA", "#DC2626"  # los de .streamlit/config.toml


def comprobar_auditoria() -> str:
    """La orden que comprueba este mismo libro desde la consola (en el modo demo, cada visitante tiene su carpeta)."""
    carpeta = Path(os.path.relpath(DATA, Path(__file__).parent)).as_posix() if SIMULADO else ""
    return f"python verificar_auditoria.py {carpeta}".rstrip()


@st.cache_resource
def get_rail() -> PayPalRail:
    return conectar()


def md(texto: str) -> str:
    return texto.replace("$", "\\$")


def usd(v: float, dec: int = 0) -> str:
    return f"${v:,.{dec}f}"


def con_claude() -> bool:
    if os.environ.get("RC_NO_CLAUDE") == "1":  # para ensayar la demo pública (sin clave) en un equipo que sí la tiene
        return False
    return bool(read_env(ENV).get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))


VIGILANCIA = 8  # segundos entre dos miradas a PayPal en busca de cobros
for k, v in (("log", []), ("cambios", None), ("error", None), ("resumen_ia", ""), ("plan_ia", None), ("vistos", None),
             ("plan_visto", None)):
    st.session_state.setdefault(k, v)

rail = get_rail()
if SIMULADO and not (DATA / "sandbox_simulado.json").exists():  # primera visita: las 5 facturas de la demo
    with contextlib.redirect_stdout(io.StringIO()):
        preparar_facturas.main(lambda m: None, rail)
ronda = ronda_actual()
DATA.mkdir(exist_ok=True)
libro, book = Ledger(DATA / "ledger.json"), ApprovalBook.load(APROBACIONES)
senales = senales_de(ronda)


# ---------- pasos ----------
def reiniciar(log) -> None:
    preparar_facturas.main(log)
    st.session_state.cambios = None
    st.session_state.resumen_ia, st.session_state.plan_ia = "", None  # el resumen era de la ronda anterior


def leer(log) -> None:
    if not con_claude() and not GRABACION.exists():  # ensayo: las señales que Claude registraría, sin la API
        guardar_senales(ronda, SENALES_ENSAYO)
        for s in SENALES_ENSAYO:
            log(f"Recorded {s.evidence}")
        log("msg-203 ignored: not sent from one of your customers' domains")
        return
    import anthropic
    from agente_ia import GRABAR, Bandeja, cliente, guardar_grabacion, leer_bandeja, repetir_grabacion, resumen
    bandeja = Bandeja(lambda ss: resumen(situacion(rail, ronda, ss)))
    if con_claude():
        try:
            st.session_state.resumen_ia = leer_bandeja(cliente(ENV), bandeja)
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude could not read the replies ({type(e).__name__}). Nothing was sent") from e
        if GRABAR:
            guardar_grabacion(bandeja, st.session_state.resumen_ia, date.today())
    else:
        st.session_state.resumen_ia = repetir_grabacion(bandeja)
    st.session_state.plan_ia = bandeja.plan  # sobre este plan escribió Claude su resumen
    guardar_senales(ronda, bandeja.senales)
    guardar_notas(ronda, bandeja.notas)
    for paso in bandeja.registro:
        log(paso)


def actuar(log) -> None:
    ejecutar(rail, libro, book, situacion(rail, ronda, senales or []), ronda, senales or [], log,
             notas=notas_de(ronda))


def paga_fabrikam(log) -> None:
    """El cliente paga en PayPal. El agente no se entera por este botón: lo ve al mirar PayPal (`vigilar_cobros`)."""
    cobro(rail, libro, ronda, "INV-103", log)


def solo_el_vigilante() -> bool:
    """¿Está Streamlit repintando solo el vigilante (lo ha despertado su temporizador), no la página entera? En una
    pasada entera, la página se dibuja después ya con el cobro: volver a empezar perdería el clic que la provocó."""
    return bool(getattr(get_script_run_ctx(), "fragment_ids_this_run", None))


@st.fragment(run_every=VIGILANCIA)
def vigilar_cobros() -> None:
    """Mira PayPal cada pocos segundos. Si entra dinero en una factura (lo pague el cliente en PayPal o lo registre
    alguien allí), el agente lo ve solo y recalcula el plan, sin que nadie pulse nada."""
    vistos = st.session_state.vistos
    try:
        ahora = cobrado_en_paypal(rail, ronda)
        nuevos = [] if vistos is None else [i for i, v in ahora.items() if v > vistos.get(i, 0.0) + 0.005]
        if nuevos and st.session_state.plan_visto is not None:
            despues = situacion(rail, ronda, senales or []).plan
    except (PayPalError, requests.RequestException):  # sin red (o PayPal caído): la pantalla sigue, y se reintenta
        st.caption(":material/sensors_off: Could not reach PayPal; trying again in a few seconds")
        return
    if nuevos and st.session_state.plan_visto is not None:
        antes = st.session_state.plan_visto
        st.session_state.cambios = {"lineas": cambios(antes, despues), "antes": antes.p_short,
                                    "despues": despues.p_short,
                                    "detectado": [f"{i} ({CONCEPTO[i][0]})" for i in nuevos]}
        st.session_state.log = (["**Payment detected in PayPal**"]
                                + [f"{i}: {CONCEPTO[i][0]} paid {ahora[i] - vistos.get(i, 0.0):,.2f} USD; plan recomputed"
                                   for i in nuevos] + st.session_state.log)
        st.session_state.vistos = ahora
        if solo_el_vigilante():
            st.rerun()
    st.caption(f":material/sensors: Watching PayPal for payments every {VIGILANCIA} s · last check "
               f"{datetime.now():%H:%M:%S}")


def decidir(fp: str, si: bool) -> None:
    if fp in book.pending:  # con un doble clic, la tarjeta ya está decidida
        (book.approve if si else book.reject)(fp, "owner")


pulsado = None
lista = len(facturas_de(ronda)) == len(FACTURAS)  # la ronda tiene sus 5 facturas en PayPal (paso 1 terminado)
pagada = any(e.status == "COMPLETED" for e in libro.attempts(f"payment:{ronda}:INV-103"))
with st.sidebar:
    st.header("Run the demo")
    st.caption(f"{ESTUDIO} · round `{ronda}` · " + ("simulated PayPal sandbox, no keys" if SIMULADO
                                                    else "PayPal sandbox, no real money"))
    if st.button("1 · New round: send 5 invoices", icon=":material/restart_alt:", width="stretch"):
        pulsado = ("Creating and sending the invoices in PayPal", reiniciar)
    if st.button("2 · Read customer replies" + ("" if con_claude() else " (replay of a real Claude run)"
                                                if GRABACION.exists() else " (rehearsal)"), icon=":material/mail:",
                 width="stretch", disabled=senales is not None or not lista):
        pulsado = ("Reading customer replies", leer)
    if st.button("3 · Act on the plan", icon=":material/play_arrow:", type="primary", width="stretch",
                 disabled=not lista):
        pulsado = ("Acting on the plan in PayPal", actuar)
    if st.button("4 · Fabrikam pays", icon=":material/payments:", width="stretch", disabled=pagada or not lista):
        pulsado = ("Fabrikam pays its invoice", paga_fabrikam)
    st.caption("After approving the discount, press 3 again to apply it." if lista
               else "Press 1 first: this round does not have its 5 invoices in PayPal yet.")
    if lista:
        vigilar_cobros()
    with st.expander("Agent log", icon=":material/receipt_long:"):
        for linea in st.session_state.log[:40]:
            if linea.startswith("**"):
                st.markdown(linea)
            else:
                st.text(linea)

st.title("Receivables Copilot")
st.caption(f"{ESTUDIO} · a collections agent for PayPal invoices that decides who to chase, how, and when "
           "to ask you first")
if SIMULADO:
    st.info("No PayPal keys here, so a built-in simulator answers the same PayPal Invoicing API calls. With sandbox "
            "keys in `.env`, the same buttons create, remind and update real invoices in the PayPal sandbox. "
            "**Run the demo with steps 2 to 4 in the sidebar** (on a phone, open it with » at the top left).",
            icon=":material/science:")

# Huecos fijos para lo que aparece y desaparece (progreso, errores, avisos): así lo de abajo no cambia de sitio y
# Streamlit no vuelve a montar las tablas en cada paso (si no, no se verían parpadear las celdas que cambian)
arriba = st.container()
if pulsado:
    nombre, fn = pulsado
    st.session_state.error, mensajes = None, []
    with arriba, st.status(f":shimmer[{nombre}]", expanded=True) as progreso:
        def log(m: str) -> None:
            mensajes.append(m)
            st.text(m)
        try:
            fn(log)
            progreso.update(label=f"{nombre}: done", state="complete", expanded=False)
        except (PayPalError, RuntimeError) as e:
            st.session_state.error = f"{nombre}: {e}"
            progreso.update(label=f"{nombre}: stopped", state="error")
    st.session_state.log = [f"**{nombre}**"] + mensajes + st.session_state.log
    st.rerun()
if st.session_state.error:
    arriba.error(st.session_state.error, icon=":material/error:")

s = situacion(rail, ronda, senales or [])
decision = {d.invoice_id: d for d in s.plan.decisions}
st.session_state.vistos, st.session_state.plan_visto = dict(s.cobrado_por or {}), s.plan  # lo que ya sabe el agente

def tarjeta_de(iid: str, d):
    """La tarjeta que aprueba el dueño para esta decisión (descuento o plan por encima del límite), o None."""
    if d is not None and d.action in (DISCOUNT, PLAN) and d.needs_approval:
        return (tarjeta_descuento if d.action == DISCOUNT else tarjeta_plan)(ronda, iid, senales or [])
    return None


# ---------- cabecera: el día de las nóminas ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{NEED.what.capitalize()} in {NEED.day} days", usd(NEED.amount), border=True, height="stretch",
          help="The cash the studio needs on payday")
c2.metric("Cash available", usd(s.caja), border=True, height="stretch",
          help=f"{usd(CAJA_INICIAL)} in the bank plus {usd(s.cobrado)} collected through PayPal in this round")
c3.metric("Chance of being short on payday", f"{s.plan.p_short:.1%}",
          round((s.plan.p_short - s.plan.p_short_if_wait) * 100, 1), delta_color="inverse",
          delta_description="pts vs doing nothing", border=True, height="stretch",
          help=f"Simulated over 5,000 scenarios of when each customer pays. The policy allows {POLICY.max_short_prob:.0%}.")
esperan = [iid for iid, d in decision.items() if (req := tarjeta_de(iid, d)) and req.fingerprint in book.pending]
c4.metric("Waiting for your approval", len(esperan), border=True, height="stretch",
          help=f"Discounts above {usd(POLICY.autonomous_discount_limit)} need you")

avisos = st.container()
for n in s.plan.notes:
    avisos.warning(n, icon=":material/warning:")
if st.session_state.cambios:
    c = st.session_state.cambios
    lineas = "; ".join(f"**{i}** {ACCION[a][0].lower()} → {ACCION[b][0].lower()}" for i, a, b in c["lineas"]) or "nothing"
    origen = (f" in PayPal: {', '.join(c['detectado'])}. The agent spotted it on its own (it checks PayPal every "
              f"{VIGILANCIA} s) and re-planned" if c.get("detectado") else "")
    avisos.success(md(f"Payment received{origen}. Chance of being short {c['antes']:.1%} → {c['despues']:.1%}. "
                      f"The agent only reopened what the new cash changes: {lineas}."), icon=":material/savings:")

facturas, bandeja, actividad, reglas = st.tabs(["Invoices", "Inbox", "Activity in PayPal", "How it decides"])
PAGADA = ("PAID", "MARKED_AS_PAID")
COLUMNAS_TRABAJO = [
    {"field": "factura", "headerName": "Invoice", "pinned": "left", "flex": 0, "width": 95, "filter": False},
    {"field": "cliente", "headerName": "Customer", "flex": 0, "width": 125},
    {"field": "importe", "headerName": "Amount", "tipo": "dinero", "flex": 0, "width": 100, "filter": False},
    {"field": "vence", "headerName": "Due", "tipo": "dias", "flex": 0, "width": 155},
    {"field": "estado", "headerName": "In PayPal", "tipo": "estado", "flex": 0, "width": 140,
     "headerTooltip": "The invoice's status in PayPal, and what has been paid on it"},
    {"field": "accion", "headerName": "Agent's call", "tipo": "accion", "minWidth": 230, "flex": 2,
     "headerTooltip": "What the agent will do, and whether it needs your approval first"},
    {"field": "p_despues", "headerName": "On-time odds", "tipo": "probabilidad", "minWidth": 140, "filter": False,
     "headerTooltip": "Chance this invoice is paid on time: before → after the agent's action"},
]
COLUMNAS_HISTORIAL = [
    {"field": "numero", "headerName": "Invoice", "minWidth": 210},
    {"field": "cliente", "headerName": "Customer"},
    {"field": "importe", "headerName": "Amount", "tipo": "dinero"},
    {"field": "vence", "headerName": "Due", "sort": "desc"},
    {"field": "pagada", "headerName": "Paid"},
    {"field": "retraso", "headerName": "Days late", "tipo": "retraso"},
]


def aprobacion(iid: str, d, prefijo: str = "") -> None:
    req = tarjeta_de(iid, d)
    if req is None:
        return
    if req.fingerprint in book.pending:
        st.info(md(f"Gives away {usd(req.amount, 2)}: above the {usd(POLICY.autonomous_discount_limit)} "
                   "the agent may give on its own." if d.action == DISCOUNT else
                   f"Changes the invoice's terms: {usd(req.amount, 2)} now, the rest "
                   f"{POLICY.plan_rest_days} days later."), title="Needs your approval",
                icon=":material/approval:")
        b = st.container(horizontal=True)
        if prefijo:  # en el detalle (que se repinta solo): decidir y repintar toda la pantalla, que lo cierra
            for si, texto, extra in ((True, "Approve", {"type": "primary", "icon": ":material/check:"}),
                                     (False, "Reject", {"icon": ":material/close:"})):
                if b.button(texto, key=f"{prefijo}{'ok' if si else 'no'}-{iid}", **extra):
                    decidir(req.fingerprint, si)
                    st.rerun()
            return
        b.button("Approve", key=f"ok-{iid}", type="primary", icon=":material/check:",
                 on_click=decidir, args=(req.fingerprint, True))
        b.button("Reject", key=f"no-{iid}", icon=":material/close:",
                 on_click=decidir, args=(req.fingerprint, False))
    elif req.fingerprint in book.granted:
        st.caption(":material/verified: Approved by the owner")


def filas_trabajo() -> list[dict]:
    filas = []
    for iid, cliente, importe, vence, _ in FACTURAS:
        d, estado = decision.get(iid), s.estados.get(iid)
        etiqueta, color, _ = ACCION[d.action] if d else (("Paid: nothing to do" if estado in PAGADA else ""), "green", "")
        req = tarjeta_de(iid, d)
        filas.append({"id": iid, "factura": iid, "cliente": cliente, "importe": importe,
                      "cobrado": (s.cobrado_por or {}).get(iid, 0.0), "vence": vence, "estado": estado,
                      "accion": etiqueta, "color": color, "motivo": d.reason if d else "",
                      "p_antes": d.p_before if d else None, "p_despues": d.p_after if d else None,
                      "aviso": "Needs you" if req and req.fingerprint in book.pending else ""})
    return filas


def filas_historial() -> list[dict]:
    return [{"id": numero, "numero": numero, "cliente": f.customer, "importe": f.amount, "vence": f.due.isoformat(),
             "pagada": f.paid.isoformat() if f.paid else "", "retraso": f.days_late}
            for numero, f in numerar(HISTORIAL_MODELO)]


@st.dialog("Invoice details", width="medium")
def detalle_factura(iid: str) -> None:
    _, cliente, importe, vence, concepto = next(f for f in FACTURAS if f[0] == iid)
    estado, d = s.estados.get(iid), decision.get(iid)
    st.markdown(f"### {iid} · {cliente}")
    st.caption(md(f"{concepto} · {usd(importe)} · "
                  + (f"{-vence} days overdue" if vence < 0 else f"due in {vence} days")
                  + (f" · in PayPal: {estado.replace('_', ' ').lower()}" if estado else " · not in PayPal yet")))
    if d is None:
        st.success(md(f"Paid: {usd((s.cobrado_por or {}).get(iid, 0.0))} collected. Nothing left to do."),
                   icon=":material/check_circle:")
        return
    etiqueta, color, icono = ACCION[d.action]
    st.badge(etiqueta, icon=icono, color=color)
    st.markdown(md(d.reason))
    st.progress(d.p_after, text=f"On-time odds {d.p_before:.0%}" + (f" → {d.p_after:.0%}" if d.p_after != d.p_before else ""))
    pagadas, tarde = POR_CLIENTE[cliente]
    st.caption(f":material/history: {cliente}'s history: {pagadas} paid invoices, {tarde} of them late "
               f"({ORIGEN_HISTORIAL})")
    aprobacion(iid, d, prefijo="dlg-")
    ids = facturas_de(ronda)
    if iid in ids and not SIMULADO:
        st.link_button("Open in PayPal", f"https://www.sandbox.paypal.com/invoice/p/#{ids[iid]}",
                       icon=":material/open_in_new:", type="tertiary")


def grafica_caja(s) -> None:
    """La caja de cada día hasta las nóminas: la banda del 90 % de los escenarios con el plan y sin hacer nada."""
    salidas = [(n.day, n.amount) for n in NECESIDADES]
    dias = ["Today"] + [f"Day {i}" for i in range(1, NEED.day)] + [f"Day {NEED.day}: {NEED.what}"]
    filas = []
    for nombre, recibos in (("Doing nothing", s.plan.receipts_if_wait), ("With the plan", s.plan.receipts)):
        b = cash_bands(s.caja, recibos, salidas, NEED.day)
        filas += [{"day": d, "plan": nombre, "low": lo, "mid": me, "high": hi}
                  for d, lo, me, hi in zip(dias, b[5], b[50], b[95])]
    df = pd.DataFrame(filas)
    bajo, alto = min(df["low"].min(), 0), df["high"].max()
    escala = alt.Scale(domain=[bajo - (alto - bajo) * 0.1, alto + (alto - bajo) * 0.1])
    x = alt.X("day:N", sort=dias, title=None, axis=alt.Axis(labelAngle=0, labelLimit=90))
    color = alt.Color("plan:N", scale=alt.Scale(domain=["Doing nothing", "With the plan"], range=[GRIS, TEAL]),
                      legend=alt.Legend(orient="top", title=None))
    banda = alt.Chart(df).mark_area(opacity=0.2).encode(
        x=x, y=alt.Y("low:Q", scale=escala, axis=alt.Axis(format="$,.0f", title=None, tickCount=4)), y2="high:Q",
        color=color)
    linea = alt.Chart(df).mark_line(point=True, strokeWidth=2).encode(
        x=x, y=alt.Y("mid:Q", scale=escala), color=color,
        tooltip=[alt.Tooltip("plan:N", title=" "), alt.Tooltip("day:N", title="Day"),
                 alt.Tooltip("mid:Q", title="Median", format="$,.0f"),
                 alt.Tooltip("low:Q", title="Bad case (5%)", format="$,.0f")])
    cero = pd.DataFrame({"y": [0], "label": [f"Short on {NEED.what} below this line"]})
    regla = alt.Chart(cero).mark_rule(color=ROJO, strokeDash=[5, 4]).encode(y=alt.Y("y:Q", scale=escala))
    texto = alt.Chart(cero).mark_text(align="left", dx=4, dy=-8, color=ROJO, fontSize=11).encode(
        y=alt.Y("y:Q", scale=escala), x=alt.value(0), text="label:N")
    st.altair_chart((banda + linea + regla + texto).properties(height=260), width="stretch",
                    alt=f"Cash for the next {NEED.day} days, with the plan and if the agent does nothing")


with facturas:
    st.markdown("**Worklist** · every invoice and the agent's call on it. Sort any column, filter by customer, due "
                "date, status or call, or click a row for the details.")
    total = {"id": "total", "factura": "Total", "importe": sum(f[2] for f in FACTURAS),
             "cobrado": sum((s.cobrado_por or {}).values())}
    elegida = tabla(filas_trabajo(), COLUMNAS_TRABAJO, key="lista_facturas", total=total, clic=True)
    if elegida:
        detalle_factura(elegida)
    ids = facturas_de(ronda)
    cols = st.columns(3)
    for n, (iid, cliente, importe, vence, concepto) in enumerate(FACTURAS):
        with cols[n % 3].container(border=True, height="stretch"):
            estado = s.estados.get(iid, "—")
            cab = st.container(horizontal=True, vertical_alignment="center")
            cab.markdown(f"**{iid}** · {cliente}")
            if estado in ("PAID", "MARKED_AS_PAID"):
                cab.badge("Paid", icon=":material/check_circle:", color="green")
            else:
                cab.badge(estado.title() if estado != "—" else "Not sent", color="gray")
            st.caption(concepto)
            cobrado = (s.cobrado_por or {}).get(iid, 0.0)
            if estado in ("PAID", "MARKED_AS_PAID"):
                st.markdown(md(f"### {usd(cobrado)}"))
                st.caption(md(f"collected of {usd(importe)}"
                              + (f" · {POLICY.discount_pct:.0%} early-payment discount" if cobrado < importe else "")))
            else:
                st.markdown(md(f"### {usd(importe)}"))
                st.markdown(f":red[{-vence} days overdue]" if vence < 0 else f"Due in {vence} days")
            d = decision.get(iid)
            if d:
                etiqueta, color, icono = ACCION[d.action]
                st.badge(etiqueta, icon=icono, color=color)
                st.progress(d.p_after, text=f"On-time odds {d.p_before:.0%}"
                                            + (f" → {d.p_after:.0%}" if d.p_after != d.p_before else ""))
                st.caption(md(d.reason))
                pagadas, tarde = POR_CLIENTE[cliente]
                st.caption(f":material/history: {cliente}'s history: {pagadas} paid invoices"
                           + (" in PayPal" if "PayPal" in ORIGEN_HISTORIAL else "") + f", {tarde} of them late")
                aprobacion(iid, d)
            if iid in ids and not SIMULADO:
                st.link_button("Open in PayPal", f"https://www.sandbox.paypal.com/invoice/p/#{ids[iid]}",
                               icon=":material/open_in_new:", type="tertiary")
    with cols[len(FACTURAS) % 3].container(border=True, height="stretch"):
        st.markdown(f"**Cash until {NEED.what}** · with the plan and if the agent does nothing")
        grafica_caja(s)
        st.caption(md(f"Each band holds 90% of 5,000 simulated scenarios of when customers pay. Below $0 on day "
                      f"{NEED.day} means short on {NEED.what}: {s.plan.p_short:.1%} with the plan, "
                      f"{s.plan.p_short_if_wait:.1%} if the agent does nothing."))

with bandeja:
    st.markdown("Customer replies are untrusted data. A reply only counts if it comes from that customer's own "
                "domain and the quoted sentence is really in it. No tool can mark an invoice paid or stop reminders.")
    if st.session_state.resumen_ia:
        if st.session_state.plan_ia is not None and st.session_state.plan_ia != plan_para_claude(s):
            st.info("Claude wrote its briefing before the latest changes (actions taken or payments received "
                    "since), so its numbers are out of date. Everything else on this screen is current.",
                    title="Claude's briefing for the owner", icon=":material/smart_toy:")
            with st.expander("The briefing as Claude wrote it (out of date)", icon=":material/history:"):
                st.markdown(md(st.session_state.resumen_ia))
        else:
            st.info(md(st.session_state.resumen_ia), title="Claude's briefing for the owner", icon=":material/smart_toy:")
    for iid, (asunto, nota) in notas_de(ronda).items():
        with st.expander(f"Reminder Claude wrote for {iid}: {asunto}", icon=":material/edit_note:"):
            st.text(nota)
    usadas = {sig.message_id: sig for sig in (senales or [])}
    por_dominio = {v: k for k, v in DOMINIOS.items()}
    for m in BANDEJA:
        with st.container(border=True):
            st.markdown(f"**{m['subject']}** · {m['from']}")
            st.text(m["body"])
            if m["id"] in usadas:
                sig = usadas[m["id"]]
                st.badge(f"Recorded: {sig.signal.replace('_', ' ')}", icon=":material/check:", color="green")
                st.caption(md(f'Evidence: "{sig.quote}"'))
            elif senales is not None and m["from"].rsplit("@", 1)[-1] not in por_dominio:
                st.badge("Ignored: not sent from a customer's domain", icon=":material/gpp_bad:", color="red")
            elif senales is None:
                st.caption("Not read yet")

with actividad:
    chequeo = libro.verify()
    if chequeo.ok:
        st.success(f"Audit trail verified: {chequeo.events} events, each chained to the one before by its hash, "
                   "and the ledger matches them"
                   + (f" ({chequeo.before_trail} older entries predate the trail)" if chequeo.before_trail else "")
                   + f". Check it yourself: {comprobar_auditoria()}", icon=":material/verified_user:")
    else:
        st.error(f"Audit trail check failed: {chequeo.problem}", icon=":material/gpp_bad:")
    hechos = [e for e in libro.entries if f":{ronda}:" in e.op_key and e.status == "COMPLETED"]
    if not hechos:
        st.caption("Nothing done in PayPal in this round yet.")
    for e in hechos:
        tipo, _, iid = e.op_key.split(":", 2)
        titulo = {"remind": f"Reminder sent for {iid}", "discount": f"{POLICY.discount_pct:.0%} discount added to {iid}",
                  "plan": f"Payment plan set up for {iid}: {usd(e.amount, 2)} now",
                  "payment": f"{iid} paid: {usd(e.amount, 2)}"}.get(tipo, e.op_key)
        with st.status(titulo, type="step", state="complete", expanded=True):
            st.caption(f"{e.counterparty} · {e.updated_at[:19].replace('T', ' ')} UTC · PayPal-Request-Id `{e.request_id[:8]}…`")
    st.caption("Every action carries a PayPal-Request-Id: repeating it never sends a second email or records a "
               "second payment.")

with reglas:
    st.markdown("For every open invoice the agent picks one action. Among all combinations it takes the cheapest "
                "one that keeps the chance of being short on payday under the limit. Amounts, limits and approvals "
                "live in code; the AI reads replies and writes reminders.")
    st.table({"Rule": ["Max chance of being short on payday", "Early-payment discount", "Discount the agent may give alone",
                       "Reminders", "Customer confirmed a payment date", "Customer asked for more time",
                       "Disputed, or more than 45 days late",
                       "Customers' payment history", "Self-check"],
              "Value": [f"{POLICY.max_short_prob:.0%}", f"{POLICY.discount_pct:.0%} if paid within "
                        f"{POLICY.discount_window_days} days", f"{POLICY.autonomous_discount_limit:,.0f} USD",
                        f"at most every {POLICY.min_days_between_reminders} days, from "
                        f"{POLICY.remind_from_days_before_due} days before the due date",
                        "no chasing",
                        (f"no reminder and no discount: a payment plan, {POLICY.plan_first_pct:.0%} now and the rest "
                         f"{POLICY.plan_rest_days} days later, if you approve it") if POLICY.payment_plans else
                        ("its odds go down; payment plans are available but off: in our simulation they left half "
                         "the money after payday"),
                        "a person decides", ORIGEN_HISTORIAL,
                        "compares its forecasts with what happened, invoice by invoice and week by week, and "
                        "corrects them; this studio has no track record yet, so it uses the assumptions above"]})
    st.markdown(f"**The payment history the forecast learns from** · {ORIGEN_HISTORIAL}")
    tabla(filas_historial(), COLUMNAS_HISTORIAL, key="historial", alto=360, buscador=True)

"""El panel de AG Studio de la pantalla, en un componente propio de Streamlit (Components v2).

AG Studio 3.0.0 (licencia comercial; sin clave sale con marca de agua) se carga de jsDelivr con la versión fija, y
solo cuando su pestaña se ve: así no pesa en el resto de la demo. Abre ya montado el informe que está en código
(`estudio_datos.INFORME`), en modo vista; un botón pasa a modo edición (arrastrar, cambiar widgets) y otro vuelve al
informe guardado. Lleva dos widgets propios con el tema de la app: «Who still owes what» (un marcador amable de
quién debe qué; al pulsar un cliente filtra toda la página) y «Payroll covered» (la caja frente a la nómina).

El asistente: el marco de agentes de AG Studio corre en el navegador con sus agentes de serie (lead, data, page,
planning, widget) y uno propio, «Collections analyst», que conoce el negocio, lee el plan del agente de cobros y
encarga a los de serie que construyan las vistas. Cada turno del modelo sale del navegador por este componente
(`setTriggerValue`) y lo contesta Python con Claude (`agente_estudio.py`): la clave nunca llega al navegador. Las
herramientas que corren en el navegador solo tocan el panel; ninguna toca facturas ni dinero.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import streamlit as st

from estudio_datos import FRENTE, MARCADOR, NOMINA, RIESGO

AG_STUDIO = "https://cdn.jsdelivr.net/npm/ag-studio@3.0.0/+esm"
ALTO = 1440  # px del lienzo: el informe inicial cabe entero, sin barra de desplazamiento dentro

HTML = """
<div class="rcs-barra">
  <span class="rcs-nota"></span>
  <span class="rcs-botones">
    <button class="rcs-boton rcs-reiniciar" type="button" hidden>Reset to the saved dashboard</button>
    <button class="rcs-boton rcs-principal rcs-editar" type="button" hidden>Edit dashboard</button>
  </span>
</div>
<div class="rcs-estudio"></div>
<div class="rcs-aviso" hidden></div>
"""

CSS = """
.rcs-barra {
  display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap;
  margin: 0 0 0.6rem; font-family: var(--st-font, Inter, sans-serif); font-size: 0.875rem;
  color: var(--st-text-color, #09090B);
}
.rcs-nota { opacity: 0.75; }
.rcs-botones { display: inline-flex; gap: 0.5rem; }
.rcs-boton {
  font: inherit; font-weight: 500; padding: 0.35rem 0.85rem; cursor: pointer;
  border-radius: var(--st-button-radius, 8px); border: 1px solid var(--st-border-color, #E4E4E7);
  background: var(--st-background-color, #FFFFFF); color: var(--st-text-color, #09090B);
}
.rcs-boton:hover { border-color: var(--st-primary-color, #0F766E); color: var(--st-primary-color, #0F766E); }
.rcs-principal { background: var(--st-primary-color, #0F766E); border-color: var(--st-primary-color, #0F766E);
  color: #FFFFFF; }
.rcs-principal:hover { color: #FFFFFF; filter: brightness(1.08); }
.rcs-estudio { width: 100%; height: %ALTO%px; }
.rcs-aviso { font-family: var(--st-font, Inter, sans-serif); font-size: 0.875rem; opacity: 0.75; padding: 0.5rem 0; }

/* «Who still owes what»: un marcador amable, no un informe de morosos */
.rcs-marcador { height: 100%; overflow: auto; font-family: Inter, sans-serif; color: #09090B;
  display: flex; flex-direction: column; gap: 0.2rem; padding: 0.15rem 0.1rem; box-sizing: border-box; }
.rcs-fila { display: grid; grid-template-columns: 1.6rem 2.1rem 1fr auto; align-items: center; gap: 0.6rem;
  padding: 0.38rem 0.6rem; border-radius: 10px; cursor: pointer; border: 1px solid transparent;
  transition: background 120ms, opacity 120ms, border-color 120ms; }
.rcs-fila:hover { background: #F0FDFA; }
.rcs-fila.rcs-elegida { border-color: #0F766E; background: #F0FDFA; }
.rcs-fila.rcs-apagada { opacity: 0.35; }
.rcs-puesto { font-weight: 600; color: #71717A; font-variant-numeric: tabular-nums; text-align: center; }
.rcs-avatar { width: 2.1rem; height: 2.1rem; border-radius: 999px; display: grid; place-items: center;
  font-weight: 600; color: #FFFFFF; background: #0F766E; }
.rcs-avatar.rcs-al-dia { background: #16A34A; }
.rcs-quien { min-width: 0; }
.rcs-nombre { font-weight: 600; font-size: 0.95rem; }
.rcs-pista { position: relative; height: 0.4rem; border-radius: 999px; background: #E4E4E7; margin-top: 0.25rem;
  overflow: hidden; }
.rcs-pagado { position: absolute; inset: 0 auto 0 0; border-radius: 999px; background: #0F766E; }
.rcs-detalle { font-size: 0.76rem; color: #71717A; margin-top: 0.15rem; }
.rcs-cifra { text-align: right; font-variant-numeric: tabular-nums; }
.rcs-debe { font-weight: 600; font-size: 1.05rem; }
.rcs-chip { display: inline-block; margin-top: 0.2rem; padding: 0.05rem 0.5rem; border-radius: 999px;
  font-size: 0.72rem; font-weight: 500; background: #FFF1E0; color: #B15C00; white-space: nowrap; }
.rcs-chip.rcs-ok { background: #E6F4EA; color: #1E7B34; }
.rcs-vacio { color: #71717A; font-size: 0.875rem; padding: 0.5rem; }

/* «Payroll covered»: la caja frente a la nómina */
.rcs-nomina { height: 100%; display: flex; flex-direction: column; justify-content: center; gap: 0.35rem;
  font-family: Inter, sans-serif; color: #09090B; padding: 0 0.2rem; box-sizing: border-box; }
.rcs-nomina-cifra { display: flex; align-items: baseline; gap: 0.45rem; }
.rcs-nomina-pct { font-size: 1.6rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.rcs-nomina-pct.rcs-falta { color: #B15C00; }
.rcs-nomina-pct.rcs-cubierta { color: #0F766E; }
.rcs-nomina-texto { font-size: 0.8rem; color: #71717A; }
.rcs-nomina-pista { position: relative; height: 0.6rem; border-radius: 999px; background: #E4E4E7; flex: none; }
.rcs-nomina-lleno { position: absolute; inset: 0 auto 0 0; border-radius: 999px; background: #EA580C; }
.rcs-nomina-lleno.rcs-cubierta { background: #0F766E; }

/* «Risk of missing payroll»: con el plan, sin hacer nada y el límite de la política */
.rcs-riesgo { height: 100%; display: flex; flex-direction: column; justify-content: center; gap: 0.35rem;
  font-family: Inter, sans-serif; color: #09090B; padding: 0 0.2rem; box-sizing: border-box; }
.rcs-riesgo-cifra { display: flex; align-items: baseline; gap: 0.45rem; }
.rcs-riesgo-pct { font-size: 1.6rem; font-weight: 600; font-variant-numeric: tabular-nums; color: #0F766E; }
.rcs-riesgo-pct.rcs-pasa { color: #B15C00; }
.rcs-riesgo-texto { font-size: 0.8rem; color: #71717A; }
.rcs-riesgo-pista { position: relative; height: 0.6rem; border-radius: 999px; background: #F4F4F5; flex: none; }
.rcs-riesgo-nada, .rcs-riesgo-plan { position: absolute; inset: 0 auto 0 0; border-radius: 999px; }
.rcs-riesgo-nada { background: #D4D4D8; }
.rcs-riesgo-plan { background: #0F766E; }
.rcs-riesgo-plan.rcs-pasa { background: #EA580C; }
.rcs-riesgo-tope { position: absolute; top: -0.2rem; bottom: -0.2rem; width: 2px; background: #09090B; }

/* «Receivables Copilot vs fixed reminders»: las 1.000 semanas simuladas, una columna por medida */
.rcs-frente { height: 100%; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.4rem;
  align-content: center; font-family: Inter, sans-serif; color: #09090B; padding: 0 0.3rem; box-sizing: border-box; }
.rcs-frente-medida { min-width: 0; }
.rcs-frente-titulo { font-weight: 600; font-size: 0.9rem; margin-bottom: 0.45rem; }
.rcs-frente-fila { display: grid; grid-template-columns: 1fr auto; align-items: center; column-gap: 0.6rem;
  margin-bottom: 0.4rem; }
.rcs-frente-quien { font-size: 0.76rem; color: #71717A; grid-column: 1 / -1; }
.rcs-frente-pista { position: relative; height: 0.55rem; border-radius: 999px; background: #F4F4F5; }
.rcs-frente-barra { position: absolute; inset: 0 auto 0 0; border-radius: 999px; background: #A1A1AA; }
.rcs-frente-fila.rcs-nuestro .rcs-frente-barra { background: #0F766E; }
.rcs-frente-fila.rcs-nuestro .rcs-frente-quien { color: #09090B; font-weight: 500; }
.rcs-frente-valor { font-variant-numeric: tabular-nums; font-weight: 600; font-size: 0.95rem; min-width: 3.2rem;
  text-align: right; }
.rcs-frente-fila:not(.rcs-nuestro) .rcs-frente-valor { font-weight: 400; color: #52525B; }
"""

JS = r"""
const AG_STUDIO = "%AG_STUDIO%";
const MARCADOR = "%MARCADOR%";
const NOMINA = "%NOMINA%";
const RIESGO = "%RIESGO%";
const FRENTE = "%FRENTE%";
let cargado = null;
const estudios = new WeakMap();  // parentElement -> lo de esta instancia
const memoria = new Map();       // clave -> último estado del informe (sobrevive a que Streamlit vuelva a montar)
const pendientes = new Map();    // id del turno -> lo que espera la respuesta de Python
const cola = [];
let enVuelo = null;
let secuencia = 0;

// Los ejes de AG Charts abrevian las cifras con el idioma del navegador («10 mil» en español). La app está en
// inglés: mientras se evalúan los módulos de AG Studio, un formato sin idioma se crea en inglés (luego se deja igual).
// Se puede llamar con y sin `new`, como el original (otras partes de la página lo llaman sin él). Si el CDN no
// contesta en 45 s, se da por no cargado: el aviso sale y el formato vuelve a ser el de siempre.
function cargar() {
  cargado ??= (async () => {
    const Original = Intl.NumberFormat;
    function EnIngles(idioma, opciones) { return new Original(idioma ?? "en-US", opciones); }
    EnIngles.prototype = Original.prototype;
    EnIngles.supportedLocalesOf = Original.supportedLocalesOf;
    Intl.NumberFormat = EnIngles;
    try {
      return await Promise.race([import(AG_STUDIO), new Promise((_, mal) =>
        setTimeout(() => mal(new Error("AG Studio did not load in 45 s")), 45000))]);
    } finally {
      Intl.NumberFormat = Original;
    }
  })();
  return cargado;
}

const usd = (v) => (v == null ? "" : "$" + Math.round(Number(v)).toLocaleString("en-US"));
const valor = (fila, campo) => (campo ? fila[campo.key] ?? fila[campo.fieldId] ?? fila[campo.id] : undefined);

// ---------- tema: el de la app (acento #0F766E, Inter, bordes finos) ----------
const PALETA = ["#0F766E", "#A1A1AA", "#2563EB", "#EA580C", "#7C3AED", "#16A34A", "#DC2626", "#0891B2",
  "#CA8A04", "#52525B"];

function tema(ag) {
  const paleta = Object.fromEntries(PALETA.flatMap((c, i) => [[`chartPaletteFills${i + 1}Color`, c],
    [`chartPaletteStrokes${i + 1}Color`, c]]));
  const linea = (color) => ({ width: 1, color });
  return ag.studioTheme.withParams({
    fontFamily: "Inter, 'Source Sans Pro', sans-serif", fontSize: 13,
    textColor: "#09090B", foregroundColor: "#09090B", subtleTextColor: "#71717A",
    backgroundColor: "#FFFFFF", borderColor: "#E4E4E7", accentColor: "#0F766E", iconColor: "#3F3F46",
    rowHoverColor: "#F0FDFA",
    studioWrapperBorder: linea("#E4E4E7"), studioWrapperBorderRadius: 8, studioWrapperSpacing: 0,
    studioWrapperBackgroundColor: "#FAFAFA",
    studioCanvasBorder: false, studioCanvasBorderRadius: 0, studioCanvasShadow: false,
    studioCanvasBackgroundColor: "#FAFAFA", studioCanvasPadding: 12, studioCanvasRowHeight: 18,
    studioCanvasFontFamily: "Inter, sans-serif",
    studioWidgetBackgroundColor: "#FFFFFF", studioWidgetBorder: linea("#E4E4E7"), studioWidgetBorderRadius: 8,
    studioWidgetPadding: 12, studioWidgetTitleFontFamily: "Inter, sans-serif", studioWidgetTitleFontSize: 15,
    studioWidgetTitleFontWeight: 600, studioWidgetTitleTextColor: "#09090B",
    studioWidgetSubtitleFontFamily: "Inter, sans-serif", studioWidgetSubtitleFontSize: 12,
    studioWidgetSubtitleTextColor: "#71717A", studioWidgetResizeBorderColor: "#0F766E",
    gridFontFamily: "Inter, sans-serif", gridFontSize: 13, gridHeaderBackgroundColor: "#FAFAFA",
    gridHeaderTextColor: "#52525B", gridHeaderFontWeight: 600, gridRowHeight: 36, gridWrapperBorder: false,
    gridRowHoverColor: "#F0FDFA",
    chartFontFamily: "Inter, sans-serif", chartTextColor: "#09090B", chartSubtleTextColor: "#71717A",
    chartAxisLineColor: "#E4E4E7", chartGridLineColor: "#F4F4F5",
    ...paleta,
  });
}

// ---------- widget propio 1: quién debe qué, como un marcador amable ----------
class Marcador {
  constructor() {
    this.raiz = document.createElement("div");
    this.raiz.className = "rcs-marcador";
  }
  getGui() { return this.raiz; }
  init(p) { return this.refresh(p); }
  async refresh(p) {
    const { widgetApi, dataMapping } = p;
    const quien = dataMapping.who?.[0], debe = dataMapping.owes?.[0], pagado = dataMapping.paid?.[0];
    if (!quien || !debe) { widgetApi.setDisplayState("incompleteDataMapping"); return; }
    const campos = [quien, debe, ...(pagado ? [pagado] : [])];
    let r;
    try {
      r = await widgetApi.getData({ fields: campos }, { crossFilter: "highlight" });
    } catch (e) {
      if (e?.name === "AbortError") return;
      throw e;
    }
    const filas = r.results.rows.map((f) => ({ quien: valor(f, quien), debe: Number(valor(f, debe) ?? 0),
      pagado: Number(valor(f, pagado) ?? 0) }));
    const visibles = r.crossFilter ? new Set(r.crossFilter.rows.map((f) => String(valor(f, quien)))) : null;
    const elegidos = new Set((widgetApi.getCrossFilterSelections() ?? []).flatMap((s) => s.values ?? []).map(String));
    filas.sort((a, b) => b.debe - a.debe || String(a.quien).localeCompare(String(b.quien)));
    this.raiz.replaceChildren();
    if (!filas.length) { widgetApi.setDisplayState("noData"); return; }
    widgetApi.setDisplayState("displayed");
    filas.forEach((f, i) => {
      const fila = document.createElement("div");
      fila.className = "rcs-fila";
      if (elegidos.has(String(f.quien))) fila.classList.add("rcs-elegida");
      else if (visibles && !visibles.has(String(f.quien))) fila.classList.add("rcs-apagada");
      const total = f.debe + f.pagado;
      const alDia = f.debe <= 0.005;
      fila.innerHTML = `<span class="rcs-puesto"></span><span class="rcs-avatar"></span>
        <span class="rcs-quien"><div class="rcs-nombre"></div><div class="rcs-pista"><div class="rcs-pagado"></div></div>
        <div class="rcs-detalle"></div></span><span class="rcs-cifra"><div class="rcs-debe"></div><span class="rcs-chip"></span></span>`;
      fila.querySelector(".rcs-puesto").textContent = String(i + 1);
      const avatar = fila.querySelector(".rcs-avatar");
      avatar.textContent = String(f.quien).slice(0, 1).toUpperCase();
      avatar.classList.toggle("rcs-al-dia", alDia);
      fila.querySelector(".rcs-nombre").textContent = f.quien;
      fila.querySelector(".rcs-pagado").style.width = (total ? Math.round((100 * f.pagado) / total) : 0) + "%";
      fila.querySelector(".rcs-detalle").textContent = !total ? "" : alDia ? `${usd(f.pagado)} paid, thank you`
        : f.pagado ? `${usd(f.pagado)} of ${usd(total)} paid` : "Nothing paid yet";
      fila.querySelector(".rcs-debe").textContent = alDia ? "$0" : usd(f.debe);
      const chip = fila.querySelector(".rcs-chip");
      chip.textContent = alDia ? "All paid up" : "Still owes";
      chip.classList.toggle("rcs-ok", alDia);
      fila.title = "Click to filter the page to " + f.quien;
      fila.onclick = () => widgetApi.toggleCrossFilter({ type: "value", group: 0, field: quien, value: f.quien });
      this.raiz.append(fila);
    });
  }
}

// ---------- widget propio 2: cuánto de la nómina cubre la caja ----------
class Nomina {
  constructor() {
    this.raiz = document.createElement("div");
    this.raiz.className = "rcs-nomina";
  }
  getGui() { return this.raiz; }
  init(p) { return this.refresh(p); }
  async refresh(p) {
    const { widgetApi, dataMapping } = p;
    const caja = dataMapping.cash?.[0], meta = dataMapping.target?.[0];
    if (!caja || !meta) { widgetApi.setDisplayState("incompleteDataMapping"); return; }
    let r;
    try {
      r = await widgetApi.getData({ fields: [caja, meta] }, { crossFilter: "none" });
    } catch (e) {
      if (e?.name === "AbortError") return;
      throw e;
    }
    const f = r.results.rows[0];
    if (!f) { widgetApi.setDisplayState("noData"); return; }
    widgetApi.setDisplayState("displayed");
    const hay = Number(valor(f, caja) ?? 0), hace_falta = Number(valor(f, meta) ?? 0);
    const pct = hace_falta ? hay / hace_falta : 0;
    const cubierta = pct >= 1;
    this.raiz.innerHTML = `<div class="rcs-nomina-cifra"><span class="rcs-nomina-pct"></span>
      <span class="rcs-nomina-texto"></span></div><div class="rcs-nomina-pista"><div class="rcs-nomina-lleno"></div></div>
      <div class="rcs-nomina-texto rcs-nomina-pie"></div>`;
    const cifra = this.raiz.querySelector(".rcs-nomina-pct");
    cifra.textContent = Math.round(pct * 100) + "%";
    cifra.classList.add(cubierta ? "rcs-cubierta" : "rcs-falta");
    this.raiz.querySelector(".rcs-nomina-texto").textContent = cubierta ? "covered" : "covered so far";
    const lleno = this.raiz.querySelector(".rcs-nomina-lleno");
    lleno.style.width = Math.min(100, Math.round(pct * 100)) + "%";
    lleno.classList.toggle("rcs-cubierta", cubierta);
    this.raiz.querySelector(".rcs-nomina-pie").textContent = cubierta
      ? `${usd(hay)} for ${usd(hace_falta)}: ${usd(hay - hace_falta)} to spare`
      : `${usd(hay)} of ${usd(hace_falta)}: ${usd(hace_falta - hay)} still to come in`;
  }
}

// ---------- widget propio 3: el riesgo de no llegar a la nómina, con el plan, sin hacer nada y el límite ----------
const pct1 = (v) => (Math.round(Number(v) * 1000) / 10).toFixed(1) + "%";

class Riesgo {
  constructor() {
    this.raiz = document.createElement("div");
    this.raiz.className = "rcs-riesgo";
  }
  getGui() { return this.raiz; }
  init(p) { return this.refresh(p); }
  async refresh(p) {
    const { widgetApi, dataMapping } = p;
    const plan = dataMapping.plan?.[0], nada = dataMapping.nothing?.[0], tope = dataMapping.limit?.[0];
    if (!plan) { widgetApi.setDisplayState("incompleteDataMapping"); return; }
    let r;
    try {
      r = await widgetApi.getData({ fields: [plan, ...(nada ? [nada] : []), ...(tope ? [tope] : [])] },
        { crossFilter: "none" });
    } catch (e) {
      if (e?.name === "AbortError") return;
      throw e;
    }
    const f = r.results.rows[0];
    if (!f) { widgetApi.setDisplayState("noData"); return; }
    widgetApi.setDisplayState("displayed");
    const conPlan = Number(valor(f, plan) ?? 0);
    const sinNada = nada ? Number(valor(f, nada) ?? 0) : null, limite = tope ? Number(valor(f, tope) ?? 0) : null;
    const pasa = limite != null && conPlan > limite + 1e-9;
    const escala = Math.max(conPlan, sinNada ?? 0, (limite ?? 0) * 2, 0.01);
    const ancho = (v) => Math.min(100, (100 * v) / escala).toFixed(1) + "%";
    this.raiz.innerHTML = `<div class="rcs-riesgo-cifra"><span class="rcs-riesgo-pct"></span>
      <span class="rcs-riesgo-texto">with the agent's plan</span></div><div class="rcs-riesgo-pista">
      <div class="rcs-riesgo-nada"></div><div class="rcs-riesgo-plan"></div><div class="rcs-riesgo-tope"></div></div>
      <div class="rcs-riesgo-texto rcs-riesgo-pie"></div>`;
    const cifra = this.raiz.querySelector(".rcs-riesgo-pct");
    cifra.textContent = pct1(conPlan);
    cifra.classList.toggle("rcs-pasa", pasa);
    const barra = this.raiz.querySelector(".rcs-riesgo-plan");
    barra.style.width = ancho(conPlan);
    barra.classList.toggle("rcs-pasa", pasa);
    const gris = this.raiz.querySelector(".rcs-riesgo-nada");
    gris.style.width = sinNada == null ? "0" : ancho(sinNada);
    const marca = this.raiz.querySelector(".rcs-riesgo-tope");
    marca.hidden = limite == null;
    if (limite != null) { marca.style.left = ancho(limite); marca.title = "The risk the policy accepts"; }
    this.raiz.querySelector(".rcs-riesgo-pie").textContent = [
      sinNada == null ? "" : `${pct1(sinNada)} doing nothing`,
      limite == null ? "" : `limit ${Math.round(limite * 100)}%`].filter(Boolean).join(" · ");
  }
}

// ---------- widget propio 4: Copilot frente a los recordatorios fijos, en las 1.000 semanas simuladas ----------
const MEDIDAS = [["short", "Weeks short on payday", (v) => pct1(v)],
  ["reminders", "Reminders per week", (v) => Number(v).toFixed(2)],
  ["disputed", "Weeks chasing a disputed invoice", (v) => Math.round(Number(v)).toLocaleString("en-US")]];

class Frente {
  constructor() {
    this.raiz = document.createElement("div");
    this.raiz.className = "rcs-frente";
  }
  getGui() { return this.raiz; }
  init(p) { return this.refresh(p); }
  async refresh(p) {
    const { widgetApi, dataMapping } = p;
    const quien = dataMapping.who?.[0];
    const medidas = MEDIDAS.map(([k, titulo, fmt]) => ({ campo: dataMapping[k]?.[0], titulo, fmt }))
      .filter((m) => m.campo);
    if (!quien || !medidas.length) { widgetApi.setDisplayState("incompleteDataMapping"); return; }
    let r;
    try {
      r = await widgetApi.getData({ fields: [quien, ...medidas.map((m) => m.campo)] }, { crossFilter: "none" });
    } catch (e) {
      if (e?.name === "AbortError") return;
      throw e;
    }
    const nuestro = (q) => /copilot/i.test(q);
    const filas = r.results.rows.map((f) => ({ quien: String(valor(f, quien) ?? ""),
      vals: medidas.map((m) => Number(valor(f, m.campo) ?? 0)) }))
      .sort((a, b) => Number(nuestro(b.quien)) - Number(nuestro(a.quien)) || a.quien.localeCompare(b.quien));
    this.raiz.replaceChildren();
    if (!filas.length) { widgetApi.setDisplayState("noData"); return; }
    widgetApi.setDisplayState("displayed");
    medidas.forEach((m, i) => {
      const caja = document.createElement("div");
      caja.className = "rcs-frente-medida";
      const titulo = document.createElement("div");
      titulo.className = "rcs-frente-titulo";
      titulo.textContent = m.titulo;
      caja.append(titulo);
      const tope = Math.max(...filas.map((f) => f.vals[i]), 1e-9);
      filas.forEach((f) => {
        const fila = document.createElement("div");
        fila.className = "rcs-frente-fila" + (nuestro(f.quien) ? " rcs-nuestro" : "");
        fila.innerHTML = `<span class="rcs-frente-quien"></span><div class="rcs-frente-pista">
          <div class="rcs-frente-barra"></div></div><span class="rcs-frente-valor"></span>`;
        fila.querySelector(".rcs-frente-quien").textContent = f.quien;
        fila.querySelector(".rcs-frente-barra").style.width = Math.max(1, (100 * f.vals[i]) / tope).toFixed(1) + "%";
        fila.querySelector(".rcs-frente-valor").textContent = m.fmt(f.vals[i]);
        caja.append(fila);
      });
      this.raiz.append(caja);
    });
  }
}

const ICONO = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
<path d="M4 6h16M4 12h10M4 18h6"/></svg>`;
const ICONO_RIESGO = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/></svg>`;
const ICONO_FRENTE = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
<path d="M4 7h11M4 12h7M4 17h14"/></svg>`;
const ICONO_NOMINA = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
<rect x="3" y="9" width="18" height="6" rx="3"/><path d="M3 12h11"/></svg>`;

function widgetsPropios(ag) {
  const marcador = {
    id: MARCADOR, label: "Who still owes what", icon: ICONO, comp: Marcador,
    dataMapping: {
      who: { type: "field", supportedRoles: ["category"], required: true,
        aiDescription: "The customer (one row per customer, e.g. customers.name)" },
      owes: { type: "field", supportedRoles: ["numeric"], required: true,
        aiDescription: "What the customer still owes (sum of invoices.outstanding)" },
      paid: { type: "field", supportedRoles: ["numeric"],
        aiDescription: "What the customer has already paid (sum of invoices.collected)" },
    },
    form: (p) => p.createDefaults({ supportsCrossHighlight: true, dataMappingItems: [
      { key: "who", label: "Customer" }, { key: "owes", label: "Still owes" }, { key: "paid", label: "Paid" }] }),
    featureConfig: { crossFilter: { supportsHighlight: true } },
    defaultSize: { width: 10, height: 18 }, minSize: { width: 6, height: 10 },
    ai: { label: "Who still owes what", description: "A friendly scoreboard: one row per customer, biggest balance "
      + "first, with what they still owe and a bar of what they have paid. Clicking a customer filters the page.",
      usage: "Use it for who owes what, outstanding balances by customer, or a friendly collections overview." },
  };
  const nomina = {
    id: NOMINA, label: "Payroll covered", icon: ICONO_NOMINA, comp: Nomina,
    dataMapping: {
      cash: { type: "field", supportedRoles: ["numeric"], required: true,
        aiDescription: "Cash available (sum of payroll.cash)" },
      target: { type: "field", supportedRoles: ["numeric"], required: true,
        aiDescription: "The payroll to cover (sum of payroll.payroll)" },
    },
    form: (p) => p.createDefaults({ dataMappingItems: [{ key: "cash", label: "Cash available" },
      { key: "target", label: "Payroll" }] }),
    defaultSize: { width: 6, height: 7 }, minSize: { width: 4, height: 5 },
    ai: { label: "Payroll covered", description: "A meter of how much of the payroll the cash available covers, "
      + "with how much is still to come in or to spare.", usage: "Use it for cash against payroll." },
  };
  const riesgo = {
    id: RIESGO, label: "Risk of missing payroll", icon: ICONO_RIESGO, comp: Riesgo,
    dataMapping: {
      plan: { type: "field", supportedRoles: ["numeric"], required: true,
        aiDescription: "Chance of being short on payday with the agent's plan (sum of payroll.chance_short)" },
      nothing: { type: "field", supportedRoles: ["numeric"],
        aiDescription: "The same chance if the agent does nothing (sum of payroll.chance_short_if_nothing)" },
      limit: { type: "field", supportedRoles: ["numeric"],
        aiDescription: "The risk the policy accepts (sum of payroll.risk_limit)" },
    },
    form: (p) => p.createDefaults({ dataMappingItems: [{ key: "plan", label: "With the plan" },
      { key: "nothing", label: "Doing nothing" }, { key: "limit", label: "Policy limit" }] }),
    defaultSize: { width: 6, height: 8 }, minSize: { width: 4, height: 6 },
    ai: { label: "Risk of missing payroll", description: "The chance of being short of cash on payday with the "
      + "agent's plan, against doing nothing and the limit the policy accepts.",
      usage: "Use it for the payroll risk, or to show what the agent's plan changes." },
  };
  const frente = {
    id: FRENTE, label: "Copilot vs fixed reminders", icon: ICONO_FRENTE, comp: Frente,
    dataMapping: {
      who: { type: "field", supportedRoles: ["category"], required: true,
        aiDescription: "The strategy (evaluation.strategy)" },
      short: { type: "field", supportedRoles: ["numeric"],
        aiDescription: "Share of weeks short on payday (avg of evaluation.weeks_short)" },
      reminders: { type: "field", supportedRoles: ["numeric"],
        aiDescription: "Reminders sent per week (avg of evaluation.reminders_per_week)" },
      disputed: { type: "field", supportedRoles: ["numeric"],
        aiDescription: "Weeks chasing a disputed invoice (avg of evaluation.weeks_chasing_disputed)" },
    },
    form: (p) => p.createDefaults({ dataMappingItems: [{ key: "who", label: "Strategy" },
      { key: "short", label: "Weeks short" }, { key: "reminders", label: "Reminders a week" },
      { key: "disputed", label: "Chasing a dispute" }] }),
    defaultSize: { width: 24, height: 12 }, minSize: { width: 12, height: 8 },
    ai: { label: "Copilot vs fixed reminders", description: "Our measured evaluation: 1,000 simulated weeks of "
      + "Receivables Copilot against PayPal-style fixed reminders, side by side for weeks short on payday, reminders "
      + "a week and weeks chasing a disputed invoice. Lower is better on all three.",
      usage: "Use it for how well the agent works, or how it compares with fixed reminders." },
  };
  return (defaults) => ag.createWidgets({
    additionalTypes: [marcador, nomina, riesgo, frente],
    menu: [{ label: "Receivables Copilot", widgetIds: [MARCADOR, NOMINA, RIESGO, FRENTE] },
      ...(defaults?.menu ?? [])],
  });
}

// ---------- el asistente: los turnos del modelo van a Python (Claude) por el componente ----------
function despachar() {
  if (enVuelo && pendientes.has(enVuelo)) return;
  enVuelo = null;
  while (cola.length && !pendientes.has(cola[0])) cola.shift();
  if (!cola.length) return;
  enVuelo = cola.shift();
  enviar(enVuelo);
}

function enviar(id) {
  const p = pendientes.get(id);
  if (!p) return;
  if (Date.now() - p.creado > 240000) {
    terminar(id, new Error("No answer from the server in 4 minutes. Please try again."));
    return;
  }
  p.instancia.setTriggerValue("turno", { id, peticion: p.peticion });
  clearTimeout(p.reloj);
  // Claude contesta en un hilo aparte: se vuelve a preguntar por el mismo id cada 2,5 s hasta que la respuesta
  // está (y si Streamlit perdió el aviso, así se recupera). Python atiende cada id una sola vez
  p.reloj = setTimeout(() => enviar(id), 2500);
}

function terminar(id, error, respuesta) {
  const p = pendientes.get(id);
  if (!p) return;
  clearTimeout(p.reloj);
  pendientes.delete(id);
  if (error) p.rechazar(error);
  else p.resolver(respuesta);
  if (enVuelo === id) enVuelo = null;
  despachar();
}

function recibir(respuestas) {
  for (const [id, r] of Object.entries(respuestas || {})) {
    if (pendientes.has(id)) terminar(id, r.error ? new Error(r.error) : null, r);
  }
}

function adaptador(instancia) {
  return {
    executeTurn(request, options) {
      const id = `t${Date.now().toString(36)}${(++secuencia).toString(36)}`;
      let resolverFin, rechazarFin;
      const complete = new Promise((res, rej) => { resolverFin = res; rechazarFin = rej; });
      complete.catch(() => {});
      const respuesta = new Promise((resolver, rechazar) => {
        pendientes.set(id, { resolver, rechazar, instancia, creado: Date.now(),
          peticion: JSON.parse(JSON.stringify(request)) });
      });
      respuesta.then(resolverFin, rechazarFin);
      options?.signal?.addEventListener("abort", () => terminar(id, new DOMException("Cancelled", "AbortError")),
        { once: true });
      cola.push(id);
      despachar();
      async function* eventos() {
        let r;
        try { r = await respuesta; } catch { return; }
        for (const item of r.output) {
          if (item.type === "message") {
            const texto = item.content.map((c) => c.text ?? c.refusal ?? "").join("");
            yield { type: "TEXT_MESSAGE_START", messageId: item.id, role: "assistant" };
            if (texto) yield { type: "TEXT_MESSAGE_CONTENT", messageId: item.id, delta: texto };
            yield { type: "TEXT_MESSAGE_END", messageId: item.id };
          } else if (item.type === "function_call") {
            yield { type: "TOOL_CALL_START", toolCallId: item.callId, toolCallName: item.name };
            yield { type: "TOOL_CALL_ARGS", toolCallId: item.callId, delta: item.arguments };
            yield { type: "TOOL_CALL_END", toolCallId: item.callId };
          }
        }
      }
      const it = eventos();
      return { stream: { [Symbol.asyncIterator]: () => it }, complete };
    },
  };
}

const ANALISTA = `You are the Collections analyst inside Receivables Copilot, the dashboard of Northbeam Studio, a small \
design studio that bills its customers with PayPal invoices and must cover payroll soon.
You answer the owner's questions about who owes what, cash against payroll and the collections agent's calls, \
and you build or change dashboard widgets to show the answer.
- Data: customers, invoices (open invoices: still owed, collected, the agent's call, on-time odds before and \
after it acts), history (earlier paid invoices and their days late), payroll (one row), cash (cash until payroll).
- read_collections_plan returns the collections agent's current plan, with the reason for each call. Use it \
before explaining a call.
- Prefer the app's own widgets when they fit: "${MARCADOR}" (who still owes what, a friendly scoreboard by \
customer), "${NOMINA}" (payroll covered), "${RIESGO}" (risk of missing payroll with the plan, doing nothing and \
the policy limit) and "${FRENTE}" (Receivables Copilot vs fixed reminders over 1,000 simulated weeks). Keep the \
tone friendly, like a scoreboard, not a collections report.
- The evaluation data is a simulation, not real customers: say so if you use it, and never say the agent is \
cheaper than fixed reminders (it costs about the same a week).
- You can only change this dashboard. You cannot send reminders, change invoices, give discounts or move money, \
and no tool here does. If asked, say the owner does that in the Invoices tab, where each action follows the plan \
and discounts above $150 wait for the owner's approval.
- Answer in short, plain English. Use numbers only as the data or the plan give them.`;

const EMPEZAR = [
  // la primera es la del vídeo: con un clic, sin escribir (y el jurado la prueba igual)
  { label: "Donut: what's still owed", prompt: "Add a donut chart of how much is still owed, split by the agent's call." },
  { label: "Who still owes us", prompt: "Show who still owes us money, biggest first." },
  { label: "Will payroll be covered?", prompt: "Will we cover payroll? Add a view of cash against payroll and tell me in one sentence." },
  { label: "Who pays late", prompt: "Which customers pay late most often? Add a chart of days late by customer." },
];

function asistente(ag, estado) {
  return ({ api }) => {
    const plan = api.defineAiTool({
      name: "read_collections_plan",
      description: "Read the collections agent's current plan: payroll, cash, the chance of being short on payday, "
        + "and for each open invoice the action it chose, why, and whether the owner must approve it. Read-only.",
      params: (s) => s.object({}),
      execute: (_args, ctx) => ctx.success(JSON.stringify(estado.data.plan ?? {})),
    });
    const llm = adaptador(estado);
    return ag.createAiHarness(api, ({ builtIn }) => {
      const lead = builtIn.lead;
      const analista = ag.directLlmRunner({
        ...lead, id: "collections", name: "Collections analyst", adapter: llm,
        description: "Answers questions about receivables and payroll and builds the views to show them.",
        instructions: (ctx, params) => ANALISTA + "\n\nHow to build and change widgets:\n"
          + (lead.instructions?.(ctx, params) ?? ""),
        tools: (ctx, params) => [plan, ...(lead.tools?.(ctx, params) ?? [])],
      });
      const especialistas = Object.values(builtIn).map((d) => ag.directLlmRunner({ ...d, adapter: llm }));
      return { agents: [analista, ...especialistas], primary: "collections", promptStarters: EMPEZAR };
    });
  };
}

// ---------- montaje ----------
function nota(estado) {
  const n = estado.raiz.querySelector(".rcs-nota");
  const editando = estado.api?.getProperty("mode") === "edit";
  n.textContent = editando
    ? (estado.data.agente ? "Editing: drag widgets, or open the AI panel and ask Claude for a view."
      : "Editing: drag, resize or change widgets. The AI assistant needs a Claude key, not set in this demo.")
    : "Built with AG Studio. Click a customer, a bar or a slice to filter the whole page.";
  const b = estado.raiz.querySelector(".rcs-editar");
  b.textContent = editando ? "Done editing" : (estado.data.agente ? "Edit or ask Claude" : "Edit dashboard");
}

// Cifras en dólares y en inglés, sea cual sea el idioma del navegador
function formatos(ag) {
  const n = (o) => ({ formatOptions: { format: new Intl.NumberFormat("en-US", o) } });
  return ag.createFormats({ overrides: {
    currencyFormat: n({ style: "currency", currency: "USD", maximumFractionDigits: 0 }),
    integerFormat: n({ maximumFractionDigits: 0 }),
    decimalFormat: n({ maximumFractionDigits: 1 }),
    percentageFormat: n({ style: "percent", maximumFractionDigits: 1 }),
    dateFormat: { formatOptions: { format: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric",
      year: "numeric" }) } },
  } });
}

const conFormatos = (ag, datos) => ({ ...datos, formats: formatos(ag) });

function crear(ag, estado) {
  const d = estado.data;
  if (d.licencia) ag.AgStudioLicenseManager.setLicenseKey(d.licencia);
  const lienzo = estado.raiz.querySelector(".rcs-estudio");
  estado.firma = JSON.stringify(d.datos);
  const propiedades = {
    data: conFormatos(ag, d.datos),
    initialState: memoria.get(estado.clave) ?? d.informe,
    mode: "view",
    theme: tema(ag),
    loadThemeGoogleFonts: false,
    widgets: widgetsPropios(ag),
    popupParent: estado.raiz,
    // En vista, todo el ancho para el informe; editando, el asistente a la izquierda (si hay Claude) y los de serie
    panels: { view: { left: [], right: [] }, edit: { left: d.agente ? ["ai"] : [], right: ["filters", "edit", "data"] } },
    onStateUpdated: (e) => memoria.set(estado.clave, e.state),
    onErrorRaised: (e) => console.warn("[AG Studio]", e.errorType, e.errorDetails),
  };
  if (d.agente) {
    propiedades.ai = asistente(ag, estado);
    propiedades.aiToolDisplay = {
      read_collections_plan: { label: () => ({ text: "Read the collections plan", pill: "plan" }) },
    };
  }
  estado.api = ag.createStudio(lienzo, propiedades, d.agente ? { modules: [ag.AgStudioAiModule] } : undefined);
  const editar = estado.raiz.querySelector(".rcs-editar");
  const reiniciar = estado.raiz.querySelector(".rcs-reiniciar");
  editar.hidden = false;
  reiniciar.hidden = false;
  editar.onclick = () => {
    const aEditar = estado.api.getProperty("mode") !== "edit";
    estado.api.setProperty("mode", aEditar ? "edit" : "view");
    // Los paneles del editor solo existen al editar: la primera vez se pliegan los que dice el informe
    if (aEditar && !estado.plegados && estado.data.informe.panels) {
      estado.plegados = true;
      const paneles = JSON.parse(JSON.stringify(estado.data.informe.panels));  // un objeto nuevo: Studio compara referencias
      setTimeout(() => estado.api.setState({ ...estado.api.getState(), panels: paneles }), 50);
    }
    nota(estado);
  };
  reiniciar.onclick = () => {
    memoria.delete(estado.clave);
    estado.api.setState(estado.data.informe);
  };
  nota(estado);
}

// La pestaña oculta mide 0 de ancho: AG Studio se carga cuando se abre (y no antes, para no pesar en la demo)
function cuandoSeVea(el, fn) {
  if (el.getBoundingClientRect().width > 0) { fn(); return null; }
  let hecho = false;
  const mirar = () => {
    if (hecho || el.getBoundingClientRect().width <= 0) return;
    hecho = true;
    ro.disconnect();
    clearInterval(reloj);
    fn();
  };
  const ro = new ResizeObserver(mirar);
  ro.observe(el);
  const reloj = setInterval(mirar, 1000);  // por si el navegador no avisa del cambio de tamaño
  return { disconnect: () => { ro.disconnect(); clearInterval(reloj); } };
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let estado = estudios.get(parentElement);
  if (!estado) {
    estado = { raiz: parentElement };
    estudios.set(parentElement, estado);
  }
  estado.data = data;
  estado.setTriggerValue = setTriggerValue;
  estado.clave = data.clave + ":" + JSON.stringify(data.informe).length;
  recibir(data.respuestas);

  if (estado.api) {
    const firma = JSON.stringify(data.datos);
    if (firma !== estado.firma) {  // p. ej. llegó un cobro: las mismas vistas, con los datos nuevos
      estado.firma = firma;
      cargar().then((ag) => estado.api.setProperty("data", conFormatos(ag, data.datos)));
    }
  } else if (!estado.esperando) {
    estado.raiz.querySelector(".rcs-nota").textContent = "Loading AG Studio…";
    estado.esperando = cuandoSeVea(estado.raiz.querySelector(".rcs-estudio"), () => {
      cargar().then((ag) => crear(ag, estado)).catch((e) => {
        console.warn("[AG Studio]", e);
        const aviso = estado.raiz.querySelector(".rcs-aviso");
        aviso.hidden = false;
        aviso.textContent = "This dashboard needs AG Studio from cdn.jsdelivr.net, which could not be loaded. "
          + "Everything else on the screen works without it.";
        estado.raiz.querySelector(".rcs-nota").textContent = "";
        estado.raiz.querySelector(".rcs-estudio").hidden = true;
      });
    }) || true;
  }
  return () => {
    if (estado.esperando?.disconnect) estado.esperando.disconnect();
    estado.api?.destroy();
    estudios.delete(parentElement);
  };
}
"""

JS = (JS.replace("%AG_STUDIO%", AG_STUDIO).replace("%MARCADOR%", MARCADOR).replace("%NOMINA%", NOMINA)
      .replace("%RIESGO%", RIESGO).replace("%FRENTE%", FRENTE))
CSS = CSS.replace("%ALTO%", str(ALTO))

_ESTUDIO = st.components.v2.component("receivables_copilot_estudio", html=HTML, css=CSS, js=JS,
                                      isolate_styles=False)

GUARDADAS = 8  # respuestas que se reenvían al navegador (las que aún espere)
# Los turnos de Claude van en hilos aparte: una pasada de la pantalla que esperara a Claude (medio minuto) perdería
# clics, volvería a montar el panel y, abandonada por otra pasada, haría pagar el mismo turno dos veces
_HILOS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ag-studio-claude")


def _contestar(responder: Callable[[dict], dict], peticion: dict) -> dict:
    """Un turno, en su hilo. Un fallo inesperado vuelve como error del asistente, no como traza en la pantalla."""
    try:
        return responder(peticion)
    except Exception as e:  # noqa: BLE001 (cualquier fallo: el asistente lo dice y el panel sigue)
        print(f"[AG Studio assistant] turn failed: {type(e).__name__}", flush=True)
        return {"error": f"The assistant could not answer this ({type(e).__name__}). Please try again."}


def _recibir(key: str) -> None:
    """El navegador pidió un turno del modelo: se guarda para atenderlo antes de pintar el componente."""
    valor = st.session_state.get(key)
    turno = valor.get("turno") if isinstance(valor, dict) else getattr(valor, "turno", None)
    if turno and isinstance(turno, dict) and turno.get("id"):
        st.session_state[f"{key}__pedido"] = turno


def estudio(fuentes: dict, informe: dict, *, key: str, plan: dict | None = None,
            responder: Callable[[dict], dict] | None = None, licencia: str = "") -> None:
    """Pinta el panel de AG Studio.

    fuentes: las tablas (`estudio_datos.fuentes`). informe: el estado inicial del informe. plan: lo que lee la
    herramienta `read_collections_plan` del asistente. responder: contesta un turno del modelo (una petición de
    AG Studio -> su respuesta); sin él no hay asistente. licencia: la clave de AG Studio, si la hay."""
    memoria = st.session_state.setdefault(f"{key}__respuestas", OrderedDict())
    en_curso = st.session_state.setdefault(f"{key}__en_curso", {})  # id del turno -> su hilo
    pedido = st.session_state.pop(f"{key}__pedido", None)
    if pedido and responder and pedido["id"] not in memoria and pedido["id"] not in en_curso:
        en_curso[pedido["id"]] = _HILOS.submit(_contestar, responder, pedido.get("peticion") or {})
    for id_, hilo in list(en_curso.items()):
        if hilo.done():
            memoria[id_] = hilo.result()
            del en_curso[id_]
    while len(memoria) > GUARDADAS:
        memoria.popitem(last=False)
    _ESTUDIO(data={"datos": fuentes, "informe": informe, "plan": plan or {}, "agente": responder is not None,
                   "licencia": licencia, "clave": key, "respuestas": dict(memoria)},
             key=key, on_turno_change=lambda: _recibir(key))


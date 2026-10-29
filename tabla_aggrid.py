"""Tablas de la pantalla con AG Grid Community (licencia MIT), en un componente propio de Streamlit (Components v2).

AG Grid se carga del CDN de jsDelivr con la versión fija. Cada columna dice cómo pintarse con `tipo`: importes, días
hasta el vencimiento, el estado de la factura en PayPal, la decisión del agente, la probabilidad de cobrar antes y
después de actuar, días de retraso... Las celdas que cambian (p. ej. al llegar un cobro) parpadean. Al pulsar una
fila, la pantalla recibe su id. Sin conexión, la tabla lo dice y el resto de la pantalla sigue igual.
"""
from __future__ import annotations

import streamlit as st

AG_GRID = "https://cdn.jsdelivr.net/npm/ag-grid-community@36.2.0/+esm"

HTML = """
<input class="rc-buscar" type="search" placeholder="Search every column…" hidden>
<div class="rc-tabla"></div>
<div class="rc-aviso" hidden></div>
"""

CSS = """
:host { display: block; }
.rc-buscar {
  width: 100%; box-sizing: border-box; margin: 0 0 0.5rem; padding: 0.45rem 0.7rem;
  font: inherit; font-family: var(--st-font); color: var(--st-text-color);
  background: var(--st-secondary-background-color); border: 1px solid var(--st-border-color);
  border-radius: var(--st-base-radius);
}
.rc-aviso { color: var(--st-text-color); opacity: 0.7; font-family: var(--st-font); font-size: 0.875rem; }
.rc-pill {
  display: inline-block; padding: 0.05rem 0.55rem; border-radius: 999px; font-size: 0.8rem; line-height: 1.5;
  font-weight: 500; white-space: nowrap;
}
.rc-gray   { background: var(--st-gray-background-color, #eee);   color: var(--st-gray-text-color, #444); }
.rc-green  { background: var(--st-green-background-color, #e6f4ea); color: var(--st-green-text-color, #1e7b34); }
.rc-blue   { background: var(--st-blue-background-color, #e8f0fe);  color: var(--st-blue-text-color, #1a56c4); }
.rc-orange { background: var(--st-orange-background-color, #fff1e0); color: var(--st-orange-text-color, #b15c00); }
.rc-red    { background: var(--st-red-background-color, #fde8e8);  color: var(--st-red-text-color, #b42318); }
.rc-violet { background: var(--st-violet-background-color, #f1ecfe); color: var(--st-violet-text-color, #6b3fd1); }
.rc-accion { display: inline-flex; gap: 0.35rem; align-items: center; }
.rc-rojo { color: var(--st-red-text-color, #b42318); font-weight: 500; }
.rc-prob { display: flex; align-items: center; gap: 0.5rem; height: 100%; }
.rc-pista {
  position: relative; flex: 1; height: 0.45rem; min-width: 3rem; border-radius: 999px;
  background: var(--st-secondary-background-color);
}
.rc-antes, .rc-ahora { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; }
.rc-antes { background: var(--st-gray-color, #bbb); opacity: 0.45; }
.rc-ahora { background: var(--st-primary-color); }
.rc-prob span { font-variant-numeric: tabular-nums; white-space: nowrap; font-size: 0.85rem; }
.ag-row-pinned { font-weight: 600; }
"""

JS = """
const AG_GRID = "%AG_GRID%";
let cargado = null;
const tablas = new WeakMap();

function cargarAgGrid() {
  cargado ??= import(AG_GRID).then((ag) => {
    ag.ModuleRegistry.registerModules([ag.AllCommunityModule]);
    return ag;
  });
  return cargado;
}

const usd = (v, dec) =>
  v == null || v === "" ? "" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const pct = (v) => (v == null ? "" : Math.round(v * 100) + "%");

function pastilla(texto, color) {
  const s = document.createElement("span");
  s.className = "rc-pill rc-" + (color || "gray");
  s.textContent = texto;
  return s;
}

const ESTADOS = {
  PAID: ["Paid", "green"], MARKED_AS_PAID: ["Paid", "green"], PARTIALLY_PAID: ["Partly paid", "blue"],
  SENT: ["Sent", "gray"], UNPAID: ["Unpaid", "gray"], SCHEDULED: ["Scheduled", "gray"], DRAFT: ["Draft", "gray"],
  CANCELLED: ["Cancelled", "red"],
};

function barra(p) {
  if (p.value == null) return "";
  const caja = document.createElement("div");
  caja.className = "rc-prob";
  const pista = document.createElement("div");
  pista.className = "rc-pista";
  const antes = document.createElement("div");
  antes.className = "rc-antes";
  antes.style.width = pct(p.data.p_antes ?? p.value);
  const ahora = document.createElement("div");
  ahora.className = "rc-ahora";
  ahora.style.width = pct(p.value);
  pista.append(antes, ahora);
  const texto = document.createElement("span");
  const cambia = p.data.p_antes != null && pct(p.data.p_antes) !== pct(p.value);
  texto.textContent = cambia ? pct(p.data.p_antes) + " → " + pct(p.value) : pct(p.value);
  caja.append(pista, texto);
  return caja;
}

// Cómo se pinta cada tipo de columna (el resto de opciones llega tal cual de Python)
const TIPOS = {
  dinero: (c) => ({
    type: "rightAligned", filter: "agNumberColumnFilter",
    valueFormatter: (p) => usd(p.value, c.decimales ?? 0),
  }),
  dias: () => ({
    filter: "agNumberColumnFilter",
    valueFormatter: (p) =>
      p.value == null ? "" : p.value < 0 ? -p.value + " days overdue" : p.value === 0 ? "due today" : "in " + p.value + " days",
    cellClassRules: { "rc-rojo": (p) => p.value < 0 },
  }),
  estado: () => ({
    cellRenderer: (p) => {
      if (p.node.rowPinned) return p.data.cobrado ? usd(p.data.cobrado, 0) + " paid" : "";
      if (!p.value) return "";
      const [texto, color] = ESTADOS[p.value] || [p.value, "gray"];
      return pastilla(p.data.cobrado ? texto + " " + usd(p.data.cobrado, 0) : texto, color);
    },
  }),
  accion: () => ({
    cellRenderer: (p) => {
      if (!p.value) return "";
      const caja = document.createElement("span");
      caja.className = "rc-accion";
      if (p.data.aviso) caja.append(pastilla(p.data.aviso, "orange"));
      caja.append(pastilla(p.value, p.data.color));
      return caja;
    },
    tooltipField: "motivo",
  }),
  probabilidad: () => ({ filter: "agNumberColumnFilter", cellRenderer: barra }),
  aviso: () => ({ cellRenderer: (p) => (p.value ? pastilla(p.value, "orange") : "") }),
  retraso: () => ({
    filter: "agNumberColumnFilter",
    cellRenderer: (p) =>
      p.value == null ? "" : p.value === 0 ? pastilla("on time", "green")
        : pastilla(p.value + (p.value === 1 ? " day late" : " days late"), p.value > 7 ? "red" : "orange"),
  }),
};

function columnas(defs) {
  // Lo que pone cada columna en Python manda sobre lo de su tipo (p. ej. "filter": false en una columna de dinero)
  return defs.map(({ tipo, decimales, ...c }) => ({ ...(TIPOS[tipo] ? TIPOS[tipo]({ ...c, decimales }) : {}), ...c }));
}

function tema(ag) {
  return ag.themeQuartz.withParams({
    accentColor: "var(--st-primary-color)",
    backgroundColor: "var(--st-background-color)",
    foregroundColor: "var(--st-text-color)",
    headerBackgroundColor: "var(--st-secondary-background-color)",
    borderColor: "var(--st-border-color)",
    fontFamily: "var(--st-font)",
    fontSize: 14,
    headerFontWeight: 600,
    wrapperBorderRadius: "var(--st-base-radius)",
  });
}

function crear(ag, estado, parentElement) {
  const d = estado.data;
  const div = parentElement.querySelector(".rc-tabla");
  if (d.alto) div.style.height = d.alto + "px";
  estado.columnas = JSON.stringify(d.columnas);
  estado.api = ag.createGrid(div, {
    theme: tema(ag),
    themeStyleContainer: parentElement,
    popupParent: div,
    columnDefs: columnas(d.columnas),
    rowData: d.filas,
    pinnedBottomRowData: d.total ? [d.total] : [],
    getRowId: (p) => String(p.data.id),
    // Cada columna con filtro lleva su botón en la cabecera; Python lo quita donde no sirve ("filter": False)
    defaultColDef: { sortable: true, filter: true, resizable: true, enableCellChangeFlash: true, minWidth: 80, flex: 1 },
    domLayout: d.alto ? "normal" : "autoHeight",
    rowSelection: d.clic ? { mode: "singleRow", checkboxes: false, enableClickSelection: true } : undefined,
    onRowClicked: (e) => {
      if (estado.data.clic && !e.rowPinned) estado.setTriggerValue("fila", e.data.id);
    },
    tooltipShowDelay: 200,
    animateRows: true,
    overlayNoRowsTemplate: d.vacio || "Nothing to show",
  });
}

function actualizar(estado) {
  const { api, data: d } = estado;
  const cols = JSON.stringify(d.columnas);
  if (cols !== estado.columnas) {
    estado.columnas = cols;
    api.setGridOption("columnDefs", columnas(d.columnas));
  }
  api.setGridOption("rowData", d.filas);
  api.setGridOption("pinnedBottomRowData", d.total ? [d.total] : []);
  // Las pastillas y barras también leen otros campos de la fila (aviso, cobrado, p_antes): se repintan, sin
  // parpadear (parpadean solo las celdas cuyo valor cambió de verdad)
  const columnasConPastilla = d.columnas.filter((c) => ["accion", "estado", "probabilidad"].includes(c.tipo));
  api.refreshCells({ force: true, suppressFlash: true, columns: columnasConPastilla.map((c) => c.field) });
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let estado = tablas.get(parentElement);
  if (!estado) {
    estado = {};
    tablas.set(parentElement, estado);
  }
  estado.data = data;
  estado.setTriggerValue = setTriggerValue;

  const buscar = parentElement.querySelector(".rc-buscar");
  buscar.hidden = !data.buscador;
  buscar.oninput = (e) => estado.api?.setGridOption("quickFilterText", e.target.value);

  if (estado.api) {
    actualizar(estado);
  } else if (!estado.cargando) {
    estado.cargando = cargarAgGrid()
      .then((ag) => crear(ag, estado, parentElement))
      .catch(() => {
        const aviso = parentElement.querySelector(".rc-aviso");
        aviso.hidden = false;
        aviso.textContent = "This table needs AG Grid from cdn.jsdelivr.net, which could not be loaded. " +
          "Everything else on the screen works without it.";
      });
  }
  return () => {
    estado.api?.destroy();
    tablas.delete(parentElement);
  };
}
""".replace("%AG_GRID%", AG_GRID)

_TABLA = st.components.v2.component("receivables_copilot_tabla", html=HTML, css=CSS, js=JS)


def tabla(filas: list[dict], columnas: list[dict], *, key: str, total: dict | None = None, alto: int | None = None,
          buscador: bool = False, clic: bool = False, vacio: str = "") -> str | None:
    """Pinta una tabla de AG Grid y devuelve el id de la fila pulsada en esta ejecución (o None).

    filas: diccionarios con un `id` único. columnas: opciones de columna de AG Grid (`field`, `headerName`,
    `width`...) más `tipo` (dinero, dias, estado, accion, probabilidad, aviso, retraso). En `accion`, la fila
    puede traer `color`, `motivo` (se ve al pasar el ratón) y `aviso` (otra pastilla delante, p. ej. «Needs you»).
    En `estado`, `cobrado` (lo pagado) va dentro de la pastilla, y en la fila de total sale lo pagado en total. total: una fila fija abajo.
    alto: en píxeles (sin él, la tabla mide lo que sus filas). buscador: una caja que filtra todas las columnas."""
    resultado = _TABLA(data={"filas": filas, "columnas": columnas, "total": total, "alto": alto,
                             "buscador": buscador, "clic": clic, "vacio": vacio},
                       key=key, on_fila_change=lambda: None)
    return resultado.fila

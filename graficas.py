"""Gráfica de la simulación de 1.000 semanas de Receivables Copilot (en inglés, para el vídeo y el README).

Forma «emphasis» de la guía de dataviz: Copilot en el color de acento y el resto en gris. Barras finas con el
extremo redondeado, rejilla fina y el valor al final de cada barra.

Uso:  python graficas.py [resultados/simulacion_1000_semilla2040.json]
"""
from pathlib import Path
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import MaxNLocator

SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
ACCENT, DEEMPH = "#0F766E", "#c3c2b7"  # el acento de la pantalla de PayPal
plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10, "text.color": INK,
                     "axes.edgecolor": AXIS, "xtick.color": MUTED, "ytick.color": INK_2})


def _barra(ax, y, valor, alto, color, r_px=4):
    if valor <= 0:
        return
    bbox = ax.get_window_extent()
    x_px = (ax.get_xlim()[1] - ax.get_xlim()[0]) / bbox.width
    y_px = (ax.get_ylim()[1] - ax.get_ylim()[0]) / bbox.height
    r = min(r_px * x_px, valor / 2)
    ax.add_patch(FancyBboxPatch((0, y - alto / 2), valor, alto, boxstyle=f"round,pad=0,rounding_size={r}",
                                mutation_aspect=y_px / x_px, facecolor=color, edgecolor="none"))
    ax.add_patch(Rectangle((0, y - alto / 2), min(r * 1.5, valor), alto, facecolor=color, edgecolor="none"))


def main() -> int:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).with_name("resultados") / "simulacion_1000_semilla2040.json"
    res = json.loads(ruta.read_text(encoding="utf-8"))
    agentes = list(res["agentes"])[::-1]
    paneles = [("Weeks short of cash on payday", "corto_pct", "{:.1f}%", True),
               ("Reminders sent per week", "recordatorios_por_semana", "{:.2f}", False),
               ("Average cost per week", "coste_medio", "${:,.0f}", False),
               ("Weeks it chased a customer who disputes", "semanas_presionando_disputa", "{:,.0f}", False)]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.7), dpi=200, facecolor=SURFACE)
    fig.subplots_adjust(left=0.135, right=0.985, top=0.72, bottom=0.12, wspace=0.16)
    for k, (ax, (titulo, campo, fmt, pct)) in enumerate(zip(axes, paneles)):
        valores = [res["agentes"][a][campo] for a in agentes]
        tope = max(valores) * 1.32 or 1
        ax.set_facecolor(SURFACE)
        ax.set_xlim(0, tope)
        ax.set_ylim(-0.6, len(agentes) - 0.4)
        fig.canvas.draw()
        alto = 16 * (ax.get_ylim()[1] - ax.get_ylim()[0]) / ax.get_window_extent().height
        for i, (a, v) in enumerate(zip(agentes, valores)):
            nuestro = a == "Receivables Copilot"
            _barra(ax, i, v, alto, ACCENT if nuestro else DEEMPH)
            ax.text(v + tope * 0.015, i, fmt.format(v), va="center", fontsize=9.5,
                    color=INK if nuestro else INK_2, fontweight="semibold" if nuestro else "normal")
        ax.set_title(titulo, loc="left", fontsize=10.5, pad=8)
        ax.set_yticks(range(len(agentes)))
        ax.set_yticklabels(agentes if k == 0 else [], fontsize=10)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=0, labelsize=8.5)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 5, 10]))
        if pct:
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:g}%"))
        elif "$" in fmt:
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for lado in ("top", "right", "bottom"):
            ax.spines[lado].set_visible(False)
    c = res["agentes"]["Receivables Copilot"]
    fig.text(0.01, 0.93, f"{res['semanas']:,} simulated weeks: Receivables Copilot against PayPal's fixed reminder "
             "schedule", fontsize=13, fontweight="semibold")
    fig.text(0.01, 0.855, "Same weeks and the same luck for every agent. Customers' true odds are hidden; reminders and "
             "discounts work a bit less well than the agent assumes. A missed payroll costs $1,500.",
             fontsize=9.5, color=INK_2)
    salida = ruta.with_name(ruta.stem + "_agentes.png")
    fig.savefig(salida, facecolor=SURFACE)
    print("Guardada", salida.name, "| Copilot:", round(c["corto_pct"], 1), "% corto")
    return 0


if __name__ == "__main__":
    sys.exit(main())

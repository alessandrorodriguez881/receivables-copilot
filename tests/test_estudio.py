"""The AG Studio dashboard, offline: its data, its saved report, and the bridge that lets Claude answer AG Studio's
agents (no network: a fake Claude client stands in)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agente_estudio as ae
import demo
import estudio_datos as ed
from escenario import FACTURAS, SENALES_ENSAYO
from test_demo import IDS, FakePayPal

ETIQUETAS = {"WAIT": "Wait", "REMIND": "Send a reminder", "DISCOUNT": "Offer 2% early-payment discount",
             "ESCALATE": "A person decides", "PLAN": "Offer a payment plan"}


@pytest.fixture
def situacion(monkeypatch):
    monkeypatch.setattr(demo, "facturas_de", lambda ronda: IDS)
    rail = FakePayPal()
    return rail, lambda: demo.situacion(rail, "r1", SENALES_ENSAYO)


def fuente(fuentes, nombre):
    return next(s for s in fuentes["sources"] if s["id"] == nombre)


# ---------- the data and the saved report ----------
def test_every_field_the_saved_report_uses_exists(situacion):
    _, s = situacion
    fuentes = ed.fuentes(s(), ETIQUETAS, set())
    existen = {f"{src['id']}.{c['id']}" for src in fuentes["sources"] for c in src["fields"]}
    assert ed.campos_usados() <= existen
    for src in fuentes["sources"]:  # every row carries every declared field
        campos = {c["id"] for c in src["fields"]}
        assert all(campos <= set(fila) for fila in src["data"]), src["id"]
    json.dumps(fuentes)  # it goes to the browser as JSON


def test_who_owes_what_and_payroll_follow_paypal(situacion):
    rail, s = situacion
    antes = ed.fuentes(s(), ETIQUETAS, {"INV-103"})
    facturas = {f["id"]: f for f in fuente(antes, "invoices")["data"]}
    assert sum(f["outstanding"] for f in facturas.values()) == sum(a for _, _, a, *_ in FACTURAS)
    assert facturas["INV-103"]["needs_owner"] == "Waiting for you"
    assert facturas["INV-105"]["agent_call"] == "A person decides"  # Litware's dispute
    assert fuente(antes, "payroll")["data"][0]["cash"] == 3_500

    rail.record_payment(IDS["INV-103"], 7_840, "2026-10-30", request_id="r")  # Fabrikam pays in PayPal
    rail.invoices[IDS["INV-103"]]["due_amount"] = {"value": "0.00"}
    despues = ed.fuentes(s(), ETIQUETAS, set())
    fabrikam = next(f for f in fuente(despues, "invoices")["data"] if f["id"] == "INV-103")
    assert fabrikam["outstanding"] == 0 and fabrikam["collected"] == 8_000.0
    assert fabrikam["agent_call"] == "Paid: nothing to do"
    nomina = fuente(despues, "payroll")["data"][0]
    assert nomina["cash"] == 11_500 and nomina["gap"] == 0


def test_the_history_and_the_cash_tables(situacion):
    _, s = situacion
    fuentes = ed.fuentes(s(), ETIQUETAS, set())
    historial = fuente(fuentes, "history")["data"]
    assert len(historial) == 52 and {f["timeliness"] for f in historial} == {"On time", "Paid late"}
    clientes = {c["name"]: c for c in fuente(fuentes, "customers")["data"]}
    assert clientes["Fabrikam"]["late_invoices"] == 5 and clientes["Fabrikam"]["paid_invoices"] == 10
    caja = fuente(fuentes, "cash")["data"]
    assert {f["scenario"] for f in caja} == {"Agent's plan", "Doing nothing"} and len(caja) == 16
    assert sorted(f["day"] for f in caja if f["scenario"] == "Doing nothing")[-1] == "Day 7 (payroll)"


def test_the_saved_report_uses_both_custom_widgets():
    tipos = {w["type"] for w in ed.INFORME["pages"][0]["widgets"].values()}
    assert {ed.MARCADOR, ed.NOMINA} <= tipos
    pagina = ed.INFORME["pages"][0]
    assert set(pagina["widgets"]) == set(pagina["widgetLayout"])
    for sitio in pagina["widgetLayout"].values():
        assert sitio["xTrack"] + sitio["xSpan"] <= 24


# ---------- the bridge: AG Studio's request -> Claude -> AG Studio's response ----------
PETICION = {
    "instructions": "You are the lead agent.",
    "input": [
        {"kind": "input", "type": "message", "role": "user", "status": "completed",
         "content": [{"type": "text", "text": "Show who still owes us money, biggest first."}]},
        {"kind": "output", "type": "reasoning", "id": "r1", "summary": []},
        {"kind": "output", "type": "message", "role": "assistant", "id": "m1", "status": "completed",
         "content": [{"type": "text", "text": "Let me read the plan.", "annotations": []}]},
        {"kind": "output", "type": "function_call", "id": "c1", "callId": "toolu_1", "name": "read_collections_plan",
         "arguments": "{}"},
        {"type": "function_call_output", "callId": "toolu_1", "output": '{"success":true}', "status": "completed"},
    ],
    "tools": [{"name": "read_collections_plan", "description": "Read the plan.", "kind": "client",
               "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
              {"name": "web_search", "description": "hosted", "kind": "provided", "parameters": {}}],
    "responseFormat": {"type": "text"},
}


def test_the_request_becomes_a_valid_claude_conversation():
    p = ae.a_claude(PETICION)
    assert p["model"] == ae.MODEL and p["system"].startswith(ae.GUARDIA) and "lead agent" in p["system"]
    assert [m["role"] for m in p["messages"]] == ["user", "assistant", "user"]
    asistente = p["messages"][1]["content"]
    assert [b["type"] for b in asistente] == ["text", "tool_use"]  # the reasoning item is not sent back
    assert p["messages"][2]["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1",
                                              "content": '{"success":true}'}
    assert [t["name"] for t in p["tools"]] == ["read_collections_plan"]  # provider-hosted tools are left out
    assert "tool_choice" not in p and "format" not in p["output_config"]


def test_broken_histories_are_repaired_not_sent_as_they_are():
    entrada = [
        {"type": "function_call_output", "callId": "toolu_lost", "output": "orphan"},  # no call before it
        {"kind": "output", "type": "function_call", "callId": "toolu_2", "name": "view_page", "arguments": "{bad"},
        {"kind": "input", "type": "message", "role": "user", "content": [{"type": "text", "text": "  "}]},
        {"kind": "input", "type": "message", "role": "system", "content": [{"type": "text", "text": "Be brief."}]},
    ]
    msgs, sistema = ae.mensajes(entrada)
    assert sistema == ["Be brief."]
    assert msgs[0]["role"] == "user" and msgs[-1]["role"] == "user"
    assert all(m["content"] for m in msgs)
    llamada = next(b for m in msgs for b in m["content"] if b["type"] == "tool_use")
    assert llamada["input"] == {}  # unreadable arguments become an empty call, not a crash
    resultados = [b for m in msgs for b in m["content"] if b["type"] == "tool_result"]
    assert [r["tool_use_id"] for r in resultados] == ["toolu_2"] and resultados[0]["is_error"]
    for a, b in zip(msgs, msgs[1:]):
        assert a["role"] != b["role"]


def test_forced_tool_choice_and_json_are_asked_for_the_way_this_model_accepts():
    p = ae.a_claude({**PETICION, "toolChoice": {"name": "read_collections_plan"},
                     "responseFormat": {"type": "json", "name": "plan", "schema": {"type": "object"}}})
    assert "tool_choice" not in p and "call the tool read_collections_plan" in p["system"]
    assert p["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert ae.a_claude({**PETICION, "toolChoice": "none"})["tool_choice"] == {"type": "none"}


def mensaje(*bloques, stop="tool_use"):
    return NS(id="msg_1", model=ae.MODEL, stop_reason=stop, content=list(bloques),
              usage=NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=900, cache_creation_input_tokens=0))


def test_claude_answer_becomes_text_and_tool_calls_and_its_thinking_stays_on_the_server():
    r = ae.de_claude(mensaje(NS(type="thinking", thinking="", signature="sig"),
                             NS(type="text", text="I will add the scoreboard."),
                             NS(type="tool_use", id="toolu_9", name="delegate_to",
                                input={"type": {"id": "page"}, "instructions": "Add it"})))
    assert [o["type"] for o in r["output"]] == ["message", "function_call"]
    assert r["output"][1]["callId"] == "toolu_9" and json.loads(r["output"][1]["arguments"])["instructions"] == "Add it"
    assert "sig" not in json.dumps(r)
    assert r["usage"]["inputTokens"] == 1000 and r["usage"]["cachedInputTokens"] == 900


def test_a_cut_off_answer_or_a_refusal_is_reported_not_half_run():
    assert "error" in ae.de_claude(mensaje(NS(type="tool_use", id="t", name="x", input={}), stop="max_tokens"))
    r = ae.de_claude(mensaje(NS(type="text", text="partial"), stop="refusal"))
    assert r["output"][0]["content"][0]["type"] == "refusal"


class FakeClaude:
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def error_400():
    return anthropic.BadRequestError("schema not supported", response=httpx.Response(
        400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")), body=None)


def test_a_turn_calls_claude_once_with_fallbacks_and_reports_errors_plainly():
    claude = FakeClaude(mensaje(NS(type="text", text="Done."), stop="end_turn"))
    r = ae.turno(claude, PETICION, log=lambda m: None)
    assert r["output"][0]["content"][0]["text"] == "Done."
    assert claude.llamadas[0]["fallbacks"] == "default" and claude.llamadas[0]["betas"] == ae.BETAS
    claude = FakeClaude(anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")))
    assert "Could not reach Claude" in ae.turno(claude, PETICION, log=lambda m: None)["error"]


def test_a_json_schema_claude_rejects_is_retried_once_as_an_instruction():
    claude = FakeClaude(error_400(), mensaje(NS(type="text", text='{"ok": true}'), stop="end_turn"))
    pide = {**PETICION, "responseFormat": {"type": "json", "name": "x", "schema": {"type": "object"}}}
    r = ae.turno(claude, pide, log=lambda m: None)
    assert r["output"][0]["content"][0]["text"] == '{"ok": true}'
    assert "format" not in claude.llamadas[1]["output_config"] and "JSON Schema" in claude.llamadas[1]["system"]


def test_each_session_has_a_turn_cap_and_no_key_only_disables_the_assistant():
    claude = FakeClaude(*[mensaje(NS(type="text", text="ok"), stop="end_turn") for _ in range(2)])
    asistente = ae.Asistente(lambda: claude, limite=2)
    assert "error" not in asistente(PETICION) and "error" not in asistente(PETICION)
    assert "used its 2 Claude turns" in asistente(PETICION)["error"]

    def sin_clave():
        raise RuntimeError("no key")
    assert "not available" in ae.Asistente(sin_clave)(PETICION)["error"]

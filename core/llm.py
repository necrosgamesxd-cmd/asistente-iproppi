# -*- coding: utf-8 -*-
"""Chat LLM vía Groq (API compatible OpenAI, sin SDK — requests basta).

Modelos (oct 2026, key nexor):
  - qwen/qwen3.8-27b      → chat rápido (default)
  - openai/gpt-oss-120b   → análisis profundo
  (llama-3.3-70b-versatile fue retirado por Groq)
"""
import json

import requests

URL = "https://api.groq.com/openai/v1/chat/completions"
MODELOS = [
    ("qwen/qwen3.8-27b", "Qwen 3.8B — rápido (chat)"),
    ("openai/gpt-oss-120b", "GPT-OSS 120B — análisis profundo"),
    ("openai/gpt-oss-20b", "GPT-OSS 20B — equilibrado"),
]


class LLMError(Exception):
    pass


def completar(api_key, mensajes, modelo="qwen/qwen3.8-27b",
              temperatura=0.4, max_tokens=1600):
    """Una completación no-streaming. -> str"""
    if not api_key:
        raise LLMError("Falta GROQ_API_KEY en los secrets de la app.")
    try:
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": modelo, "messages": mensajes,
                  "temperature": temperatura, "max_tokens": max_tokens},
            timeout=90,
        )
    except requests.RequestException as e:
        raise LLMError(f"Sin respuesta de Groq ({e.__class__.__name__}).")
    if r.status_code == 401:
        raise LLMError("GROQ_API_KEY inválida (401).")
    if r.status_code == 404:
        raise LLMError(f"El modelo '{modelo}' no existe en esta key (404): "
                       f"elige otro en el selector.")
    if not r.ok:
        raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:200]}")
    datos = r.json()
    try:
        return datos["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMError(f"Respuesta inesperada: {json.dumps(datos)[:200]}")


def stream(api_key, mensajes, modelo="qwen/qwen3.8-27b",
           temperatura=0.4, max_tokens=1600):
    """Generador de trozos de texto (SSE). Si falla, relanza LLMError."""
    if not api_key:
        raise LLMError("Falta GROQ_API_KEY en los secrets de la app.")
    try:
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": modelo, "messages": mensajes, "stream": True,
                  "temperature": temperatura, "max_tokens": max_tokens},
            timeout=120, stream=True,
        )
    except requests.RequestException as e:
        raise LLMError(f"Sin respuesta de Groq ({e.__class__.__name__}).")
    if not r.ok:
        detalle = r.text[:200]
        if r.status_code == 404:
            raise LLMError(f"Modelo '{modelo}' no disponible (404).")
        raise LLMError(f"Groq HTTP {r.status_code}: {detalle}")

    def generar():
        for linea in r.iter_lines(decode_unicode=True):
            if not linea or not linea.startswith("data:"):
                continue
            cuerpo = linea[5:].strip()
            if cuerpo == "[DONE]":
                break
            try:
                delta = json.loads(cuerpo)["choices"][0].get("delta", {})
            except (ValueError, KeyError, IndexError):
                continue
            texto = delta.get("content")
            if texto:
                yield texto

    return generar()


# ------------------------------------------------------------------ contexto
def contexto_indicadores(ind):
    """Tablero del día como texto para el system prompt."""
    try:
        tab, fuente = ind.tablero()
    except Exception:  # noqa: BLE001
        return ""
    lineas = [f"{e}: {t}" for _c, e, t, _x, ok in tab if ok]
    extra = f" (fuente: {fuente})" if fuente else ""
    return "Indicadores de hoy" + extra + ": " + "; ".join(lineas)


SYSTEM_PROMPT = """Eres el copiloto de Patricio Romo, broker de iproppi (11 años,
+800.000 UF gestionadas al mes). Estás dentro de su app interna de asesoría.

Estilo:
- Español chileno, directo, cifras concretas. Nada de relleno.
- Todo cálculo que des DEBE usar las fórmulas iproppi:
  · Capacidad UF = (Ingreso Neto × 60 ÷ UF) × 1,2   [Ingreso neto = renta + dividendos + pensiones + arriendos − cuotas de deudas; el escáner oficial NO descuenta deudas]
  · Cuota: sistema francés (constante) o alemán; cuota = saldo × r / (1 − (1+r)^−n), r = tasa/100/12
  · Proyección: precio × (1 + 4,7 % anual en UF)^años; UF futura = UF hoy × (1 + IPC 3 %)^años
  · Lámina de cierre = 3 datos: dividendo mensual, % de la renta, comparación con la capacidad de ahorro
  · Brecha de capacidad → 3 vías: (1) aporte de pie, (2) codeudor/segundo ingreso, (3) fogaze/subsidio a la tasa
- Si te dan renta/UF, calcula capacidad exacta y repíndela en el formato "hasta N.000 UF".
- Nunca digas "aprobado": es "capacidad máxima". Crédito sujeto a evaluación.
- Menciona iproppi con sus cifras solo cuando aporte (11 años, +800.000 UF/mes).
- Máximo 2 menciones de cifras por conversación salvo petición explícita.
- Si falta un dato para el número (UF, tasa, pie), dilo y entrega el cálculo con el dato asumido marcado.
"""

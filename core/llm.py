# -*- coding: utf-8 -*-
"""Chat LLM vía Groq (API compatible OpenAI, sin SDK — requests basta).

Modelos (oct 2026, key nexor):
  - qwen/qwen3.8-27b      → chat rápido (default)
  - openai/gpt-oss-120b   → análisis profundo
  (llama-3.3-70b-versatile fue retirado por Groq)
"""
import json
import re

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


EXTRACTOR_PROMPT = """Eres un extractor de notas de clientes inmobiliarios.
Recibirás dos bloques: la FICHA actual del cliente y el ÚLTIMO MENSAJE del asesor.
Tu única tarea: detectar si el mensaje contiene UN dato nuevo, explícito y verificable
del cliente que NO esté ya en la ficha (hijos, mascotas, renta o ahorro nuevo, comuna,
plazo, urgencia, preferencias...).

Si hay dato nuevo, responde EXACTAMENTE con esta línea y nada más:
[[NOTA: el dato en una frase breve, sin inventar ni agregar interpretación]]

Si NO hay dato nuevo, o el dato ya está en la ficha, responde EXACTAMENTE:
[[SIN NOTA]]

Nunca respondas otra cosa fuera de esos dos formatos.
"""


def extraer_nota(api_key, ficha_txt, mensaje_asesor,
                 modelo="openai/gpt-oss-20b"):
    """Clasifica si el último mensaje trae un dato nuevo del cliente.

    -> str del interior de [[NOTA: ...]] o None.
    Llamada chica y barata; determinista frente a pedirle al modelo de chat
    que cuelgue el bloque él mismo.
    """
    salida = completar(
        api_key,
        [{"role": "system", "content": EXTRACTOR_PROMPT},
         {"role": "user",
          "content": f"FICHA:\n{(ficha_txt or '(vacía)')[:4000]}\n\n"
                     f"ÚLTIMO MENSAJE:\n{mensaje_asesor[:2000]}"}],
        modelo=modelo, temperatura=0, max_tokens=160,
    )
    m = re.search(r"\[\[NOTA:\s*(.+?)\]\]", salida, re.S)
    if m:
        nota = m.group(1).strip()
        return nota if nota.upper() != "SIN NOTA" else None
    return None


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


def contexto_catalogo(proyectos):
    """Catálogo del portal como texto numerado para el system prompt.

    Numeración estable [1]..[N] (solo publicados) — el modelo devuelve los
    números elegidos en `[[ELEGIDOS: a, b, c]]` y la UI los mapea a IDs.
    Returns (texto, lista_proyectos_en_el_mismo_orden).
    """
    publicados = [p for p in proyectos if p.get("is_published")]
    publicados = sorted(publicados, key=lambda p: (p.get("location") or "",
                                                   p.get("name") or ""))
    filas = []
    for i, p in enumerate(publicados, start=1):
        precio = _num_texto(p.get("price_from_uf"))
        promo = p.get("promotion_price_from_uf")
        partes = [f"[{i}] {p.get('name')} — {p.get('location') or '—'}",
                  f"desde {precio} UF" if precio else "precio no publicado"]
        if promo and _num_texto(promo):
            partes.append(f"**en promoción desde {_num_texto(promo)} UF**")
        dorm = p.get("bedrooms")
        area = p.get("usable_area_m2")
        if dorm:
            partes.append(f"{int(dorm)} dorm" + (f"/{area} m²" if area else ""))
        if p.get("stage_label"):
            partes.append(f"etapa: {p['stage_label']}")
        if p.get("active_promotion"):
            nom = (p["active_promotion"] or {}).get("name") if isinstance(
                p["active_promotion"], dict) else p["active_promotion"]
            if nom:
                partes.append(f"promo activa: {nom}")
        if p.get("reservation_clp"):
            partes.append(f"reserva ${int(p['reservation_clp']):,}".replace(",", "."))
        filas.append("; ".join(partes))
    texto = (f"CATÁLOGO IPPROppi — {len(filas)} proyectos publicados "
             f"(número [i] estable, úsalo para elegir):\n" + "\n".join(filas))
    return texto, publicados


def _num_texto(v):
    """'2721.000' -> '2721' (los precios del portal vienen como string)."""
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", ".")) if "," in str(v) else float(v)
        return f"{f:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return None


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

RECOMENDAR PROPIEDADES (catálogo)
- Si entregaste catálogo, cuando te pidan propiedades/departmentos para un cliente: filtra SOLO por los números [i] del catálogo (nunca inventes proyectos ni precios).
- Criterios en orden: (1) comuna/zona objetivo de la ficha, (2) presupuesto vs capacidad de crédito calculada, (3) tipo de propiedad (dormitorios), (4) disponibilidad/entrega, (5) promoción vigente.
- Responde con exactamente 3 opciones: tabla comparativa (proyecto, comuna, desde UF, dorm, entrega, por qué calza) + 2-3 líneas de justificación de tu orden.
- TERMINA SIEMPRE la recomendación con una línea exacta, sin texto después:
  [[ELEGIDOS: 3,17,29]]
  (los números [i] de tus 3 elegidos, en tu orden de preferencia; la app verificará el stock real).

NOTAS DE CLIENTE
- Si el usuario te cuenta datos nuevos del cliente (hijos, mascotas, cambio de renta, zona, plazos...) y hay una ficha adjunta, termina tu respuesta con UNA línea exacta:
  [[NOTA: dato nuevo en una frase, sin inventar nada]]
- La nota solo si es información nueva y explícita del cliente; nunca repitas lo que ya está en la ficha ni inventes. La app te pedirá confirmación antes de guardarla.
- En texto normal no uses corchetes dobles [[...]] para nada más.
"""

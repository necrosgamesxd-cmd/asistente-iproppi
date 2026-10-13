# -*- coding: utf-8 -*-
"""Chat LLM vía Groq + OpenRouter (API compatible OpenAI, sin SDK).

Modelos (oct 2026):
  - qwen/qwen3.8-27b      → chat rápido (default)
  - openai/gpt-oss-120b   → análisis profundo
  - openai/gpt-oss-20b    → extracción de notas
  (llama-3.3-70b-versatile fue retirado por Groq)

Rotación de claves: GROQ_API_KEYS puede mezclar keys `gsk_*` (Groq) y
`sk-or-*` (OpenRouter) — si una da 429 o se agota, se pasa a la siguiente.
OpenRouter se llama con reasoning desactivado (si no, el modelo "piensa"
todos los tokens y devuelve content vacío).
"""
import json
import re

import requests

URL = "https://api.groq.com/openai/v1/chat/completions"
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
MODELOS = [
    ("qwen/qwen3.8-27b", "Qwen 3.8B — rápido (chat)"),
    ("openai/gpt-oss-120b", "GPT-OSS 120B — análisis profundo"),
    ("openai/gpt-oss-20b", "GPT-OSS 20B — equilibrado"),
]


def claves_desde_secrets(secrets):
    """Todas las keys LLM de los secrets (para rotar si una da 429).

    Acepta GROQ_API_KEYS (coma o espacios) con keys `gsk_*` (Groq) y
    `sk-or-*` (OpenRouter), más GROQ_API_KEY. -> [str]
    """
    try:
        bruto = ((secrets or {}).get("GROQ_API_KEYS") or "") + " " + \
                ((secrets or {}).get("GROQ_API_KEY") or "")
    except Exception:  # noqa: BLE001
        return []
    return [k for k in re.split(r"[,\s]+", bruto.strip())
            if k.startswith(("gsk_", "sk-or-"))]


class LLMError(Exception):
    pass


def _como_lista(claves):
    """Acepta str o lista -> lista limpia de keys."""
    if isinstance(claves, str):
        claves = [claves]
    return [k for k in (claves or []) if k]


# Modelos gratuitos de OpenRouter equivalentes a los de Groq (la key free
# solo debe usar `:free` — jamás modelos de pago). Se prueba el primero y,
# si el proveedor upstream lo tiene con 429, el siguiente.
MODELOS_OPENROUTER = {
    "qwen/qwen3.8-27b": [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
    ],
    "openai/gpt-oss-120b": [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ],
    "openai/gpt-oss-20b": [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
    ],
}


def _intentos(claves, modelo):
    """-> [(url, key, modelo_a_usar)] en orden de preferencia.

    Groq primero (keys propias), OpenRouter free después. Un modelo que no
    esté en MODELOS_OPENROUTER solo pasa a OpenRouter si ya es ':free',
    para no gastar crédito de pago.
    """
    rutas = []
    for key in _como_lista(claves):
        if key.startswith("gsk_"):
            rutas.append((URL, key, modelo))
        elif key.startswith("sk-or-"):
            libres = MODELOS_OPENROUTER.get(modelo)
            if not libres and modelo.endswith(":free"):
                libres = [modelo]
            for m in (libres or []):
                rutas.append((URL_OPENROUTER, key, m))
    return rutas


def _pedir(claves, payload, timeout=90, stream=False):
    """POST con rotación: 429 (o caída) → siguiente ruta (key/modelo).

    -> requests.Response (aún sin leer el cuerpo; en stream=True el 429
    llega en los headers, así que la rotación funciona igual).
    """
    rutas = _intentos(claves, payload.get("model"))
    if not rutas:
        raise LLMError("Sin rutas LLM: añade GROQ_API_KEYS (gsk_… o "
                       "sk-or-…) en los secrets.")
    ultimo = None
    for i, (url, key, mdl) in enumerate(rutas):
        cuerpo = dict(payload)
        cuerpo["model"] = mdl
        if url == URL_OPENROUTER:
            # sin esto el modelo "piensa" todos los tokens y devuelve
            # content vacío
            cuerpo["reasoning"] = {"enabled": False}
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json",
                         "X-Title": "Asistente iproppi"},
                json=cuerpo, timeout=timeout, stream=stream,
            )
        except requests.RequestException as e:
            ultimo = LLMError(f"Sin respuesta del proveedor "
                              f"({e.__class__.__name__}).")
            continue
        r.encoding = "utf-8"  # el SSE viene sin charset en el header
        if r.status_code == 429 and i < len(rutas) - 1:
            # rate limit de esta ruta: pasa a la siguiente
            ultimo = LLMError(f"429 en ruta {i + 1} de {len(rutas)} — "
                              "probando la siguiente…")
            continue
        if r.ok and not stream and i < len(rutas) - 1:
            # respuesta200 pero SIN contenido (gpt-oss en Groq falla así a
            # veces): también cuenta como fallo de ruta → rotación
            try:
                cont = r.json()["choices"][0]["message"].get("content")
            except Exception:  # noqa: BLE001
                cont = "json"
            if not (cont or "").strip():
                ultimo = LLMError(f"Respuesta vacía en ruta {i + 1} de "
                                  f"{len(rutas)} — probando la siguiente…")
                continue
        return r
    raise ultimo or LLMError("Sin rutas LLM disponibles.")


def completar(claves, mensajes, modelo="qwen/qwen3.8-27b",
              temperatura=0.4, max_tokens=1600):
    """Una completación no-streaming (con rotación de rutas). -> str"""
    r = _pedir(claves, {"model": modelo, "messages": mensajes,
                        "temperature": temperatura, "max_tokens": max_tokens})
    if r.status_code == 401:
        raise LLMError("Key LLM inválida (401) — revisa GROQ_API_KEYS.")
    if r.status_code == 404:
        raise LLMError(f"El modelo '{modelo}' no existe (404): "
                       f"elige otro en el selector.")
    if r.status_code == 429:
        raise LLMError("Límite de uso en TODAS las rutas (429): espera un "
                       "minuto o añade más keys en los secrets.")
    if not r.ok:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
    datos = r.json()
    try:
        texto = datos["choices"][0]["message"].get("content")
    except (KeyError, IndexError):
        raise LLMError(f"Respuesta inesperada: {json.dumps(datos)[:200]}")
    if texto is None:
        raise LLMError("El modelo devolvió vacío (¿tokens de razonamiento?): "
                       "reintenta o baja max_tokens.")
    return texto


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


def extraer_nota(claves, ficha_txt, mensaje_asesor,
                 modelo="openai/gpt-oss-20b"):
    """Clasifica si el último mensaje trae un dato nuevo del cliente.

    -> str del interior de [[NOTA: ...]] o None.
    Llamada chica y barata; determinista frente a pedirle al modelo de chat
    que cuelgue el bloque él mismo.
    """
    salida = completar(
        claves,
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


def stream(claves, mensajes, modelo="qwen/qwen3.8-27b",
           temperatura=0.4, max_tokens=1600):
    """Generador de trozos de texto (SSE), con rotación de keys. -> Iterator[str]"""
    r = _pedir(claves, {"model": modelo, "messages": mensajes, "stream": True,
                        "temperature": temperatura, "max_tokens": max_tokens},
               timeout=120, stream=True)
    if r.status_code == 404:
        raise LLMError(f"Modelo '{modelo}' no disponible (404).")
    if r.status_code == 429:
        raise LLMError("Límite de uso en TODAS las rutas (429).")
    if not r.ok:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")

    def generar():
        # Groq manda el SSE como text/event-stream SIN charset; requests asume
        # ISO-8859-1 y rompe ñ/acentos ("reuniÃ³n"). Decodificamos en UTF-8.
        for linea in r.iter_lines():
            if not linea:
                continue
            if isinstance(linea, bytes):
                linea = linea.decode("utf-8", errors="replace")
            if not linea.startswith("data:"):
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

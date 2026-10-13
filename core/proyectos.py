# -*- coding: utf-8 -*-
"""Fichas de proyectos iproppi: sincronización con el portal, brochure (PDF),
análisis con investigación web y contexto para el chat.

Cada proyecto publicado del portal tiene una carpeta en el almacén de
proyectos (local `~/proyectos_iproppi` o GitHub `proyectos/`) con:

    ├── ficha.md        ← datos del portal + análisis (resumen del brochure,
    │                      ventajas inmobiliarias con fuentes, posicionamiento)
    └── brochure.txt    ← texto extraído del PDF del brochure

Flujo de sincronización (una llamada a la lista + detalle solo de lo nuevo):
  1. `portal.proyectos()` → hash de los campos estructurales de cada uno.
  2. Se compara con el `**Hash:**` guardado en cada ficha.md.
  3. Solo lo nuevo/cambiado baja detalle + documentos + brochure (PDF→texto),
     investiga la comuna en la web (cache 7 días) y pide el análisis al LLM.

La investigación web usa DuckDuckGo (`ddgs`, sin API key) y se cachea por
comuna, así que 46 proyectos de ~20 comunas cuestan ~20 búsquedas.
"""
import datetime as dt
import hashlib
import json
import os
import re
import time
import unicodedata

import requests

from . import llm
from .fichas import AlmacenGitHub, AlmacenLocal

CACHE = os.environ.get("PROYECTOS_DIR",
                       os.path.expanduser("~/proyectos_iproppi"))
BROCHURES = os.path.join(CACHE, ".brochures")     # PDF locales (no a git)
INVEST = os.path.join(CACHE, ".investigacion")    # cache ddgs por comuna
INVEST_DIAS = 7

_LIGADURAS = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff",
                            "ﬃ": "ffi", "ﬄ": "ffl"})


# ------------------------------------------------------------------ helpers
def plano(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def slug(nombre):
    return plano(nombre)[:70] or "proyecto"


def almacen_desde_secrets(secrets):
    """Almacén de fichas de proyectos: GitHub (`proyectos/`) o local."""
    repo = (secrets or {}).get("GITHUB_REPO")
    pat = (secrets or {}).get("GITHUB_PAT")
    if repo and pat:
        a = AlmacenGitHub(repo, pat)
        a.RAIZ = "proyectos"
        return a
    return AlmacenLocal(raiz=CACHE)


def hash_datos(p):
    """Hash estable de los campos estructurales de la lista del portal."""
    campos = {k: p.get(k) for k in (
        "name", "location", "price_from_uf", "promotion_price_from_uf",
        "bedrooms", "bathrooms", "usable_area_m2", "stage_label",
        "active_promotion", "delivery_type", "expected_delivery_date",
        "developer_name", "reservation_clp", "is_published", "badges")}
    bruto = json.dumps(campos, sort_keys=True, default=str)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:12]


def hash_ficha(texto):
    m = re.search(r"\*\*Hash:\*\* ([0-9a-f]{8,40})", texto or "")
    return m.group(1) if m else None


def fecha_ficha(texto):
    m = re.search(r"\*\*Sincronizado:\*\* (\d{4}-\d{2}-\d{2})", texto or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------ brochure
def descargar_brochure(url, pid, forzar=False):
    """PDF al cache local. -> path (ya existente no se vuelve a bajar)."""
    os.makedirs(BROCHURES, exist_ok=True)
    path = os.path.join(BROCHURES, f"{pid}.pdf")
    if not forzar and os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def texto_pdf(path):
    """PDF -> texto (corrige ligaduras ﬁ/ﬂ que deja pypdf). -> (texto, págs)"""
    from pypdf import PdfReader
    lector = PdfReader(path)
    texto = "\n".join((pg.extract_text() or "") for pg in lector.pages)
    return texto.translate(_LIGADURAS), len(lector.pages)


# ------------------------------------------------------------ investigación
def investigar_comuna(comuna, forzar=False):
    """Snippets web sobre ventajas inmobiliarias de la comuna. -> [líneas]

    Cache en disco por INVEST_DIAS días (2 consultas DuckDuckGo por comuna).
    Sin internet devuelve [] — la ficha se arma igual con el brochure.
    """
    os.makedirs(INVEST, exist_ok=True)
    path = os.path.join(INVEST, slug(comuna) + ".json")
    if not forzar and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            caduca = (dt.date.fromisoformat(d["fecha"])
                      + dt.timedelta(days=INVEST_DIAS))
            if dt.date.today() < caduca:
                return d.get("lineas", [])
        except Exception:  # noqa: BLE001
            pass  # cache corrupto: re-investiga
    lineas, año = [], dt.date.today().year
    consultas = [
        f"ventajas de invertir en vivienda en {comuna} plusvalía "
        f"rentabilidad {año}",
        f"{comuna} proyectos inmobiliarios transporte infraestructura "
        f"mejoras",
    ]
    try:
        from ddgs import DDGS
        dd = DDGS()
    except Exception:  # noqa: BLE001 — paquete no instalado
        return lineas
    for q in consultas:
        try:
            for x in (dd.text(q, max_results=5) or []):
                titulo = (x.get("title") or "").strip()
                cuerpo = (x.get("body") or "").strip()
                url = (x.get("href") or "").strip()
                if titulo and cuerpo:
                    lineas.append(f"- {titulo}: {cuerpo} ({url})")
        except Exception:  # noqa: BLE001 — una consulta caída no anula la otra
            continue
    if not lineas:
        # sin resultados: NO cachear (fallo transitorio típico de ddgs)
        return ["(investigación web no disponible ahora: usa 'Re-analizar' "
                "más tarde para conseguir fuentes)"]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fecha": dt.date.today().isoformat(),
                       "lineas": lineas}, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    return lineas


# ------------------------------------------------------------------ análisis
def _datos_tabla(det, stock):
    """Tabla markdown de datos duros (sección 1 de la ficha)."""
    def uf(v):
        try:
            return f"{float(v):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return "—"
    filas = [
        ("Comuna", det.get("location") or "—"),
        ("Inmobiliaria", det.get("developer_name") or "—"),
        ("Desde", f"{uf(det.get('price_from_uf'))} UF"),
        ("Dormitorios", str(int(det.get("bedrooms") or 0))),
        ("Baños", str(int(det.get("bathrooms") or 0))),
        ("Superficie", f"{det.get('usable_area_m2') or '—'} m²"),
        ("Etapa", det.get("stage_label") or "—"),
        ("Entrega", det.get("expected_delivery_date")
         or {"immediate": "Inmediata", "future": "Futura"}
            .get(det.get("delivery_type"), det.get("delivery_type") or "—")),
        ("Promoción", det.get("active_promotion") or "Sin promoción vigente"),
        ("Reserva", f"${det.get('reservation_clp') or 0:,.0f}".replace(",", ".")
         if det.get("reservation_clp") else "—"),
        ("Publicado", det.get("publication_date") or "—"),
        ("Stock hoy", stock),
    ]
    return "| Campo | Valor |\n|---|---|\n" + "\n".join(
        f"| {k} | {v} |" for k, v in filas)


def analizar(claves, det, stock, brochure_txt, inv_lineas,
             modelo="qwen/qwen3.8-27b", reintentos=3):
    """Análisis del proyecto con brochure + investigación web. -> markdown

    Devuelve las secciones '## 2. Resumen del brochure',
    '## 3. Ventajas inmobiliarias' y '## 4. Cómo posicionarlo'.

    Ante 429 (límite de tokens de salida/min en Groq) espera 65 s y reintenta:
    una sincronización larga no debe morirse por la cuota de la tier gratis.
    """
    inv = ("\n".join(inv_lineas)
           or "(sin resultados de búsqueda web — apóyate solo en el brochure)")
    system = (
        "Eres analista inmobiliario senior de iproppi (Chile). Escribes "
        "fichas de proyectos para asesores: concretas, en español, sin "
        "inventar datos (todo lo que afirmes debe venir del brochure o de "
        "la investigación web). Máximo 5 viñetas por sección. Devuelve SOLO "
        "el markdown pedido, sin preámbulo ni cierre.")
    user = f"""PROYECTO: {det.get('name')} — {det.get('location')}
Inmobiliaria: {det.get('developer_name')} · Etapa: {det.get('stage_label')}
Stock actual: {stock}

BROCHURE (texto extraído del PDF; puede tener errores de saltos de línea):
{brochure_txt[:9000]}

INVESTIGACIÓN WEB sobre {det.get('location')}:
{inv[:2500]}

Escribe exactamente estas tres secciones:

## 2. Resumen del brochure
(qué ofrece el proyecto: tipología, metrajes, amenidades, hitos del plan de
pago — datos concretos del brochure)

## 3. Ventajas inmobiliarias
(4-5 viñetas con los datos de la INVESTIGACIÓN WEB: plusvalía de la comuna,
conectividad, proyectos públicos. OBLIGATORIO: cierra cada viñeta con su
fuente tal como aparece en la investigación, así: (fuente: https://…).
Prohibido agregar datos que no estén ni en el brochure ni en la
investigación: si la investigación dice "no disponible", limita la sección
a lo que el brochure respalde)

## 4. Cómo posicionarlo ante el cliente
(para qué perfil calza, cómo presentarlo, 1-2 objeciones previsibles y su
respuesta)"""
    mensajes = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    for intento in range(reintentos):
        try:
            return llm.completar(claves, mensajes, modelo=modelo,
                                 temperatura=0.3, max_tokens=1000)
        except llm.LLMError as e:
            if "429" in str(e) and intento < reintentos - 1:
                time.sleep(65)  # la cuota de Groq se libera por minuto
                continue
            raise
    raise llm.LLMError("Análisis abortado tras reintentos 429.")


def construir_ficha(det, docs, stock, brochure_txt, paginas, inv_lineas,
                    analisis_md, h):
    """Arma ficha.md completa (header + datos + análisis + documentos)."""
    hoy = dt.date.today().isoformat()
    pdf_url = ((det.get("presentation") or {}).get("file") or "")
    doc_lineas = []
    for d in docs or []:
        nombre = d.get("file_name") or d.get("title") or "documento"
        url = d.get("file") or ""
        doc_lineas.append(f"- {d.get('title') or nombre}: [PDF]({url})")
    documentos = "\n".join(doc_lineas) or "- *(sin documentos adicionales)*"
    return f"""# Proyecto: {det.get('name')}

**Sincronizado:** {hoy} · **Hash:** {h} · **ID portal:** {det.get('id')}

**Brochure PDF:** {pdf_url} · **Texto:** brochure.txt ({paginas} páginas)

## 1. Datos del portal

{_datos_tabla(det, stock)}

{analisis_md}

## 5. Documentos

- 📕 Brochure completo ({paginas} páginas) — texto en `brochure.txt`
{documentos}
"""


# ------------------------------------------------------------- sincronizar
def estado_stock(portal, pid):
    """-> '190/200 disponibles' consultando el portal (cache 60 s)."""
    try:
        from .iproppi_api import resumen_stock
        s = resumen_stock(portal.unidades(pid))
        return (f"{s['disponible']}/{s['total']} disponibles"
                + (f" · {s['reservada']} reservadas" if s['reservada'] else ""))
    except Exception:  # noqa: BLE001
        return "—"


def _analizar_uno(portal, alm, claves, p, progreso=None, inv_cache=None,
                  forzar=False):
    """Descarga y analiza UN proyecto nuevo/cambiado. -> carpeta slug"""
    pid = p["id"]
    carpeta = slug(p["name"])
    det = portal.proyecto(pid, forzar=True)
    docs = portal.documentos(pid)
    stock = estado_stock(portal, pid)
    pdf_url = (det.get("presentation") or {}).get("file") or ""
    brochure_txt, paginas = "", 0
    if pdf_url:
        try:
            path = descargar_brochure(pdf_url, pid, forzar=forzar)
            brochure_txt, paginas = texto_pdf(path)
        except Exception as e:  # noqa: BLE001 — sin PDF la ficha igual sale
            brochure_txt, paginas = f"({type(e).__name__}: sin texto)", 0
    if progreso:
        progreso(f"investigando {det.get('location')}…")
    comuna = det.get("location") or ""
    if not forzar and inv_cache is not None and comuna in inv_cache:
        inv_lineas = inv_cache[comuna]
    else:
        inv_lineas = investigar_comuna(comuna, forzar=forzar)
        if inv_cache is not None:
            inv_cache[comuna] = inv_lineas
    if claves:
        if progreso:
            progreso("analizando con IA…")
        analisis_md = analizar(claves, det, stock, brochure_txt, inv_lineas)
    else:
        analisis_md = ("## 2. Resumen del brochure\n*(sin GROQ_API_KEY: "
                       "análisis no generado)*\n\n## 3. Ventajas "
                       "inmobiliarias\n*(conecta Groq para generarla)*\n\n"
                       "## 4. Cómo posicionarlo ante el cliente\n"
                       "*(conecta Groq para generarla)*")
    h = hash_datos(p)
    ficha = construir_ficha(det, docs, stock, brochure_txt, paginas,
                            inv_lineas, analisis_md, h)
    alm.escribir(carpeta, ficha, f"proyecto: {det.get('name')} — análisis {h}")
    if brochure_txt and not brochure_txt.startswith("("):
        try:
            alm.escribir_archivo(carpeta, "brochure.txt", brochure_txt,
                                 f"brochure: {det.get('name')}")
        except Exception:  # noqa: BLE001 — lo bonito no tapa lo importante
            pass
    return carpeta


def sincronizar(portal, alm, claves, progreso=None, limite=None,
                solo_nuevos=False):
    """Compara el portal con las fichas guardadas y analiza lo nuevo.

    progreso(mensaje) opcional (para st.progress/status).
    limite: analiza solo los N primeros pendientes (para pruebas).
    solo_nuevos: ignora cambios de precio/etapa (solo altas).
    -> informe {'nuevos', 'actualizados', 'sin_cambios', 'errores', 'segundos'}
    """
    t0 = time.time()
    proyectos = [p for p in portal.proyectos(forzar=True)
                 if p.get("is_published")]
    carpetas = set(alm.listar())
    pendientes = []
    n_nuevos = n_cambiados = n_iguales = 0
    for p in proyectos:
        s = slug(p["name"])
        h = hash_datos(p)
        if s not in carpetas:
            pendientes.append((p, s, "nuevo"))
            n_nuevos += 1
        elif hash_ficha(alm.leer(s)) != h:
            n_cambiados += 1
            if not solo_nuevos:
                pendientes.append((p, s, "cambiado"))
        else:
            n_iguales += 1
    if limite:
        pendientes = pendientes[:limite]
    inv_cache = {}
    errores, total = [], len(pendientes)
    nuevos, cambiados = [], []
    for i, (p, s, tipo) in enumerate(pendientes, start=1):
        def progreso_msg(msg, i=i, p=p, total=total):
            if progreso:
                progreso(i, total, f"{p['name']}: {msg}")
        try:
            _analizar_uno(portal, alm, claves, p, progreso=progreso_msg,
                          inv_cache=inv_cache)
            (nuevos if tipo == "nuevo" else cambiados).append(p["name"])
        except Exception as e:  # noqa: BLE001 — un proyecto no frena al resto
            errores.append((p["name"], f"{type(e).__name__}: {e}"))
    return {
        "nuevos": nuevos,
        "actualizados": cambiados,
        "sin_cambios": n_iguales,
        "sin_analizar": n_cambiados - len(cambiados),  # solo_nuevos o límite
        "errores": errores,
        "segundos": round(time.time() - t0),
    }


def pendientes_de_sync(portal, alm):
    """-> (n_nuevos, n_cambiados) sin analizar — barato, para avisos."""
    try:
        proyectos = [p for p in portal.proyectos()
                     if p.get("is_published")]
        carpetas = set(alm.listar())
    except Exception:  # noqa: BLE001
        return 0, 0
    nuevos = sum(1 for p in proyectos if slug(p["name"]) not in carpetas)
    cambiados = 0
    for p in proyectos:
        s = slug(p["name"])
        if s in carpetas and hash_ficha(alm.leer(s)) != hash_datos(p):
            cambiados += 1
    return nuevos, cambiados


def reanalizar(portal, alm, claves, carpeta):
    """Regenera UNA ficha (botón 'Re-analizar'). -> bool"""
    for p in portal.proyectos():
        if slug(p["name"]) == carpeta:
            _analizar_uno(portal, alm, claves, p, forzar=True)
            return True
    return False


# ------------------------------------------------------------ contexto chat
def contexto_fichas(mensaje, alm, elegidos=None, catalogo=None, max_car=8000):
    """Fichas de proyectos mencionados o recomendados, para el system prompt.

    - mencionados: nombre del proyecto en el mensaje (tolerante a tildes).
    - elegidos: índices del catálogo de la última recomendación [[ELEGIDOS]].
    """
    try:
        carpetas = alm.listar()
    except Exception:  # noqa: BLE001
        return ""
    if not carpetas:
        return ""
    norm = re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize(
        "NFKD", mensaje or "").encode("ascii", "ignore").decode().lower())
    elegidas = []
    if catalogo and elegidos:
        for i in elegidos:
            if 1 <= i <= len(catalogo):
                s = slug(catalogo[i - 1].get("name", ""))
                if s in carpetas and s not in elegidas:
                    elegidas.append(s)
    mencionadas = []
    for c in carpetas:
        if c in elegidas:
            continue
        toks = [t for t in c.split("-") if len(t) >= 4]
        score = sum(1 for t in toks if t in norm)
        if score >= 2 or any(len(t) >= 7 and t in norm for t in toks):
            mencionadas.append((score, c))
    mencionadas.sort(reverse=True)
    elegidas = [c for _, c in mencionadas[:3]] + elegidas
    if not elegidas:
        return ""
    partes, presupuesto = [], max_car
    for c in elegidas[:4]:
        if presupuesto <= 500:
            break
        txt = alm.leer(c)
        if not txt:
            continue
        parte = txt[:presupuesto]
        partes.append(parte)
        presupuesto -= len(parte)
    if not partes:
        return ""
    return ("FICHAS DE PROYECTOS iproppi (fuente de verdad — respóndate en "
            "ellas):\n\n" + "\n\n---\n\n".join(partes))

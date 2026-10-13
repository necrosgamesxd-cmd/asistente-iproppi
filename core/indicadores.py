# -*- coding: utf-8 -*-
"""Indicadores en vivo (mindicador.cl, respaldo SII) + formato chileno.

Port de scripts/base.py de la skill `asistente-inmobiliario`, adaptado a la
nube: caché en memoria + /tmp (Community Cloud no tiene disco persistente).

Cadena de fuentes:
  1. mindicador.cl — tablero completo (uf, utm, dolar, tpm, ipc...)
  2. SII (www.sii.cl) — respaldo oficial de UF/UTM cuando mindicador cae.
"""
import datetime as dt
import json
import os
import re
import tempfile
import threading
import time
import urllib.request

API = "https://mindicador.cl/api"
SII_UF = "https://www.sii.cl/valores_y_fechas/uf/uf{anio}.htm"
SII_UTM = "https://www.sii.cl/valores_y_fechas/utm/utm{anio}.htm"
CACHE_DIR = os.path.join(tempfile.gettempdir(), "asistente-iproppi")

MESES_SII = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_bloqueo = threading.Lock()
_memoria: dict = {}  # clave -> (momento_iso, datos)
_mindicador_hasta = 0.0  # timestamp: si mindicador cayó, no reintentar hasta entonces


def _guardar(clave, data):
    """Escribe en memoria y, si el FS lo permite, en /tmp."""
    with _bloqueo:
        _memoria[clave] = (dt.date.today().isoformat(), data)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, clave), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass  # FS de solo lectura (nube): la memoria basta


def _apagar_mindicador(minutos=5):
    global _mindicador_hasta
    _mindicador_hasta = time.time() + minutos * 60


def _mindicador_fuera():
    return time.time() < _mindicador_hasta


def _http_json(url, timeout=8, reintentos=2):
    """GET JSON con reintentos (mindicador.cl a veces tarda o falla)."""
    req = urllib.request.Request(url, headers={"User-Agent": "asistente-iproppi/1.0"})
    ultimo = None
    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — reintentamos ante cualquier fallo de red
            ultimo = e
            if intento < reintentos - 1:
                time.sleep(1.0)
    raise ultimo


def _html(url, timeout=15):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 asistente-iproppi/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("latin-1", errors="replace")


def _leer_o_fetch(clave, fetch):
    """Caché a dos capas: memoria → /tmp → fuente."""
    hoy = dt.date.today().isoformat()
    with _bloqueo:
        guardado = _memoria.get(clave)
        if guardado and guardado[0] == hoy:
            return guardado[1]
    path = os.path.join(CACHE_DIR, clave)
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            with _bloqueo:
                _memoria[clave] = (hoy, data)
            return data
    except (OSError, ValueError):
        pass
    data = fetch()
    _guardar(clave, data)
    return data


# ------------------------------------------------------------------ SII (UF/UTM)
def _numero_cl(txt):
    """'41.130,94' -> 41130.94"""
    return float(txt.replace(".", "").replace(",", ".").strip())


def serie_sii(indicador, anio=None, refresh=False):
    """Serie diaria del SII para un año ('uf'|'utm') -> {'YYYY-MM-DD': float}."""
    anio = anio or dt.date.today().year
    clave = f"sii-{indicador}-{anio}.json"
    if refresh:
        _memoria.pop(clave, None)

    def fetch():
        html = _html((SII_UF if indicador == "uf" else SII_UTM).format(anio=anio))
        out = {}
        if indicador == "utm":
            # UTM: una fila por mes (sin decimales) -> expande a días del mes
            meses_en = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                        "Julio", "Agosto", "Septiembre", "Setiembre", "Octubre",
                        "Noviembre", "Diciembre"]
            patron = re.compile(
                r">\s*(" + "|".join(meses_en) + r")\s*</\w+>\s*"
                r"(?:<[^>]+>\s*)*<t[dh][^>]*>\s*([0-9.]+(?:,[0-9]+)?)\s*</t[dh]>",
                re.I)
            normalizar = {"setiembre": "septiembre"}
            for mes_txt, valor in patron.findall(html):
                mes = normalizar.get(mes_txt.lower(), mes_txt.lower())
                num = MESES_SII.index(mes) + 1
                ultimo = 31
                if num == 2:
                    ultimo = 28 if anio % 4 else 29
                elif num in (4, 6, 9, 11):
                    ultimo = 30
                for dia in range(1, ultimo + 1):
                    out[f"{anio}-{num:02d}-{dia:02d}"] = _numero_cl(valor)
        else:
            for mes in MESES_SII:
                i = html.find(f"id='mes_{mes}'")
                if i < 0:
                    i = html.find(f'id="mes_{mes}"')
                if i < 0:
                    continue
                bloque = html[i:i + 30000]
                fin = bloque.find("<div class='meses'")
                if fin > 0:
                    bloque = bloque[:fin]
                num = MESES_SII.index(mes) + 1
                for d, v in re.findall(
                        r"<th[^>]*>\s*<strong>(\d{1,2})\s*</strong>\s*</th>\s*"
                        r"<td[^>]*>\s*([0-9.]+,[0-9]{2})\s*</td>", bloque):
                    out[f"{anio}-{num:02d}-{int(d):02d}"] = _numero_cl(v)
        if not out:
            raise ValueError(f"SII: sin valores de {indicador} {anio}")
        return out

    return _leer_o_fetch(clave, fetch)


def _valor_hasta(indicador, fecha, refresh=False):
    """Último valor publicado por el SII <= fecha."""
    anio = int(fecha[:4])
    serie = serie_sii(indicador, anio, refresh)
    if fecha in serie:
        return serie[fecha]
    pasadas = sorted(d for d in serie if d <= fecha)
    if not pasadas:
        if anio > 2000:  # intenta con el año anterior
            serie = serie_sii(indicador, anio - 1, refresh)
            pasadas = sorted(d for d in serie if d <= fecha)
    if not pasadas:
        raise ValueError(f"SII: sin {indicador} para {fecha}")
    return serie[pasadas[-1]]


def uf_sii(fecha=None, refresh=False):
    """UF oficial según el SII (fecha YYYY-MM-DD o hoy)."""
    return _valor_hasta("uf", fecha or dt.date.today().isoformat(), refresh)


def utm_sii(fecha=None, refresh=False):
    """UTM oficial según el SII (fecha YYYY-MM-DD o hoy)."""
    return _valor_hasta("utm", fecha or dt.date.today().isoformat(), refresh)


# ------------------------------------------------------------- mindicador.cl
def _serie_mindicador(indicador, desde, hasta=None, refresh=False):
    clave = f"{indicador}-{desde}-{hasta or 'hoy'}.json"
    if refresh:
        _memoria.pop(clave, None)
    d = dt.date.fromisoformat(desde)

    def fetch():
        if _mindicador_fuera():
            raise ConnectionError("mindicador.cl en cooldown tras un fallo reciente")
        ddmm = f"{d.day:02d}-{d.month:02d}-{d.year}"
        try:
            data = _http_json(f"{API}/{indicador}/{ddmm}")
        except Exception:
            _apagar_mindicador()
            raise
        out = [
            {"fecha": p["fecha"], "valor": float(p["valor"])}
            for p in sorted(data.get("serie", []), key=lambda p: p["fecha"])
        ]
        if hasta:
            out = [p for p in out if p["fecha"][:10] <= hasta]
        return out

    return _leer_o_fetch(clave, fetch)


def serie(indicador, desde, hasta=None, refresh=False):
    """Serie histórica de cualquier indicador. UF/UTM tienen respaldo SII."""
    try:
        return _serie_mindicador(indicador, desde, hasta, refresh)
    except Exception:
        if indicador not in ("uf", "utm"):
            raise
        # Respaldo SII: arma la serie con las páginas de cada año cubierto.
        # Se cachea bajo la misma clave para no volver a golpear mindicador.
        clave = f"{indicador}-{desde}-{hasta or 'hoy'}.json"
        with _bloqueo:
            guardado = _memoria.get(clave)
            if guardado and guardado[0] == dt.date.today().isoformat():
                return guardado[1]
        fin = hasta or dt.date.today().isoformat()
        out = []
        for anio in range(int(desde[:4]), int(fin[:4]) + 1):
            try:
                s = serie_sii(indicador, anio, refresh)
            except Exception:
                continue
            out += [{"fecha": k, "valor": v} for k, v in sorted(s.items())
                    if desde <= k <= fin]
        if not out:
            raise
        _guardar(clave, out)
        return out


def serie_uf(desde, hasta=None, refresh=False):
    """Serie diaria de la UF. `desde`/`hasta` en YYYY-MM-DD."""
    return serie("uf", desde, hasta, refresh)


def get_indicadores(refresh=False):
    """Indicadores del día (cacheados por fecha).

    Fuente principal: mindicador.cl. Si está caído (cooldown de 5 min),
    devuelve tablero mínimo con UF/UTM del SII, cacheado igualmente.
    """
    global _mindicador_hasta
    hoy = dt.date.today().isoformat()
    clave = f"indicadores-{hoy}.json"
    if refresh:
        _mindicador_hasta = 0.0
        _memoria.pop(clave, None)
        try:
            os.remove(os.path.join(CACHE_DIR, clave))
        except OSError:
            pass
    try:
        def _fetch_tablero():
            if _mindicador_fuera():
                raise ConnectionError("mindicador.cl en cooldown tras un fallo reciente")
            try:
                return _http_json(API)
            except Exception:
                _apagar_mindicador()
                raise

        return _leer_o_fetch(clave, _fetch_tablero)
    except Exception as first:
        out = {"fecha": hoy, "fuente": "SII (respaldo: mindicador.cl no responde)"}
        try:
            out["uf"] = {"codigo": "UF", "nombre": "UF", "unidad": "Pesos",
                         "fecha": hoy, "valor": round(uf_sii(hoy), 4)}
        except Exception:
            raise first  # sin UF no hay app: reporta el error original
        try:
            out["utm"] = {"codigo": "UTM", "nombre": "UTM", "unidad": "Pesos",
                          "fecha": hoy, "valor": round(utm_sii(hoy), 2)}
        except Exception:
            pass  # UTM secundaria
        _guardar(clave, out)  # cachea el respaldo también (refresh lo fuerza)
        return out


def get_uf(refresh=False):
    """Valor de la UF vigente (pesos)."""
    try:
        return float(get_indicadores(refresh)["uf"]["valor"])
    except Exception:
        return uf_sii(refresh=refresh)


def get_uf_fecha(fecha, refresh=False):
    """Valor de la UF en una fecha YYYY-MM-DD."""
    puntos = serie_uf(desde=fecha, refresh=refresh)
    objetivo = dt.date.fromisoformat(fecha)
    mejor = None
    for punto in puntos:
        d = dt.date.fromisoformat(punto["fecha"][:10])
        if d <= objetivo:
            mejor = punto
        else:
            break
    return float((mejor or puntos[0])["valor"])


# ------------------------------------------------------------------- formato
def miles(n, dec=0):
    """1234567.5 -> '1.234.568' (separador de miles chileno)."""
    if dec == 0:
        s = f"{round(n):,.0f}"
    else:
        s = f"{n:,.{dec}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def clp(pesos, dec=0):
    """Pesos chilenos: 41081.76 -> '$41.082'."""
    signo = "-" if pesos < 0 else ""
    return f"{signo}${miles(abs(pesos), dec)}"


def _num(x):
    """Convierte a float tolerando strings numéricos; si no es número, devuelve None.

    - Números se pasan tal cual.
    - Strings: se trata el punto como decimal (formato del portal, ej. '2721.000')
      y la coma como decimal chilena. Los miles se infieren por longitud si no
      hay separador (ej. '2847' -> 2847.0, no 2.847.000).
    """
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("UF", "").replace("$", "").strip()
    if not s:
        return None
    try:
        if "," in s:      # coma decimal chilena: 2.804,5 -> 2804.5
            return float(s.replace(".", "").replace(",", "."))
        if "." in s:      # punto decimal: 2721.000 -> 2721.0
            return float(s)
        return float(s)   # sin separador: '2847' -> 2847.0
    except (TypeError, ValueError):
        return None


def uf(monto_uf, dec=0):
    """UF: 2804.23 -> '2.804 UF'. Acepta números o strings numéricos."""
    monto_uf = _num(monto_uf)
    if monto_uf is None:
        return "—"
    signo = "-" if monto_uf < 0 else ""
    return f"{signo}{miles(abs(monto_uf), dec)} UF"


def pct(valor, dec=1):
    return f"{miles(valor, dec)}%"


MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_larga(iso):
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


# ------------------------------------------------------------------ tablero
TABLERO = [
    ("uf", "UF", "money", 2),
    ("utm", "UTM", "money", 0),
    ("dolar", "Dólar observado", "money", 0),
    ("euro", "Euro", "money", 0),
    ("tpm", "TPM", "pct", 2),
    ("ipc", "IPC", "pct", 2),
    ("ivp", "IVP", "money", 2),
    ("imacec", "Imacec", "pct", 2),
    ("tasa_desempleo", "Desempleo", "pct", 2),
    ("libra_cobre", "Libra de cobre", "cobre", 2),
]


def tablero(refresh=False):
    """-> [(clave, etiqueta, valor_formateado, fecha_extra|None, disponible)]"""
    data = get_indicadores(refresh)
    out = []
    for clave, etiqueta, tipo, dec in TABLERO:
        item = data.get(clave)
        if not item:
            out.append((clave, etiqueta, "—", None, False))
            continue
        valor = float(item["valor"])
        if tipo == "money":
            texto = clp(valor, dec)
        elif tipo == "pct":
            texto = pct(valor, dec)
        else:
            texto = f"US$ {miles(valor, dec)}"
        fecha_item = item.get("fecha")
        extra = (fecha_larga(fecha_item)
                 if fecha_item and fecha_item[:10] != data.get("fecha", "")[:10]
                 else None)
        out.append((clave, etiqueta, texto, extra, True))
    return out, data.get("fuente")

# -*- coding: utf-8 -*-
"""Fichas de clientes: plantilla, parseo y almacenamiento (local o GitHub).

La ficha.md sigue siendo la fuente de verdad (mismo formato que la skill
`asistente-inmobiliario`). El almacenamiento es intercambiable:

  - AlmacenLocal  → carpeta en disco (uso local, sin nube)
  - AlmacenGitHub → repo privado vía Contents API (Streamlit Community Cloud)

Estructura en el repo:
    clientes/
    ├── clientes/                       ← carpeta raíz de fichas
    │   └── Nombre Apellido/
    │       ├── ficha.md
    │       └── transcripciones/2026-09-29.md
"""
import base64
import datetime as dt
import re
import unicodedata

import requests

# ------------------------------------------------------------------ helpers
def plano(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def limpiar(valor):
    v = valor.replace("**", "").replace("*", "").replace("`", "").replace("__", "")
    return re.sub(r"\s+", " ", v).strip()


def una_linea(txt, n=220):
    limpio = re.sub(r"\s+", " ", re.sub(r"[*#>|`]", " ", txt or "")).strip()
    limpio = re.sub(r"^\d+[.)]\s*", "", limpio)
    return limpio[:n] + ("…" if len(limpio) > n else "")


def plantilla(nombre, hoy):
    return f"""# Ficha: {nombre}

**Creada:** {hoy} · **Última actualización:** {hoy} · **Estado:** En seguimiento

## 1. Datos personales

| Campo | Dato |
|---|---|
| Nombre completo | {nombre} |
| Estado | En seguimiento |
| RUT | |
| Teléfono | |
| Correo | |
| Fecha de nacimiento | |
| Nacionalidad | |
| Estado civil | |
| Profesión | |
| Dirección actual | |
| Cómo llegó | |

## 2. Perfil financiero (escáner)

| Campo | Dato |
|---|---|
| Renta líquida | |
| Otros ingresos | |
| Ahorro para pie | |
| Capacidad de ahorro | |
| Deudas | |
| Dicom | |
| Capacidad calculada (UF) | |

## 3. Qué busca

| Campo | Dato |
|---|---|
| Comunas objetivo | |
| Tipo de propiedad | |
| Presupuesto / capacidad | |
| Proyecto favorito | |
| Multicrédito | |
| Próxima reunión | |
| Última reunión | |

### Resumen / qué busca

*(una o dos líneas con lo que el cliente realmente quiere)*

## 4. Historial de reuniones

### {hoy} — Nombre de la reunión

- **Qué se vio:**
- **Proyectos mostrados:**
- **Acuerdos:**
- **Mis compromisos:**
- **Próxima reunión:**

## 5. Cómo abordar la próxima reunión

1. *(con qué abrir)*
2. *(qué número llevar calculado)*
3. *(qué cerrar / cuál es el objetivo de esa reunión)*

## 6. Notas y contexto

*(tono del cliente, objeciones, datos personales relevantes)*
"""


# -------------------------------------------------------------------- parseo
def parsear(texto):
    """-> (datos de las tablas '| Campo | Dato |', resumen de 'Qué busca')."""
    datos, busca, en_busca = {}, [], False
    for ln in (texto or "").splitlines():
        if ln.startswith("#"):
            enc = ln.lstrip("#").strip().lower()
            en_busca = "que busca" in enc or "qué busca" in enc
            continue
        m = re.match(r"^\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", ln)
        if m:
            clave, valor = m.group(1).strip(), m.group(2).strip()
            if clave.lower() in ("campo", "dato", "valor") or set(clave) <= set("-: "):
                continue
            if valor and set(valor) != {"-"}:
                datos[clave] = limpiar(valor)
        elif en_busca and ln.strip():
            t = ln.strip()
            if t.startswith("*(") or t.startswith("("):
                continue
            busca.append(t)
    if texto:
        m = re.search(r"\*\*Estado:\*\*\s*([^\n]+)", texto)
        if m and "estado" not in {k.lower() for k in datos}:
            datos["Estado"] = limpiar(m.group(1))
    return datos, " ".join(busca)


def historial(texto):
    """-> [(fecha, titulo, cuerpo)] de los '### YYYY-MM-DD — ...'."""
    partes = re.split(r"^###\s+", texto or "", flags=re.M)
    out = []
    for p in partes:
        lineas = p.splitlines()
        if not lineas:
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})\s*[—\-–]\s*(.*)", lineas[0].strip())
        if m:
            out.append((m.group(1), m.group(2).strip(), "\n".join(lineas[1:]).strip()))
    return out


def resumen(nombre_carpeta, texto):
    """Fila de índice (claves alineadas con las columnas del Excel)."""
    d, busca = parsear(texto)
    hist = historial(texto)
    ultima = d.get("Última reunión") or (hist[-1][0] if hist else "")
    return {
        "nombre": d.get("Nombre completo", nombre_carpeta),
        "estado": d.get("Estado", ""),
        "Teléfono": d.get("Teléfono", ""),
        "Correo": d.get("Correo", ""),
        "Renta líquida": d.get("Renta líquida", ""),
        "Capacidad de ahorro": d.get("Capacidad de ahorro", ""),
        "Capacidad calculada (UF)": d.get("Capacidad calculada (UF)", ""),
        "Comunas objetivo": d.get("Comunas objetivo", ""),
        "Tipo de propiedad": d.get("Tipo de propiedad", ""),
        "Proyecto favorito": d.get("Proyecto favorito", ""),
        "Próxima reunión": d.get("Próxima reunión", ""),
        "última": ultima,
        "busca": una_linea(busca),
        "carpeta": nombre_carpeta,
    }


def encontrar(nombre, opciones):
    """Busca en la lista de carpetas tolerando mayúsculas, tildes y palabras."""
    objetivo = plano(nombre)
    for c in opciones:
        pc = plano(c)
        if objetivo in pc or pc in objetivo:
            return c
    for c in opciones:
        pc = plano(c)
        if all(p and p in pc for p in objetivo.split()):
            return c
    return None


# --------------------------------------------------------------- almacén base
class AlmacenError(Exception):
    def __init__(self, mensaje, conflicto=False):
        super().__init__(mensaje)
        self.conflicto = conflicto


class Almacen:
    """Interfaz: listar, leer, escribir, transcribir."""

    RAIZ = "clientes"

    def listar(self):
        """-> [nombre_carpeta]"""
        raise NotImplementedError

    def leer(self, carpeta):
        """-> texto de ficha.md o None."""
        raise NotImplementedError

    def leer_meta(self, carpeta):
        """-> (texto, sha) — el sha permite detectar conflictos al guardar."""
        return self.leer(carpeta), None

    def escribir(self, carpeta, texto, mensaje, sha_esperado=None, forzar=False):
        """Guarda ficha.md. Devuelve {'ok', 'sha'|None, 'conflicto'?}."""
        raise NotImplementedError

    def transcribir(self, carpeta, fecha, texto, titulo=""):
        raise NotImplementedError

    def raiz(self):
        return self.RAIZ


# ------------------------------------------------------------ almacén local
import os  # noqa: E402


class AlmacenLocal(Almacen):
    def __init__(self, raiz=None):
        self.base = raiz or os.environ.get("CLIENTES_DIR",
                                            os.path.expanduser("~/clientes"))

    def _dir(self, carpeta):
        return os.path.join(self.base, carpeta)

    def listar(self):
        if not os.path.isdir(self.base):
            return []
        return sorted(d for d in os.listdir(self.base)
                      if os.path.isdir(os.path.join(self.base, d))
                      and not d.startswith("."))

    def leer(self, carpeta):
        path = os.path.join(self._dir(carpeta), "ficha.md")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return f.read()

    def escribir(self, carpeta, texto, mensaje, sha_esperado=None, forzar=False):
        os.makedirs(self._dir(carpeta), exist_ok=True)
        path = os.path.join(self._dir(carpeta), "ficha.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(texto)
        return {"ok": True, "sha": None}

    def transcribir(self, carpeta, fecha, texto, titulo=""):
        sub = os.path.join(self._dir(carpeta), "transcripciones")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, f"{fecha}.md"), "w", encoding="utf-8") as f:
            f.write(f"# Transcripción {fecha} — {carpeta}\n\n"
                    + (f"**{titulo}**\n\n" if titulo else "") + texto)
        return {"ok": True}


# ------------------------------------------------------------ almacén GitHub
class AlmacenGitHub(Almacen):
    """Repo privado vía GitHub Contents API (PAT con scope repo)."""
    API = "https://api.github.com"

    def __init__(self, repo, pat):
        if not repo or not pat:
            raise AlmacenError("Falta GITHUB_REPO o GITHUB_PAT en los secrets.")
        self.repo = repo
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _url(self, path):
        return f"{self.API}/repos/{self.repo}/contents/{path}"

    def _metodo(self, metodo, path, **kw):
        try:
            r = self.s.request(metodo, self._url(path), timeout=30, **kw)
        except requests.RequestException as e:
            raise AlmacenError(f"Sin respuesta de GitHub ({e.__class__.__name__}).")
        return r

    def listar(self):
        r = self._metodo("GET", self.RAIZ)
        if r.status_code == 404:
            return []
        if not r.ok:
            raise AlmacenError(f"GitHub listar: HTTP {r.status_code} {r.text[:120]}")
        return sorted(e["name"] for e in r.json()
                      if e["type"] == "dir" and not e["name"].startswith("."))

    def _obtener(self, path):
        r = self._metodo("GET", path)
        if r.status_code == 404:
            return None, None
        if not r.ok:
            raise AlmacenError(f"GitHub leer: HTTP {r.status_code} {r.text[:120]}")
        d = r.json()
        contenido = base64.b64decode(d["content"]).decode("utf-8")
        return contenido, d["sha"]

    def leer(self, carpeta):
        texto, _ = self._obtener(f"{self.RAIZ}/{carpeta}/ficha.md")
        return texto

    def leer_meta(self, carpeta):
        return self._obtener(f"{self.RAIZ}/{carpeta}/ficha.md")

    def escribir(self, carpeta, texto, mensaje, sha_esperado=None, forzar=False):
        """PUT con detección de conflictos (sha).

        sha_esperado: el sha que se leyó al abrir la ficha (None si es nueva).
        forzar=True: pisa sin avisar.
        """
        path = f"{self.RAIZ}/{carpeta}/ficha.md"
        _, sha_actual = self._obtener(path)
        if (not forzar and sha_esperado is not None
                and sha_actual is not None and sha_actual != sha_esperado):
            _, sha_actual = self._obtener(path)  # doble check por carrera
            if sha_actual != sha_esperado:
                return {"ok": False, "conflicto": True, "sha_remoto": sha_actual}
        payload = {
            "message": mensaje,
            "content": base64.b64encode(texto.encode("utf-8")).decode("ascii"),
        }
        if sha_actual:
            payload["sha"] = sha_actual
        r = self._metodo("PUT", path, json=payload)
        if r.status_code == 409:
            return {"ok": False, "conflicto": True}
        if not r.ok:
            raise AlmacenError(f"GitHub guardar: HTTP {r.status_code} {r.text[:160]}")
        return {"ok": True, "sha": r.json().get("content", {}).get("sha")}

    def transcribir(self, carpeta, fecha, texto, titulo=""):
        path = f"{self.RAIZ}/{carpeta}/transcripciones/{fecha}.md"
        contenido = (f"# Transcripción {fecha} — {carpeta}\n\n"
                     + (f"**{titulo}**\n\n" if titulo else "") + texto)
        _, sha = self._obtener(path)
        payload = {
            "message": f"transcripción: {carpeta} {fecha}",
            "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        r = self._metodo("PUT", path, json=payload)
        if not r.ok:
            raise AlmacenError(f"GitHub transcripción: HTTP {r.status_code}")
        return {"ok": True}


# ------------------------------------------------------------------ fábrica
def almacen_desde_secrets(secrets):
    """Elige almacén: GitHub si hay secrets, si no, local."""
    repo = (secrets or {}).get("GITHUB_REPO")
    pat = (secrets or {}).get("GITHUB_PAT")
    if repo and pat:
        return AlmacenGitHub(repo, pat)
    return AlmacenLocal()


def fecha_hoy():
    return dt.date.today().isoformat()

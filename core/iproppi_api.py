# -*- coding: utf-8 -*-
"""Cliente de la API del portal iproppi (soybroker-api-iproppi.onrender.com).

Autenticación JWT (rol broker, token pegado manualmente en la app).
Endpoints verificados el 2026-10-12 con credenciales reales.

Nota: Render free tier se "duerme" tras inactividad — el primer llamado
puede tardar hasta ~50 s (hay reintentos con espera).
"""
import base64
import datetime as dt
import json
import time

import requests

BASE = "https://soybroker-api-iproppi.onrender.com"

_cache: dict = {}  # (path, params) -> (timestamp, datos)
TTL_CORTO = 60      # listas que cambian (stock, quotes)
TTL_LARGO = 600     # datos relativamente estáticos (locations, developers)


class PortalError(Exception):
    """Error de la API del portal (401 token, 403 permisos, red...)."""

    def __init__(self, mensaje, status=None):
        super().__init__(mensaje)
        self.status = status


def _limpiar_cache():
    ahora = time.time()
    for k in [k for k, (t, _) in _cache.items() if ahora - t > TTL_LARGO]:
        _cache.pop(k, None)


def decodificar_jwt(token):
    """Decodifica el payload de un JWT (sin verificar firma). -> dict | None"""
    try:
        cuerpo = token.split(".")[1]
        cuerpo += "=" * (-len(cuerpo) % 4)
        return json.loads(base64.urlsafe_b64decode(cuerpo))
    except Exception:  # noqa: BLE001
        return None


def clasificar_token(token):
    """-> ('access'|'refresh'|None, payload) según el tipo de JWT."""
    datos = decodificar_jwt(token)
    if not datos:
        return None, None
    return datos.get("token_type"), datos


def intercambiar_refresh(refresh_token):
    """POST /auth/token/refresh/ -> access token nuevo."""
    try:
        r = requests.post(f"{BASE}/auth/token/refresh/",
                          json={"refresh": refresh_token}, timeout=40)
    except requests.RequestException as e:
        raise PortalError(f"Sin respuesta del portal: {e.__class__.__name__}.")
    if r.status_code == 401:
        raise PortalError("El refresh token venció: pega uno nuevo "
                          "(30 días de vigencia).", 401)
    if not r.ok:
        raise PortalError(f"Refresh falló (HTTP {r.status_code}).", r.status_code)
    return r.json()["access"]


class Portal:
    def __init__(self, token=None, refresh_token=None):
        self.token = token
        self.refresh_token = refresh_token

    # ------------------------------------------------------------ transporte
    def _request(self, metodo, path, params=None, json=None, con_token=True,
                 reintentos=2, timeout=70):
        url = path if path.startswith("http") else f"{BASE}{path}"
        headers = {"Content-Type": "application/json"}
        if con_token:
            if not self.token:
                raise PortalError("Sin token del portal: pégalo en la barra lateral.")
            headers["Authorization"] = f"Bearer {self.token}"
        ultimo = None
        for intento in range(reintentos):
            try:
                r = requests.request(metodo, url, params=params, json=json,
                                     headers=headers, timeout=timeout)
            except requests.RequestException as e:
                ultimo = PortalError(f"Sin respuesta del portal ({e.__class__.__name__}). "
                                     f"Render puede estar despertando: reintenta.")
                time.sleep(3)
                continue
            if r.status_code == 401:
                raise PortalError("Token expirado o inválido: pega uno nuevo "
                                  "(60 min de vigencia).", 401)
            if r.status_code == 403:
                raise PortalError("El rol broker no tiene acceso a esto (403).", 403)
            if r.status_code >= 500:
                ultimo = PortalError(f"El portal respondió {r.status_code}: reintenta.",
                                     r.status_code)
                time.sleep(3)
                continue
            if not r.ok:
                detalle = r.text[:200]
                try:
                    detalle = str(r.json().get("detail", detalle))
                except ValueError:
                    pass
                raise PortalError(f"HTTP {r.status_code}: {detalle}", r.status_code)
            try:
                return r.json()
            except ValueError:
                raise PortalError("Respuesta no-JSON del portal.", r.status_code)
        raise ultimo or PortalError("El portal no respondió.")

    def _get_cache(self, path, params=None, ttl=TTL_CORTO, forzar=False):
        _limpiar_cache()
        clave = (path, tuple(sorted((params or {}).items())))
        ahora = time.time()
        hit = _cache.get(clave)
        if hit and not forzar and ahora - hit[0] <= ttl:
            return hit[1]
        datos = self._request("GET", path, params=params)
        _cache[clave] = (ahora, datos)
        return datos

    def invalidar(self):
        _cache.clear()

    # ------------------------------------------------------------ autenticación
    @staticmethod
    def login(email, password):
        try:
            r = requests.post(f"{BASE}/auth/token/",
                              json={"email": email, "password": password},
                              timeout=40)
        except requests.RequestException as e:
            raise PortalError(f"Sin respuesta del portal: {e.__class__.__name__}.")
        if not r.ok:
            detalle = "credenciales inválidas"
            try:
                detalle = r.json().get("detail", detalle)
            except ValueError:
                pass
            raise PortalError(f"Login falló ({r.status_code}): {detalle}", r.status_code)
        return r.json()  # {refresh, access}

    def quien_soy(self):
        return self._request("GET", "/auth/me/")

    # ------------------------------------------------------------------ datos
    def proyectos(self, forzar=False):
        d = self._get_cache("/apartments/projects/", ttl=TTL_CORTO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def proyecto(self, pid, forzar=False):
        return self._get_cache(f"/apartments/projects/{pid}/", ttl=TTL_LARGO,
                               forzar=forzar)

    def ubicaciones(self, forzar=False):
        d = self._get_cache("/apartments/projects/locations/", ttl=TTL_LARGO,
                            forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def unidades(self, pid, forzar=False):
        d = self._get_cache("/incentives/units/", params={"project": pid},
                            ttl=TTL_CORTO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def listas_precios(self, pid, forzar=False):
        d = self._get_cache("/incentives/unit-price-lists/", params={"project": pid},
                            ttl=TTL_LARGO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def fases_pago(self, pid, forzar=False):
        d = self._get_cache(f"/apartments/projects/{pid}/payment-phases/",
                            ttl=TTL_LARGO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def documentos(self, pid, forzar=False):
        d = self._get_cache(f"/apartments/projects/{pid}/documents/",
                            ttl=TTL_LARGO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def incentivos(self, forzar=False):
        d = self._get_cache("/incentives/incentives/", ttl=TTL_LARGO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def cotizaciones(self, forzar=False):
        d = self._get_cache("/apartments/quotes/", ttl=TTL_CORTO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def clientes_portal(self, forzar=False):
        d = self._get_cache("/apartments/clients/", ttl=TTL_CORTO, forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def reservaciones(self, forzar=False):
        d = self._get_cache("/apartments/reservations/", ttl=TTL_CORTO,
                            forzar=forzar)
        return d if isinstance(d, list) else d.get("results", [])

    def uf_oficial(self, fecha=None, forzar=False):
        """UF oficial (fuente SII) según el portal. -> float"""
        params = {"date": fecha} if fecha else None
        d = self._get_cache("/incentives/uf-rates/by-date/", params=params,
                            ttl=TTL_LARGO, forzar=forzar)
        return float(d["value_clp"])


def resumen_stock(unidades):
    """-> {'total': n, 'disponible': n, 'reservada': n, por_tipo: {tipo: [disp, total]}}"""
    out = {"total": len(unidades), "disponible": 0, "reservada": 0, "por_tipo": {}}
    for u in unidades:
        estado = (u.get("status") or "").upper()
        tipo = u.get("unit_type") or "?"
        fila = out["por_tipo"].setdefault(tipo, {"disponible": 0, "total": 0})
        fila["total"] += 1
        if estado == "AVAILABLE":
            out["disponible"] += 1
            fila["disponible"] += 1
        elif estado == "RESERVED":
            out["reservada"] += 1
    return out


def hoy_iso():
    return dt.date.today().isoformat()

# -*- coding: utf-8 -*-
"""Utilidades de UI compartidas (sidebar del portal, métricas, errores)."""
import datetime as dt

import streamlit as st

from . import iproppi_api
from .iproppi_api import Portal, PortalError


def _secrets():
    try:
        return st.secrets  # object-like; getitem lanza si no existe
    except Exception:  # noqa: BLE001
        return {}


def _secret(clave):
    try:
        return st.secrets.get(clave)
    except Exception:  # noqa: BLE001
        return None


def sidebar_portal():
    """Sidebar: pegar token del portal (access o refresh). -> Portal | None

    El portal solo persiste `advisor_refresh_token` (30 días) en localStorage;
    si pegan ese, la app lo intercambia por access (60 min) automáticamente.
    """
    with st.sidebar:
        st.markdown("🔑 **Portal iproppi**")
        token = st.text_input("Token JWT", value="", type="password",
                              key="campo_token",
                              help="ventas.iproppi.com → F12 → Application → "
                                   "Local Storage → advisor_refresh_token "
                                   "(30 días) o un access token (60 min)")

        if st.button("Conectar", width="stretch",
                     disabled=not token.strip()):
            pegado = token.strip()
            tipo, payload = iproppi_api.clasificar_token(pegado)
            try:
                if tipo == "refresh":
                    access = iproppi_api.intercambiar_refresh(pegado)
                    st.session_state["portal_refresh"] = pegado
                elif tipo == "access":
                    access = pegado
                    st.session_state.pop("portal_refresh", None)
                else:
                    raise iproppi_api.PortalError(
                        "Token inválido: debe ser el JWT de advisor_refresh_token "
                        "o un access token.")
                st.session_state["portal_token"] = access
                portal = Portal(token=access)
                st.session_state["portal_quien"] = portal.quien_soy()
                st.session_state.pop("portal_error", None)
            except iproppi_api.PortalError as e:
                st.session_state.pop("portal_quien", None)
                st.session_state["portal_error"] = str(e)
            st.rerun()

        quien = st.session_state.get("portal_quien")
        if quien:
            exp = iproppi_api.decodificar_jwt(
                st.session_state.get("portal_token", "") or "")
            vigencia = ""
            if exp and exp.get("exp"):
                min_ = int((exp["exp"] - dt.datetime.now(dt.timezone.utc)
                            .timestamp()) // 60)
                vigencia = f" · vence en {min_} min"
            st.success(f"✅ {quien['first_name']} {quien['last_name']} "
                       f"({quien['role']}){vigencia}")
            if st.button("Desconectar", width="stretch"):
                for k in ("portal_token", "portal_refresh", "portal_quien"):
                    st.session_state.pop(k, None)
                st.rerun()
        elif st.session_state.get("portal_error"):
            st.error(st.session_state["portal_error"][:200])

    if st.session_state.get("portal_quien"):
        # ¿access a punto de vencer? Renovar con el refresh si lo hay.
        portal = Portal(token=st.session_state.get("portal_token"),
                        refresh_token=st.session_state.get("portal_refresh"))
        payload = iproppi_api.decodificar_jwt(st.session_state.get("portal_token", ""))
        if payload and payload.get("exp"):
            restan = payload["exp"] - dt.datetime.now(dt.timezone.utc).timestamp()
            if restan < 60 and st.session_state.get("portal_refresh"):
                try:
                    portal.token = iproppi_api.intercambiar_refresh(
                        st.session_state["portal_refresh"])
                    st.session_state["portal_token"] = portal.token
                except iproppi_api.PortalError:
                    pass  # se avisará en el siguiente 401
        return portal
    return None


def almacen():
    """Almacén de fichas (GitHub si hay secrets, si no local)."""
    from .fichas import almacen_desde_secrets
    if "almacen" not in st.session_state:
        st.session_state["almacen"] = almacen_desde_secrets(_secrets())
    return st.session_state["almacen"]


def error_ui(e, extra=""):
    if isinstance(e, PortalError):
        st.error(f"🌐 {e}")
    else:
        st.error(f"⚠️ {type(e).__name__}: {e}")
    if extra:
        st.caption(extra)


def tarjeta(valor, etiqueta, delta=None):
    st.metric(etiqueta, valor, delta)

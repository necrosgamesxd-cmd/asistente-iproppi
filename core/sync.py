# -*- coding: utf-8 -*-
"""Estado de sincronización con GitHub para la UI de Streamlit.

Modelo: cada página llama a `marcar_cambio()` al editar y `guardar_ahora()`
al pulsar "💾 Guardar en GitHub"; con auto-sync activado, guardar_ahora se
ejecuta solo tras cada edición exitosa. La barra lateral muestra el estado.
"""
import datetime as dt

import streamlit as st

CLAVE_PENDIENTES = "sync_pendientes"      # {ruta_clave: (carpeta, texto, mensaje)}
CLAVE_ULTIMO = "sync_ultimo"              # "15:32:01 ✓" o error
CLAVE_ERROR = "sync_error"
CLAVE_AUTO = "sync_auto"


def _init():
    st.session_state.setdefault(CLAVE_PENDIENTES, {})
    st.session_state.setdefault(CLAVE_ULTIMO, None)
    st.session_state.setdefault(CLAVE_ERROR, None)
    st.session_state.setdefault(CLAVE_AUTO, True)


def auto_sync():
    _init()
    return st.session_state[CLAVE_AUTO]


def pendientes():
    _init()
    return st.session_state[CLAVE_PENDIENTES]


def marcar_cambio(almacen, carpeta, texto, mensaje, sha_esperado=None):
    """Deja la ficha en cola (o la guarda ya mismo si auto-sync)."""
    _init()
    st.session_state[CLAVE_PENDIENTES][f"ficha:{carpeta}"] = (
        carpeta, texto, mensaje, sha_esperado)
    st.session_state[CLAVE_ERROR] = None
    if auto_sync():
        return guardar_ahora(almacen)
    return None


def guardar_ahora(almacen, forzar_todo=False):
    """Escribe en el almacén todo lo pendiente. -> {'ok':n, 'errores':[...]}"""
    _init()
    pend = st.session_state[CLAVE_PENDIENTES]
    if not pend:
        return {"ok": 0, "errores": [], "vacio": True}
    ok, errores = 0, []
    for clave in list(pend.keys()):
        carpeta, texto, mensaje, sha = pend[clave]
        try:
            res = almacen.escribir(carpeta, texto, mensaje,
                                   sha_esperado=sha, forzar=forzar_todo)
            if res.get("conflicto"):
                errores.append(f"{carpeta}: conflicto — alguien más la modificó "
                               f"(usa Forzar para pisarla)")
                continue
            if res.get("ok"):
                ok += 1
                pend.pop(clave, None)
        except Exception as e:  # noqa: BLE001 — mostramos el error en la UI
            errores.append(f"{carpeta}: {e}")
    if ok and not errores:
        st.session_state[CLAVE_ULTIMO] = dt.datetime.now().strftime("%H:%M:%S")
        st.session_state[CLAVE_ERROR] = None
    if errores:
        st.session_state[CLAVE_ERROR] = " | ".join(errores)
    return {"ok": ok, "errores": errores}


def barra_lateral(almacen, contexto=""):
    """Renderiza el estado de sincronización en la sidebar."""
    _init()
    st.sidebar.markdown("---")
    st.sidebar.caption("🔄 GitHub")
    n = len(pendientes())
    if n:
        st.sidebar.warning(f"⚠️ {n} cambio(s) sin guardar", icon="⚠️")
    elif st.session_state[CLAVE_ULTIMO]:
        st.sidebar.caption(f"🟢 Sincronizado — {st.session_state[CLAVE_ULTIMO]}")
    else:
        st.sidebar.caption("🟢 Sin cambios pendientes")
    if st.session_state[CLAVE_ERROR]:
        st.sidebar.error(st.session_state[CLAVE_ERROR][:300])

    auto = st.sidebar.toggle("Auto-guardar", value=auto_sync(), key="toggle_auto",
                             help="Guarda en GitHub tras cada edición")
    st.session_state[CLAVE_AUTO] = auto

    if n:
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("💾 Guardar", width="stretch"):
                res = guardar_ahora(almacen)
                if res["ok"]:
                    st.rerun()
                else:
                    st.toast("Errores al guardar (ver barra lateral)")
        with col2:
            if st.button("Force", width="stretch", help="Pisa conflictos"):
                guardar_ahora(almacen, forzar_todo=True)
                st.rerun()
    if contexto:
        st.sidebar.caption(contexto)


def guardar_ficha_ui(almacen, carpeta, texto, resumen_txt="", sha_esperado=None):
    """Botón grande de guardar (para usar en la página de ficha)."""
    mensaje = (f"ficha: {carpeta} — {resumen_txt} " if resumen_txt else f"ficha: {carpeta} ")
    mensaje += dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    marcar_cambio(almacen, carpeta, texto, mensaje, sha_esperado=sha_esperado)
    if auto_sync():
        res = guardar_ahora(almacen)
        if res.get("vacio"):
            return True
        if res["ok"]:
            return True
        return False
    return None  # en cola

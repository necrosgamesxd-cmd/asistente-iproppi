# -*- coding: utf-8 -*-
"""🏠 Asistente Inmobiliario — portada."""
import streamlit as st

from core import cifras
from core import indicadores as ind
from core import sync
from core.ui import almacen, sidebar_portal

st.set_page_config(page_title="Asistente Inmobiliario", page_icon="🏠",
                   layout="wide")

st.title("🏠 Asistente Inmobiliario — iproppi")

portal = sidebar_portal()
sync.barra_lateral(almacen())
st.session_state.setdefault("sync_auto", True)

# ------------------------------------------------------------------ indicadores
st.subheader("📊 Indicadores de hoy")
try:
    tab, fuente = ind.tablero()
    cols = st.columns(5)
    visibles = [(c, e, t, x, d) for c, e, t, x, d in tab if d]
    for i, (clave, etiqueta, texto, extra, _) in enumerate(visibles):
        with cols[i % 5]:
            st.metric(etiqueta, texto, extra)
    if fuente:
        st.caption(f"ℹ️ Fuente: {fuente}")
except Exception as e:  # noqa: BLE001
    st.error(f"No pude cargar indicadores: {e}")

# ------------------------------------------------------------- cifras iproppi
col1, col2 = st.columns([3, 2])
with col1:
    st.subheader("🏢 Cifras de respaldo iproppi")
    st.info(cifras.FRASE_10_SEGUNDOS)
    for nombre, valor, cuando in cifras.CIFRAS:
        st.markdown(f"- **{nombre}:** {valor} — *{cuando}*")
    with st.expander("🔄 Flujo de la compra (40 segundos)"):
        for i, (paso, detalle) in enumerate(cifras.FLUJO_COMPRA, start=1):
            st.markdown(f"{i}. **{paso}**{(' — ' + detalle) if detalle else ''}")
    with st.expander("⚠️ Errores detectados en evaluaciones (no repetir)"):
        for e in cifras.ERRORES:
            st.markdown(f"- {e}")

with col2:
    st.subheader("🧭 Ir a")
    st.page_link("pages/1_📊_Indicadores.py", label="📊 Indicadores y conversores",
                 icon="📊")
    st.page_link("pages/2_💰_Escáner_y_Cuota.py",
                 label="💰 Escáner de capacidad + Cuota", icon="💰")
    st.page_link("pages/3_📈_Proyección.py",
                 label="📈 Proyección y costo de esperar", icon="📈")
    st.page_link("pages/4_👥_Clientes.py", label="👥 Clientes (fichas + Excel)",
                 icon="👥")
    st.page_link("pages/5_🏢_Portal_iproppi.py",
                 label="🏢 Portal iproppi (stock y precios)", icon="🏢")
    st.page_link("pages/6_🗓️_Preparar_Reunión.py",
                 label="🗓️ Preparar la próxima reunión", icon="🗓️")
    st.page_link("pages/7_💬_Chat.py", label="💬 Chat con el asistente", icon="💬")

    if portal:
        try:
            proys = portal.proyectos()
            st.success(f"Portal conectado: **{len(proys)} proyectos**")
        except Exception as e:  # noqa: BLE001
            st.warning(str(e))
    else:
        st.warning("Pega el token del portal en la barra lateral para activar "
                   "la página **Portal iproppi**.")

st.caption("Los cálculos replican la skill `asistente-inmobiliario` — mismas "
           "fórmulas, mismos números. Fuentes: mindicador.cl / SII / API iproppi.")

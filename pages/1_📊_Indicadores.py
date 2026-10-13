# -*- coding: utf-8 -*-
"""📊 Indicadores y conversores (mindicador.cl / SII)."""
import datetime as dt

import streamlit as st

from core import indicadores as ind
from core import sync
from core.ui import almacen

st.set_page_config(page_title="Indicadores", page_icon="📊", layout="wide")
st.title("📊 Indicadores del día")
sync.barra_lateral(almacen())

colA, colB = st.columns([4, 1])
with colB:
    if st.button("🔄 Actualizar", help="Ignora la caché del día"):
        ind.get_indicadores(refresh=True)
        st.rerun()

# ------------------------------------------------------------------ tablero
try:
    tab, fuente = ind.tablero()
except Exception as e:  # noqa: BLE001
    st.error(f"No pude cargar los indicadores: {e}")
    st.stop()

cols = st.columns(5)
for i, (clave, etiqueta, texto, extra, disp) in enumerate(tab):
    with cols[i % 5]:
        if disp:
            st.metric(etiqueta, texto, extra)
        else:
            st.metric(etiqueta, "—", help="No disponible (fuente caída)")
if fuente:
    st.warning(f"⚠️ {fuente} — UF y UTM son oficiales (SII). Los demás indicadores "
               f"volverán cuando mindicador.cl responda (reintenta en unos minutos).")

st.markdown(f"**Fecha:** {ind.fecha_larga(ind.get_indicadores()['fecha'])}")

st.divider()

# --------------------------------------------------------------- conversores
st.subheader("🔁 Conversores")
c1, c2 = st.columns(2)
with c1:
    st.markdown("#### UF → pesos")
    n_uf = st.number_input("UF", min_value=0.0, value=1000.0, step=50.0,
                           key="conv_uf")
    if st.button("Convertir UF → $", key="b1"):
        st.session_state["r_uf"] = True
    if st.session_state.get("r_uf"):
        st.success(f"**{ind.uf(n_uf, 2)} = {ind.clp(n_uf * ind.get_uf(), 0)}**")
with c2:
    st.markdown("#### pesos → UF")
    pesos = st.number_input("Pesos", min_value=0, value=1_000_000, step=50_000,
                            key="conv_pesos")
    if st.button("Convertir $ → UF", key="b2"):
        st.session_state["r_pesos"] = True
    if st.session_state.get("r_pesos"):
        st.success(f"**{ind.clp(pesos)} = {ind.uf(pesos / ind.get_uf(), 2)}**")

st.divider()

# -------------------------------------------------------------- variaciones
st.subheader("📈 Variación histórica")
c1, c2, c3 = st.columns([2, 2, 2])
indicador = c1.selectbox("Indicador", ["uf", "utm", "dolar", "euro", "tpm", "ipc"],
                         format_func=str.upper)
desde = c2.date_input("Desde", value=dt.date(dt.date.today().year - 1, 1, 1),
                      max_value=dt.date.today())
if c3.button("Calcular variación"):
    try:
        puntos = ind.serie(indicador, desde.isoformat())
        if len(puntos) > 1:
            var = (puntos[-1]["valor"] / puntos[0]["valor"] - 1) * 100
            ratio = puntos[-1]["valor"] / puntos[0]["valor"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Inicio", f"{puntos[0]['valor']:,.2f}".replace(",", "@")
                      .replace(".", ",").replace("@", "."),
                      ind.fecha_larga(puntos[0]["fecha"]))
            m2.metric("Hoy", f"{puntos[-1]['valor']:,.2f}".replace(",", "@")
                      .replace(".", ",").replace("@", "."),
                      ind.fecha_larga(puntos[-1]["fecha"]))
            m3.metric("Variación", ind.pct(var), f"×{ratio:.3f}")
            st.caption(f"{len(puntos)} días de serie.")
        else:
            st.info("Serie muy corta para comparar.")
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude calcular la serie: {e}")

# ------------------------------------------------------------------ UF oficial
st.divider()
st.subheader("🏛️ UF oficial (SII)")
c1, c2 = st.columns(2)
with c1:
    fecha = st.date_input("Fecha", value=dt.date.today(), key="uf_fecha",
                          max_value=dt.date.today() + dt.timedelta(days=365))
    if st.button("Ver UF del SII"):
        try:
            st.info(f"UF al {ind.fecha_larga(fecha.isoformat())}: "
                    f"**{ind.clp(ind.uf_sii(fecha.isoformat()), 2)}** (fuente SII)")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
with c2:
    try:
        st.caption(f"UF hoy (SII): {ind.clp(ind.uf_sii(), 2)} · "
                   f"UTM hoy (SII): {ind.clp(ind.utm_sii(), 0)}")
    except Exception:  # noqa: BLE001
        pass

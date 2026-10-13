# -*- coding: utf-8 -*-
"""📈 Proyección de valorización y costo de esperar."""
import datetime as dt

import streamlit as st

from core import indicadores as ind
from core import proyeccion as proy_mod
from core import sync
from core.ui import almacen

st.set_page_config(page_title="Proyección", page_icon="📈", layout="wide")
st.title("📈 Proyección y costo de esperar")
sync.barra_lateral(almacen())

c = st.columns(5)
precio = c[0].number_input("Precio hoy (UF)", min_value=100.0, value=3500.0,
                           step=50.0)
anio = c[1].number_input("Año objetivo", min_value=dt.date.today().year + 1,
                         max_value=dt.date.today().year + 30,
                         value=dt.date.today().year + 4, step=1)
valorizacion = c[2].number_input("Valorización anual (%)", min_value=0.0,
                                 value=4.7, step=0.1,
                                 help="Referencia histórica: 4,7 % anual en UF")
ipc = c[3].number_input("IPC anual (%)", min_value=0.0, value=3.0, step=0.1,
                        help="Para proyectar la UF en pesos")
arriendo = c[4].number_input("Arriendo actual (CLP/mes)", min_value=0, value=0,
                             step=50_000)

c2 = st.columns(3)
cuota = c2[0].number_input("Dividendo futuro (CLP/mes)", min_value=0, value=0,
                           step=50_000)
historico = c2[1].toggle("Comparar con la UF real histórica", value=True)

if st.button("📈 Calcular proyección", type="primary"):
    try:
        p = proy_mod.calcular(precio=precio, anio=int(anio),
                              valorizacion=valorizacion, ipc=ipc,
                              arriendo=arriendo or None, cuota=cuota or None,
                              historico=historico)
        st.session_state["proy_resultado"] = p
    except Exception as e:  # noqa: BLE001
        st.error(str(e))

p = st.session_state.get("proy_resultado")
if p:
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Precio hoy", ind.uf(p["precio_hoy"]),
              ind.clp(p["precio_hoy_pesos"]))
    m2.metric(f"Precio en {p['anio']}", ind.uf(p["precio_futuro"]),
              ind.clp(p["precio_futuro_pesos"]))
    m3.metric("Ganancia patrimonial", ind.uf(p["ganancia_uf"]),
              ind.clp(p["ganancia_pesos"]))
    m4.metric("UF proyectada", ind.clp(p["uf_futura"], 2),
              f"desde {ind.clp(p['uf_hoy'], 2)}")

    st.caption(f"Valorización {ind.pct(p['valorizacion'])} anual en UF · "
               f"IPC {ind.pct(p['ipc'])} · UF al {ind.fecha_larga(p['uf_fecha'])}")

    esp = p.get("esperar")
    if esp:
        st.subheader("⏳ Costo de esperar")
        if "arriendo_total" in esp:
            st.error(f"Arriendo pagado en {p['anios']} años: "
                     f"**{ind.clp(esp['arriendo_total'])}** "
                     f"({ind.clp(esp['arriendo_mes'])}/mes) — plata que no es suya")
        if "cuota_total" in esp:
            st.info(f"Dividendo pagado en ese plazo: **{ind.clp(esp['cuota_total'])}** "
                    f"— construye patrimonio propio")
        if "resumen" in esp:
            st.warning(f"📌 {esp['resumen']}")

    hist = p.get("historico")
    if hist:
        st.subheader("📉 Variación real de la UF")
        st.write(f"De **{ind.clp(hist['desde_valor'], 2)}** "
                 f"({ind.fecha_larga(hist['desde'])}) a "
                 f"**{ind.clp(hist['hasta_valor'], 2)}** "
                 f"({ind.fecha_larga(hist['hasta'])}) = "
                 f"**{ind.pct(hist['variacion'])}** en {hist['dias']} días")
        st.caption(hist["frase"])

    st.divider()
    st.success(f"💬 *\"{p['frase']}\"*")
    if p.get("frase_arriendo"):
        st.info(f"💬 *\"{p['frase_arriendo']}\"*")

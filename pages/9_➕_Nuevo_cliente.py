# -*- coding: utf-8 -*-
"""➕ Nuevo cliente — formulario de alta (ficha financiera iproppi).

Réplica funcional de ficha_financiera_cliente.html: mismas 6 secciones,
mismos cálculos (financiamiento = renta × 60 ÷ UF, × 1,2) y al guardar se
crea la ficha.md del cliente en el almacén (local o GitHub).
"""
import datetime as dt

import pandas as pd
import streamlit as st

from core import capacidad
from core import fichas
from core import indicadores as ind
from core import sync
from core.ui import almacen

st.set_page_config(page_title="Nuevo cliente", page_icon="➕", layout="wide")
st.title("➕ Nuevo cliente — ficha financiera")
store = almacen()
sync.barra_lateral(store)


def _clp(v):
    return "$" + f"{int(round(v)):,}".replace(",", ".")


def _uf(v, dec=1):
    return f"{v:,.{dec}f}".replace(",", ".") + " UF"


def _tabla_md(df, cols, headers):
    lineas = ["|" + "|".join(headers) + "|",
              "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, fila in df.iterrows():
        celdas = []
        for c in cols:
            v = fila[c]
            if isinstance(v, float) and v == int(v):
                v = int(v)
            celdas.append(str(v) if str(v).strip() else "—")
        lineas.append("| " + " | ".join(celdas) + " |")
    return "\n".join(lineas)


# --------------------------------------------------------------- 01 datos
with st.container(border=True):
    st.markdown("### 01 · Datos del cliente")
    c1, c2 = st.columns(2)
    nombre = c1.text_input("Nombre completo *", key="nc_nombre")
    telefono = c1.text_input("Teléfono", key="nc_tel")
    correo = c1.text_input("Correo", key="nc_correo")
    rut = c1.text_input("RUT", key="nc_rut")
    estado_civil = c2.text_input("Estado civil", key="nc_civil")
    profesion = c2.text_input("Profesión", key="nc_prof")
    direccion = st.text_input("Dirección", key="nc_dir")

# ------------------------------------------------------------- 02 ingresos
with st.container(border=True):
    st.markdown("### 02 · Ingresos y renta")
    st.caption("Montos mensuales del cliente.")
    try:
        uf_default = int(round(ind.get_uf()))
    except Exception:  # noqa: BLE001 — sin indicadores: valor de referencia
        uf_default = 41000
    cc = st.columns(4)
    renta = cc[0].number_input("Renta ($)", min_value=0, step=10000,
                               key="nc_renta")
    boleta = cc[1].number_input("Boleta ($)", min_value=0, step=10000,
                                key="nc_boleta")
    pensiones = cc[2].number_input("Pensiones ($)", min_value=0, step=10000,
                                   key="nc_pensiones")
    arriendos = cc[3].number_input("Arriendos ($)", min_value=0, step=10000,
                                   key="nc_arriendos")
    valor_uf = st.number_input("Valor UF ($)", min_value=1000,
                               value=uf_default, step=1, key="nc_uf")
    financiamiento = (renta * 60) / valor_uf       # lógica del Excel/HTML
    propiedad = financiamiento * 1.2
    st.metric("💰 Propiedad estimada (solo con renta)", _uf(propiedad, 0))
    st.caption(f"Cálculo: (renta × 60) ÷ valor UF = {_uf(financiamiento, 0)} "
               f"de financiamiento (80%) · × 1,2 → valor total estimado.")

# ------------------------------------------------------------- 03 capacidad
with st.container(border=True):
    st.markdown("### 03 · Capacidad de inversión")
    st.caption("Recursos disponibles declarados por el cliente.")
    cd = st.columns(2)
    ahorro = cd[0].number_input("Ahorro para pie ($)", min_value=0,
                                step=10000, key="nc_ahorro")
    cam = cd[1].number_input("CAM ($)", min_value=0, step=10000,
                             key="nc_cam")

# --------------------------------------------------------------- 04 deudas
with st.container(border=True):
    st.markdown("### 04 · Deudas vigentes")
    st.caption("Obligaciones actuales del cliente.")
    deudas = st.data_editor(
        pd.DataFrame([{"Tipo deuda": "", "Institución": "", "Cuota ($)": 0,
                       "Total ($)": 0, "Nº cuotas": 0}]),
        num_rows="dynamic", key="nc_deudas", width="stretch",
        column_config={
            "Tipo deuda": st.column_config.TextColumn("Tipo deuda"),
            "Institución": st.column_config.TextColumn("Institución"),
            "Cuota ($)": st.column_config.NumberColumn("Cuota ($)",
                                                       min_value=0, format="$%d"),
            "Total ($)": st.column_config.NumberColumn("Total ($)",
                                                       min_value=0, format="$%d"),
            "Nº cuotas": st.column_config.NumberColumn("Nº cuotas",
                                                       min_value=0, format="%d"),
        })
    deudas = deudas[(deudas["Tipo deuda"].astype(str).str.strip() != "")
                    | (deudas["Cuota ($)"] > 0)]
    total_cuotas = float(deudas["Cuota ($)"].sum()) if len(deudas) else 0.0
    st.metric("Carga mensual por deudas", _clp(total_cuotas))

# --------------------------------------------------------------- 05 activos
with st.container(border=True):
    st.markdown("### 05 · Activos")
    activos = st.data_editor(
        pd.DataFrame([{"Tipo de activo": "", "Valor activo ($)": 0}]),
        num_rows="dynamic", key="nc_activos", width="stretch",
        column_config={
            "Tipo de activo": st.column_config.TextColumn("Tipo de activo"),
            "Valor activo ($)": st.column_config.NumberColumn(
                "Valor activo ($)", min_value=0, format="$%d"),
        })
    activos = activos[(activos["Tipo de activo"].astype(str).str.strip() != "")
                      | (activos["Valor activo ($)"] > 0)]
    total_activos = (float(activos["Valor activo ($)"].sum())
                     if len(activos) else 0.0)
    st.metric("Total activos", _clp(total_activos))

# --------------------------------------------------------------- 06 cuentas
with st.container(border=True):
    st.markdown("### 06 · Cuentas")
    st.caption("Cuentas e instituciones informadas.")
    cuentas = st.data_editor(
        pd.DataFrame([{"Tipo de cuenta": "", "Institución": ""}]),
        num_rows="dynamic", key="nc_cuentas", width="stretch",
        column_config={
            "Tipo de cuenta": st.column_config.TextColumn("Tipo de cuenta"),
            "Institución": st.column_config.TextColumn("Institución"),
        })
    cuentas = cuentas[cuentas["Tipo de cuenta"].astype(str).str.strip() != ""]

# ------------------------------------------------------- resumen y escáner
st.divider()
otros = boleta + pensiones + arriendos
neto, cap_uf = capacidad.capacidad_uf(
    renta=renta, dividendos=otros, deudas=total_cuotas, valor_uf=valor_uf)
pie = ahorro + cam
r1, r2, r3, r4 = st.columns(4)
r1.metric("Ingreso neto", _clp(neto))
r2.metric("Capacidad de crédito (escáner)", _uf(cap_uf, 0),
          f"con {len(deudas)} deuda(s)")
r3.metric("Pie disponible", _clp(pie))
r4.metric("Propiedad estimada (Excel)", _uf(propiedad, 0))
st.caption(f"Escáner: (ingreso neto × 60) ÷ UF × 1,2 · "
           f"fórmula Excel: (renta × 60) ÷ UF × 1,2")

# ------------------------------------------------------------------ guardar
st.divider()
if st.button("💾 Crear ficha del cliente", type="primary",
             disabled=not nombre.strip()):
    nombre = nombre.strip()
    try:
        existentes = store.listar()
    except Exception:  # noqa: BLE001
        existentes = []
    if nombre in existentes:
        st.warning(f"Ya existe una ficha llamada «{nombre}».")
    else:
        hoy = dt.date.today().isoformat()
        campos = {
            "Teléfono": telefono, "Correo": correo, "RUT": rut,
            "Estado civil": estado_civil, "Profesión": profesion,
            "Dirección actual": direccion,
            "Renta líquida": _clp(renta),
            "Otros ingresos": _clp(otros) if otros else "",
            "Ahorro para pie": _clp(ahorro) if ahorro else "",
            "Capacidad de ahorro": _clp(cam) if cam else "",
            "Deudas": (_clp(total_cuotas) + " de carga mensual")
                      if total_cuotas else "",
            "Capacidad calculada (UF)": _uf(cap_uf, 0),
        }
        detalle = [
            f"**Valor UF usado:** {_clp(valor_uf)} · "
            f"**Financiamiento (Excel):** (renta × 60) ÷ UF × 1,2",
            "",
            "### Ingresos",
            "| Ingreso | Monto |", "|---|---|",
            f"| Renta | {_clp(renta)} |",
            f"| Boleta | {_clp(boleta)} |",
            f"| Pensiones | {_clp(pensiones)} |",
            f"| Arriendos | {_clp(arriendos)} |",
            f"| **Ingreso neto (− deudas)** | **{_clp(neto)}** |",
            "",
            "### Cálculos",
            "| Cálculo | Valor |", "|---|---|",
            f"| Financiamiento estimado (solo renta) | {_uf(financiamiento, 0)} |",
            f"| Propiedad estimada (Excel) | {_uf(propiedad, 0)} |",
            f"| Capacidad escáner (con deudas) | {_uf(cap_uf, 0)} |",
            f"| Pie disponible (ahorro + CAM) | {_clp(pie)} |",
            f"| Carga mensual por deudas | {_clp(total_cuotas)} |",
            f"| Total activos | {_clp(total_activos)} |",
        ]
        if len(deudas):
            detalle += ["", "### Deudas vigentes",
                        _tabla_md(deudas,
                                  ["Tipo deuda", "Institución", "Cuota ($)",
                                   "Total ($)", "Nº cuotas"],
                                  ["Tipo", "Institución", "Cuota", "Total",
                                   "Cuotas"])]
        if len(activos):
            detalle += ["", "### Activos",
                        _tabla_md(activos, ["Tipo de activo",
                                            "Valor activo ($)"],
                                  ["Tipo", "Valor"])]
        if len(cuentas):
            detalle += ["", "### Cuentas",
                        _tabla_md(cuentas, ["Tipo de cuenta", "Institución"],
                                  ["Tipo", "Institución"])]
        ficha_txt = fichas.ficha_financiera(
            nombre, hoy, campos, "\n".join(detalle))
        res = store.escribir(nombre, ficha_txt,
                             f"ficha: {nombre} — alta con formulario "
                             f"financiero ({hoy})")
        if res.get("ok") or res.get("sha") is None:
            st.session_state.pop("clientes_cache", None)
            st.session_state["cliente_activo"] = nombre
            st.success(f"✅ Ficha creada: {nombre} "
                       f"(capacidad {_uf(cap_uf, 0)})")
            try:
                st.page_link("pages/4_👥_Clientes.py",
                             label="Abrir la ficha del cliente →",
                             icon="👥")
            except Exception:  # noqa: BLE001 — fuera del app multipágina
                st.caption("Abre la ficha en 👥 Clientes")
        else:
            st.error("⚠️ No se guardó — revisa la barra lateral")

st.caption("Los mismos números del escáner (página 2) y de la ficha: "
           "editar después puede hacerse en 👥 Clientes → ✏️ Editar.")

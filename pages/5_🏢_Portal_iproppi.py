# -*- coding: utf-8 -*-
"""🏢 Portal iproppi: proyectos, stock, precios y planes de pago."""
import streamlit as st

from core import indicadores as ind
from core import iproppi_api as api
from core import sync
from core.ui import almacen, error_ui, sidebar_portal

st.set_page_config(page_title="Portal iproppi", page_icon="🏢", layout="wide")
st.title("🏢 Portal iproppi — proyectos y stock")
sync.barra_lateral(almacen())

portal = sidebar_portal()

if not portal:
    st.info("🔑 **Conéctate al portal** con tu token JWT en la barra lateral "
            "(esquina inferior izquierda).")
    with st.expander("¿Cómo obtener el token?"):
        st.markdown("""
1. Entra a [ventas.iproppi.com](https://ventas.iproppi.com/) e inicia sesión.
2. Pulsa **F12** → pestaña **Application** → **Local Storage** → `ventas.iproppi.com`.
3. Copia el valor de la clave **`advisor_refresh_token`** (dura **30 días**).
4. Pégalo en el campo **Token JWT** de la barra lateral y presiona **Conectar**.

*La app lo intercambia por un access token (60 min) y lo renueva sola; cuando
el refresh venza, repite el proceso (cada 30 días).*""")
    st.stop()

# ------------------------------------------------------------------ proyectos
try:
    proys = portal.proyectos()
except api.PortalError as e:
    error_ui(e, "Render free tier puede estar durmiendo: espera ~50 s y reintenta.")
    st.stop()
except Exception as e:  # noqa: BLE001
    error_ui(e)
    st.stop()

st.caption(f"{len(proys)} proyectos · UF oficial portal: "
           f"**{ind.clp(portal.uf_oficial(), 2)}**")

c = st.columns([2, 2, 1])
ubicaciones = sorted({p.get("location") or "—" for p in proys})
filtro_loc = c[0].selectbox("Comuna", ["Todas"] + ubicaciones)
filtro_txt = c[1].text_input("Buscar nombre", key="filtro_proy")
solo_pub = c[2].toggle("Solo publicados", value=True)

filtrados = []
for p in proys:
    if filtro_loc != "Todas" and p.get("location") != filtro_loc:
        continue
    if filtro_txt and filtro_txt.lower() not in (p.get("name") or "").lower():
        continue
    if solo_pub and not p.get("is_published"):
        continue
    filtrados.append(p)

st.dataframe(
    [{"Proyecto": p.get("name"),
      "Comuna": p.get("location"),
      "Inmobiliaria": p.get("developer_name"),
      "Desde (UF)": ind.uf(p["price_from_uf"], 0) if p.get("price_from_uf") else "—",
      "Promoción": (p.get("active_promotion") or {}).get("name", "")
                   if isinstance(p.get("active_promotion"), dict)
                   else (p.get("active_promotion") or ""),
      "Entrega": p.get("stage_label") or p.get("delivery_type") or "",
      "Publicado": "✅" if p.get("is_published") else "—"}
     for p in filtrados],
    hide_index=True, width="stretch")

if not filtrados:
    st.stop()

# ------------------------------------------------------------------- detalle
st.divider()
nombres = [p["name"] for p in filtrados]
sel = st.selectbox("Ver detalle de proyecto", nombres)
proy = next(p for p in filtrados if p["name"] == sel)
pid = proy["id"]

with st.spinner("Cargando detalle…"):
    try:
        unidades = portal.unidades(pid)
        fases = portal.fases_pago(pid)
        docs = portal.documentos(pid)
        detalle = portal.proyecto(pid)
    except Exception as e:  # noqa: BLE001
        error_ui(e)
        st.stop()

stock = api.resumen_stock(unidades)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Proyecto", proy["name"])
m2.metric("Unidades", stock["total"])
m3.metric("Disponibles", stock["disponible"])
m4.metric("Reservadas", stock["reservada"])
m5.metric("Desde", ind.uf(proy.get("price_from_uf") or 0, 0))

if detalle.get("image_url"):
    st.image(detalle["image_url"], width=420)
if detalle.get("presentation"):
    with st.expander("Presentación"):
        st.write(detalle["presentation"])

# por tipo
if stock["por_tipo"]:
    st.subheader("Stock por tipo de unidad")
    st.dataframe(
        [{"Tipo": t, "Disponibles": v["disponible"], "Total": v["total"]}
         for t, v in stock["por_tipo"].items()],
        hide_index=True, width="stretch")

# unidades
st.subheader("Unidades")
import pandas as pd  # noqa: E402

df = pd.DataFrame([{
    "Código": u.get("code"),
    "Tipo": u.get("unit_type"),
    "Precio lista (UF)": ind.uf(float(u.get("list_price_uf") or 0), 0),
    "Estado": {"AVAILABLE": "✅ Disponible", "RESERVED": "🔒 Reservada"}
              .get((u.get("status") or "").upper(), u.get("status")),
} for u in unidades])
st.dataframe(df, hide_index=True, width="stretch")

# fases de pago
if fases:
    st.subheader("💳 Fases de pago")
    for f in fases:
        extras = []
        if f.get("max_installments"):
            extras.append(f"hasta {f['max_installments']} cuotas")
        st.write(f"- **{f.get('name')}**"
                 + (f" ({', '.join(extras)})" if extras else "")
                 + (f" — {f.get('variant_label')}" if f.get("variant_label") else ""))

# documentos
if docs:
    st.subheader("📄 Documentos")
    for d in docs:
        url = d.get("view_url") or d.get("file")
        st.markdown(f"- [{d.get('title') or d.get('file_name')}]({url})")

# ------------------------------------------------------------------- preparar
st.divider()
if st.button("🗓️ Usar este proyecto en Preparar reunión", type="primary"):
    st.session_state["proyecto_reunion"] = {"id": pid, "name": proy["name"],
                                             "precio": proy.get("price_from_uf")}
    st.switch_page("pages/6_🗓️_Preparar_Reunión.py")

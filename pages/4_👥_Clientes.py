# -*- coding: utf-8 -*-
"""👥 Clientes: fichas, transcripciones e índice Excel."""
import datetime as dt
import io

import streamlit as st

from core import excel as excel_mod
from core import fichas
from core import sync
from core.ui import almacen

st.set_page_config(page_title="Clientes", page_icon="👥", layout="wide")
st.title("👥 Clientes — fichas")
store = almacen()
sync.barra_lateral(store,
                   f"Almacén: {'GitHub (' + store.raiz() + ')' if isinstance(store, fichas.AlmacenGitHub) else 'local'}")


def listar_clientes():
    cache = st.session_state.get("clientes_cache")
    if cache and st.session_state.get("clientes_cache_ts", 0) > dt.datetime.now().timestamp() - 30:
        return cache
    try:
        nombres = store.listar()
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude listar los clientes: {e}")
        return []
    st.session_state["clientes_cache"] = nombres
    st.session_state["clientes_cache_ts"] = dt.datetime.now().timestamp()
    return nombres


nombres = listar_clientes()

# ---------------------------------------------------------------- nueva ficha
with st.expander("➕ Nuevo cliente", expanded=not nombres):
    nuevo = st.text_input("Nombre completo", key="nuevo_nombre")
    if st.button("Crear ficha", disabled=not nuevo.strip()):
        if nuevo in nombres:
            st.warning("Ya existe.")
        else:
            hoy = fichas.fecha_hoy()
            res = store.escribir(nuevo.strip(), fichas.plantilla(nuevo.strip(), hoy),
                                 f"ficha: {nuevo.strip()} — creada {hoy}")
            if res.get("ok") or res.get("sha") is None:
                st.session_state.pop("clientes_cache", None)
                st.session_state["cliente_activo"] = nuevo.strip()
                st.success(f"Ficha creada: {nuevo.strip()}")
                st.rerun()

if not nombres:
    st.info("Aún no hay clientes. Crea el primero con el formulario de arriba.")
    st.stop()

# -------------------------------------------------------------------- listing
col_sel, col_xlsx = st.columns([3, 1])
with col_sel:
    cliente = st.selectbox("Cliente", nombres,
                           index=(nombres.index(st.session_state["cliente_activo"])
                                  if st.session_state.get("cliente_activo") in nombres
                                  else 0),
                           key="selector_cliente")
    st.session_state["cliente_activo"] = cliente
with col_xlsx:
    st.write("")
    st.write("")
    if st.button("🔄 Refrescar lista"):
        st.session_state.pop("clientes_cache", None)
        st.rerun()

# ------------------------------------------------------------------- índice xlsx
try:
    filas = []
    for n in nombres:
        texto = store.leer(n)
        if texto:
            filas.append(fichas.resumen(n, texto))
    datos_xlsx = excel_mod.construir(filas)
    st.download_button("⬇️ Descargar clientes.xlsx", data=datos_xlsx,
                       file_name="clientes.xlsx",
                       mime="application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet")
except Exception as e:  # noqa: BLE001
    st.warning(f"Índice Excel no disponible: {e}")

st.divider()

# --------------------------------------------------------------------- ficha
texto, sha_leida = store.leer_meta(cliente)
if texto is None:
    st.error(f"No encontré ficha.md de {cliente}.")
    st.stop()

datos, busca = fichas.parsear(texto)
hist = fichas.historial(texto)

tab_ficha, tab_editar, tab_trans, tab_hist = st.tabs(
    ["👁️ Ver", "✏️ Editar", "🎙️ Transcripción", "📅 Historial"])

with tab_ficha:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 1. Datos personales")
        for k in ("Nombre completo", "Estado", "RUT", "Teléfono", "Correo",
                  "Profesión", "Estado civil"):
            if datos.get(k):
                st.write(f"**{k}:** {datos[k]}")
        st.markdown("#### 2. Perfil financiero")
        for k in ("Renta líquida", "Ahorro para pie", "Capacidad de ahorro",
                  "Deudas", "Dicom", "Capacidad calculada (UF)"):
            if datos.get(k):
                st.write(f"**{k}:** {datos[k]}")
    with c2:
        st.markdown("#### 3. Qué busca")
        for k in ("Comunas objetivo", "Tipo de propiedad",
                  "Presupuesto / capacidad", "Proyecto favorito",
                  "Próxima reunión", "Última reunión"):
            if datos.get(k):
                st.write(f"**{k}:** {datos[k]}")
        if busca:
            st.markdown(f"**Resumen:** {busca}")
    st.divider()
    st.markdown("#### 5. Cómo abordar la próxima reunión")
    en5 = False
    for ln in texto.splitlines():
        if ln.startswith("## 5"):
            en5 = True
            continue
        if en5 and ln.startswith("## "):
            break
        if en5 and ln.strip():
            st.markdown(ln)

with tab_editar:
    st.caption("Edita el markdown directamente. Los cambios se guardan con el "
               "botón (o automáticamente si el auto-guardar está activo).")
    nuevo_texto = st.text_area("ficha.md", value=texto, height=520)
    b1, b2 = st.columns([1, 3])
    with b1:
        if st.button("💾 Guardar en GitHub", type="primary",
                     disabled=(nuevo_texto == texto)):
            ok = sync.guardar_ficha_ui(store, cliente, nuevo_texto,
                                       "edición manual", sha_esperado=sha_leida)
            if ok:
                st.success("✅ Guardado")
                st.rerun()
            elif ok is None:
                st.info("📝 En cola de guardado (auto-guardar desactivado)")
            else:
                st.error("⚠️ No se guardó — revisa la barra lateral")
    with b2:
        if nuevo_texto != texto:
            st.warning("Cambios sin guardar")

with tab_trans:
    st.caption("Guarda la transcripción de la reunión en "
               f"{cliente}/transcripciones/")
    fc1, fc2 = st.columns(2)
    fecha_tr = fc1.date_input("Fecha", value=dt.date.today())
    titulo_tr = fc2.text_input("Título (opcional)")
    contenido = st.text_area("Transcripción", height=300)
    archivo = st.file_uploader("…o sube un .txt/.md", type=["txt", "md"])
    if archivo:
        contenido = archivo.read().decode("utf-8", errors="replace")
    if st.button("🎙️ Guardar transcripción", disabled=not contenido.strip()):
        try:
            store.transcribir(cliente, fecha_tr.isoformat(), contenido, titulo_tr)
            st.success(f"Guardada: transcripciones/{fecha_tr.isoformat()}.md")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

with tab_hist:
    if not hist:
        st.info("Sin reuniones registradas todavía.")
    for fecha, titulo, cuerpo in reversed(hist):
        with st.expander(f"📅 {fecha} — {titulo}"):
            st.markdown(cuerpo or "*(sin detalle)*")

# -*- coding: utf-8 -*-
"""📁 Fichas de proyectos: sincronización con el portal, brochure y análisis."""
import datetime as dt
import re

import streamlit as st

from core import iproppi_api as api
from core import llm
from core import proyectos as proj
from core.ui import sidebar_portal

st.set_page_config(page_title="Proyectos", page_icon="📁", layout="wide")
st.title("📁 Fichas de proyectos iproppi")

try:
    _secrets = st.secrets
except Exception:  # noqa: BLE001
    _secrets = {}

alm = proj.almacen_desde_secrets(_secrets)
claves = llm.claves_desde_secrets(_secrets)
portal = sidebar_portal()


def _ejecutar_sync():
    """Sincroniza contra el portal con barra de progreso en vivo."""
    barra = st.progress(0.0, text="Consultando el portal…")
    with st.status("🔄 Sincronizando con ventas.iproppi.com…",
                   expanded=True) as estado:
        def progreso(i, total, msg):
            barra.progress(min(i / max(total, 1), 1.0), text=msg)
            st.caption(msg)

        try:
            inf = proj.sincronizar(portal, alm, claves, progreso=progreso)
        except Exception as e:  # noqa: BLE001
            estado.update(label=f"❌ Falló: {e}", state="error")
            st.error(str(e))
            return
        barra.progress(1.0, text="Listo")
        label = (f"✅ {len(inf['nuevos'])} nuevos · "
                 f"{len(inf['actualizados'])} actualizados · "
                 f"{inf['sin_cambios']} sin cambios · {inf['segundos']} s")
        if inf["errores"]:
            estado.update(label=f"⚠️ {label} · {len(inf['errores'])} errores",
                          state="error")
            st.warning("Proyectos con error:\n" + "\n".join(
                f"- **{n}**: {e}" for n, e in inf["errores"])[:2000])
        else:
            estado.update(label=label, state="complete")
            st.success(label)
        st.session_state["proj_ultima_sync"] = dt.datetime.now().strftime(
            "%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- sincronizar
st.subheader("🔄 Sincronización con ventas.iproppi.com")
auto = st.toggle(
    "Auto-sincronizar al abrir esta página (con el portal conectado)",
    value=True, key="proj_auto",
    help="Al conectar, revisa proyectos nuevos/cambiados, descarga sus "
         "brochures y los analiza con IA + investigación web")

if not portal:
    st.info("🔑 Conecta el portal en la barra lateral para sincronizar: la "
            "primera vez analiza los ~46 proyectos publicados (unos minutos); "
            "después solo lo nuevo.")
else:
    try:
        n_nuevos, n_cambiados = proj.pendientes_de_sync(portal, alm)
    except Exception:  # noqa: BLE001
        n_nuevos, n_cambiados = 0, 0
    c1, c2 = st.columns([3, 1])
    with c1:
        if n_nuevos or n_cambiados:
            st.warning(f"🔍 {n_nuevos} proyecto(s) nuevo(s) y {n_cambiados} "
                       f"cambiado(s) sin analizar.")
        else:
            st.caption("🟢 Al día con el portal · última sync: "
                       + st.session_state.get("proj_ultima_sync", "—"))
    with c2:
        if st.button("🔄 Sincronizar ahora", type="primary"):
            _ejecutar_sync()
            st.rerun()
    if (portal and auto and n_nuevos + n_cambiados
            and not st.session_state.get("proj_sync_automatica")):
        st.session_state["proj_sync_automatica"] = True
        _ejecutar_sync()
        st.rerun()

# ---------------------------------------------------------------------- ver
st.divider()
try:
    carpetas = alm.listar()
except Exception as e:  # noqa: BLE001
    st.error(f"No pude listar las fichas de proyectos: {e}")
    carpetas = []

if not carpetas:
    st.info("📭 Todavía no hay fichas de proyectos. Conecta el portal y "
            "sincroniza (arriba) para descargar y analizar el catálogo.")
    st.stop()

sel = st.selectbox("Proyecto", carpetas, key="sel_proyecto")
texto = alm.leer(sel) or ""
if not texto:
    st.stop()

tab_f, tab_b, tab_s, tab_a = st.tabs(
    ["👁️ Ficha", "📕 Brochure", "📦 Stock en vivo", "⚙️ Acciones"])

with tab_f:
    st.markdown(texto)

with tab_b:
    bt = alm.leer_archivo(sel, "brochure.txt")
    if bt:
        st.caption(f"Texto extraído del PDF: {len(bt):,} caracteres")
        st.text_area("brochure.txt", bt, height=420, key="brochure_area")
        st.download_button("⬇️ Descargar brochure.txt", data=bt,
                           file_name=f"{sel}-brochure.txt")
    else:
        st.info("Sin texto de brochure guardado para este proyecto.")
    m_pdf = re.search(r"\*\*Brochure PDF:\*\* (\S+)", texto)
    if m_pdf and m_pdf.group(1).startswith("http"):
        st.link_button("📕 Abrir el PDF original", m_pdf.group(1),
                       icon=":material/open_in_new:")

with tab_s:
    m_id = re.search(r"\*\*ID portal:\*\* ([0-9a-f-]+)", texto)
    if not portal:
        st.info("🔑 Conecta el portal para ver el stock en vivo.")
    elif not m_id:
        st.warning("Esta ficha no tiene ID de portal (antigua): "
                   "re-analízala para regenerarla.")
    else:
        try:
            unidades = portal.unidades(m_id.group(1))
            s = api.resumen_stock(unidades)
            c1, c2, c3 = st.columns(3)
            c1.metric("Disponibles", s["disponible"],
                      f"de {s['total']} unidades")
            c2.metric("Reservadas", s["reservada"])
            c3.metric("Sin stock", max(s["total"] - s["disponible"]
                                       - s["reservada"], 0))
            filas = [{"Tipo": t, "Disponibles": v["disponible"],
                      "Total": v["total"]}
                     for t, v in s["por_tipo"].items()]
            st.dataframe(filas, hide_index=True, width="stretch")
            st.caption("Stock consultado al portal en este momento.")
        except Exception as e:  # noqa: BLE001
            st.warning(f"No pude leer el stock: {e}")

with tab_a:
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button("🤖 Re-analizar con IA", type="primary",
                     disabled=not portal):
            with st.status("Re-analizando (brochure + web)…") as est:
                try:
                    ok = proj.reanalizar(portal, alm, claves, sel)
                    if ok:
                        est.update(label="✅ Ficha regenerada",
                                   state="complete")
                        st.rerun()
                    else:
                        est.update(label="❌ Proyecto no encontrado en el "
                                         "portal", state="error")
                except Exception as e:  # noqa: BLE001
                    est.update(label=f"❌ {e}", state="error")
    with ac2:
        st.download_button("⬇️ Descargar ficha.md", data=texto,
                           file_name="ficha.md")
    if m_pdf and m_pdf.group(1).startswith("http"):
        st.link_button("📕 Abrir / guardar el PDF del brochure",
                       m_pdf.group(1), icon=":material/download:")
    st.caption("El PDF queda además en cache local tras la primera "
               "sincronización, y su texto siempre en brochure.txt.")

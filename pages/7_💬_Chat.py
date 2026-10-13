# -*- coding: utf-8 -*-
"""💬 Chat con el asistente (Groq) — notas de cliente y recomendaciones."""
import datetime as dt
import re
import time

import streamlit as st

from core import fichas
from core import indicadores as ind
from core import iproppi_api as api
from core import llm
from core import proyectos as proj
from core import sync
from core.ui import almacen, sidebar_portal

st.set_page_config(page_title="Chat", page_icon="💬", layout="wide")
st.title("💬 Chat con el asistente")
store = almacen()
sync.barra_lateral(store)
portal = sidebar_portal()

try:
    _secrets = st.secrets
except Exception:  # noqa: BLE001
    _secrets = {}

claves = llm.claves_desde_secrets(_secrets)
if not claves:
    st.error("Falta `GROQ_API_KEY` (o `GROQ_API_KEYS`, varias separadas por "
             "coma) en los secrets de la app "
             "(Settings → Advanced settings → Secrets).")
    st.stop()

# ---------------------------------------------------------------- controles
c = st.columns([2, 3, 1])
modelo = c[0].selectbox("Modelo", [m for m, _ in llm.MODELOS],
                        format_func=lambda m: dict(llm.MODELOS)[m])
with c[1]:
    con_ind = st.toggle("Contexto: indicadores del día", value=True)
    con_cat = st.toggle("Contexto: catálogo iproppi", value=bool(portal),
                        disabled=not portal,
                        help="Conecta el portal en la barra lateral para "
                             "activarlo (habilita '3 propiedades para X')")
    con_fichas = st.toggle(
        "Contexto: fichas de proyectos", value=True,
        help="Cuando nombras un proyecto (o elige [[ELEGIDOS]]), el chat "
             "recibe su ficha analizada con brochure y ventajas")
with c[2]:
    st.write("")
    st.write("")
    if st.button("🧹 Limpiar chat"):
        st.session_state["chat"] = []
        st.session_state.pop("nota_pendiente", None)
        st.rerun()

if not portal:
    st.caption("🔑 Sin portal conectado: el chat no verá el catálogo ni podrá "
               "recomendar propiedades reales ni verificar stock.")

# contexto: cliente seleccionado
cliente_ctx = None
try:
    nombres = store.listar()
except Exception:  # noqa: BLE001
    nombres = []
if nombres:
    cliente_ctx = st.selectbox(
        "Contexto: ficha de cliente (opcional)", ["(ninguno)"] + nombres,
        key="chat_cliente")
    if cliente_ctx == "(ninguno)":
        cliente_ctx = None

st.divider()

# ------------------------------------------------------------------ historial
st.session_state.setdefault("chat", [])  # [{"role","content"}]

# catálogo (numeración [i] estable para [[ELEGIDOS:]])
catalogo_txt, catalogo_lista = "", []
if con_cat and portal:
    try:
        catalogo_txt, catalogo_lista = llm.contexto_catalogo(portal.proyectos())
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar el catálogo: {e}")


def system_prompt():
    partes = [llm.SYSTEM_PROMPT]
    if con_ind:
        partes.append(llm.contexto_indicadores(ind))
    if catalogo_txt:
        partes.append(catalogo_txt)
    if cliente_ctx:
        texto = store.leer(cliente_ctx)
        if texto:
            partes.append(f"Ficha del cliente {cliente_ctx} "
                          f"(fuente de verdad):\n{texto[:6000]}")
    proyecto = st.session_state.get("proyecto_reunion")
    if proyecto:
        partes.append(f"Proyecto seleccionado en el portal: {proyecto}")
    if con_fichas:
        ultimo_usuario = next(
            (m["content"] for m in reversed(st.session_state["chat"])
             if m["role"] == "user"), "")
        try:
            ctx = proj.contexto_fichas(
                ultimo_usuario, proj.almacen_desde_secrets(_secrets),
                elegidos=st.session_state.get("ultimo_elegidos"),
                catalogo=catalogo_lista if con_cat else None)
        except Exception:  # noqa: BLE001 — el contexto es best-effort
            ctx = ""
        if ctx:
            partes.append(ctx)
    return "\n\n".join(partes)


for msg in st.session_state["chat"]:
    with st.chat_message(msg["role"],
                         avatar="🧑‍💼" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

prompt = st.chat_input(
    "Escribe aquí — ej: '3 propiedades para Daniela' o 'tiene 2 hijos'")

if prompt:
    st.session_state["chat"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(prompt)

    mensajes = ([{"role": "system", "content": system_prompt()}]
                + st.session_state["chat"])
    with st.chat_message("assistant", avatar="🤖"):
        salida = None
        for intento in range(2):
            try:
                salida = st.write_stream(
                    llm.stream(claves, mensajes, modelo=modelo))
                break
            except llm.LLMError as e:
                if "429" in str(e) and intento == 0:
                    st.warning("⏳ Groq está al límite de tokens por minuto: "
                               "espero 65 s y reintento (las 4 keys agotadas).")
                    time.sleep(65)
                    continue
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"{type(e).__name__}: {e}")
                break

    if salida:
        # --- extraer protocolos [[NOTA: ...]] y [[ELEGIDOS: ...]] ---
        m_nota = re.search(r"\[\[NOTA:\s*(.+?)\]\]", salida, re.S)
        if m_nota and cliente_ctx:
            st.session_state["nota_pendiente"] = {
                "cliente": cliente_ctx,
                "nota": re.sub(r"\s+", " ", m_nota.group(1)).strip(),
            }
        salida = re.sub(r"\[\[NOTA:\s*.+?\]\]", "", salida, flags=re.S)

        # extracción determinista: el modelo de chat no siempre cuelga el
        # bloque [[NOTA]], así que una llamada chica lo detecta siempre
        if cliente_ctx and not st.session_state.get("nota_pendiente"):
            try:
                nota = llm.extraer_nota(claves, store.leer(cliente_ctx), prompt)
                if nota:
                    st.session_state["nota_pendiente"] = {
                        "cliente": cliente_ctx, "nota": nota}
            except llm.LLMError:
                pass  # la nota es best-effort: el chat sigue funcionando

        m_el = re.search(r"\[\[ELEGIDOS:\s*([\d,\s]+?)\]\]", salida)
        elegidos = [int(x) for x in re.findall(r"\d+", m_el.group(1))] if m_el else []
        salida = re.sub(r"\[\[ELEGIDOS:\s*[\d,\s]+?\]\]", "", salida).strip()

        st.session_state["chat"].append({"role": "assistant",
                                         "content": salida})
        if elegidos and catalogo_lista:
            st.session_state["ultimo_elegidos"] = elegidos
        elif elegidos:
            st.session_state.pop("ultimo_elegidos", None)

# -------------------------------------------------- verificación de stock
elegidos = st.session_state.get("ultimo_elegidos")
if elegidos and catalogo_lista:
    st.divider()
    st.subheader("📦 Stock real de las propuestas")
    vistos = set()
    cols = st.columns(min(len(elegidos), 3))
    for n, i in enumerate(elegidos):
        if i in vistos or not (1 <= i <= len(catalogo_lista)):
            continue
        vistos.add(i)
        p_sel = catalogo_lista[i - 1]
        with cols[n % len(cols)]:
            try:
                unidades = portal.unidades(p_sel["id"])
                stock = api.resumen_stock(unidades)
                disp = stock["disponible"]
                st.metric(p_sel["name"],
                          f"{'✅' if disp else '🔒'} {disp} disponibles",
                          f"de {stock['total']} · {p_sel.get('location') or ''}")
                desde = llm._num_texto(p_sel.get("price_from_uf"))
                if desde:
                    st.caption(f"Desde {desde} UF · "
                               f"{int(p_sel.get('bedrooms') or 0)} dorm")
            except Exception as e:  # noqa: BLE001
                st.warning(f"{p_sel['name']}: {e}")
    st.caption("Stock consultado al portal en este momento (puede variar si "
               "hay reservas recientes).")

# ------------------------------------------- nota pendiente de confirmación
pend = st.session_state.get("nota_pendiente")
if pend:
    st.divider()
    with st.container(border=True):
        st.markdown(f"📝 **Nota sugerida para la ficha de {pend['cliente']}**")
        st.write(pend["nota"])
        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("✅ Guardar en la ficha", type="primary"):
                texto, sha = store.leer_meta(pend["cliente"])
                if texto is None:
                    st.error("No encontré la ficha.")
                else:
                    nuevo = fichas.agregar_nota(
                        texto, pend["nota"], dt.date.today().isoformat())
                    ok = sync.guardar_ficha_ui(
                        store, pend["cliente"], nuevo, "nota desde chat",
                        sha_esperado=sha)
                    if ok:
                        st.session_state.pop("nota_pendiente", None)
                        st.success("✅ Nota guardada en la ficha (sección 6)")
                        st.rerun()
                    elif ok is None:
                        st.session_state.pop("nota_pendiente", None)
                        st.info("📝 Nota en cola de guardado (auto-guardar "
                                "desactivado)")
                        st.rerun()
                    else:
                        st.error("⚠️ No se guardó — revisa la barra lateral")
        with b2:
            if st.button("❌ Descartar"):
                st.session_state.pop("nota_pendiente", None)
                st.rerun()

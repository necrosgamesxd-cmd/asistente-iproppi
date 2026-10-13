# -*- coding: utf-8 -*-
"""💬 Chat con el asistente (Groq)."""
import streamlit as st

from core import indicadores as ind
from core import llm
from core import sync
from core import fichas
from core.ui import almacen

st.set_page_config(page_title="Chat", page_icon="💬", layout="wide")
st.title("💬 Chat con el asistente")
store = almacen()
sync.barra_lateral(store)


def api_key():
    try:
        return st.secrets.get("GROQ_API_KEY")
    except Exception:  # noqa: BLE001
        return None


key = api_key()
if not key:
    st.error("Falta `GROQ_API_KEY` en los secrets de la app "
             "(Settings → Advanced settings → Secrets).")
    st.stop()

# ---------------------------------------------------------------- controles
c = st.columns([2, 2, 1])
modelo = c[0].selectbox("Modelo", [m for m, _ in llm.MODELOS],
                        format_func=lambda m: dict(llm.MODELOS)[m])
with c[1]:
    st.write("")
    con_ind = st.toggle("Contexto: indicadores del día", value=True)
    st.write("")
with c[2]:
    st.write("")
    st.write("")
    if st.button("🧹 Limpiar chat"):
        st.session_state["chat"] = []
        st.rerun()

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

st.divider()

# ------------------------------------------------------------------ historial
st.session_state.setdefault("chat", [])  # [{"role","content"}]


def system_prompt():
    partes = [llm.SYSTEM_PROMPT]
    if con_ind:
        partes.append(llm.contexto_indicadores(ind))
    if cliente_ctx and cliente_ctx != "(ninguno)":
        texto = store.leer(cliente_ctx)
        if texto:
            partes.append(f"Ficha del cliente {cliente_ctx} "
                          f"(fuente de verdad):\n{texto[:6000]}")
    proyecto = st.session_state.get("proyecto_reunion")
    if proyecto:
        partes.append(f"Proyecto seleccionado en el portal: {proyecto}")
    return "\n\n".join(partes)


for msg in st.session_state["chat"]:
    with st.chat_message(msg["role"],
                         avatar="🧑‍💼" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

prompt = st.chat_input(
    "Pregunta algo — ej: 'Daniela gasta 1.600.000, ¿cuánto aprueban?'")

if prompt:
    st.session_state["chat"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(prompt)

    mensajes = ([{"role": "system", "content": system_prompt()}]
                + st.session_state["chat"])
    with st.chat_message("assistant", avatar="🤖"):
        try:
            salida = st.write_stream(
                llm.stream(key, mensajes, modelo=modelo))
        except llm.LLMError as e:
            salida = None
            st.error(str(e))
        except Exception as e:  # noqa: BLE001
            salida = None
            st.error(f"{type(e).__name__}: {e}")
    if salida:
        st.session_state["chat"].append({"role": "assistant",
                                         "content": salida})

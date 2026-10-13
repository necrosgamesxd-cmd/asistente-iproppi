# -*- coding: utf-8 -*-
"""🗓️ Preparar la próxima reunión — resumen ejecutivo en 1 clic."""
import datetime as dt
import re

import streamlit as st

from core import capacidad as cap_mod
from core import cifras
from core import cuota as cuota_mod
from core import fichas
from core import indicadores as ind
from core import iproppi_api as api
from core import proyeccion as proy_mod
from core import sync
from core.ui import almacen, sidebar_portal

st.set_page_config(page_title="Preparar reunión", page_icon="🗓️", layout="wide")
st.title("🗓️ Preparar la próxima reunión")
store = almacen()
sync.barra_lateral(store)
portal = sidebar_portal()

try:
    valor_uf = ind.get_uf()
except Exception as e:  # noqa: BLE001
    st.error(f"Sin UF: {e}")
    st.stop()

# -------------------------------------------------------------------- cliente
try:
    nombres = store.listar()
except Exception as e:  # noqa: BLE001
    st.error(f"No pude listar clientes: {e}")
    st.stop()
if not nombres:
    st.info("Crea un cliente primero en la página **Clientes**.")
    st.stop()

col1, col2 = st.columns([2, 1])
with col1:
    cliente = st.selectbox("Cliente", nombres, key="prep_cliente")
with col2:
    st.metric("UF hoy", ind.clp(valor_uf, 2))

texto = store.leer(cliente)
if not texto:
    st.error(f"Sin ficha de {cliente}.")
    st.stop()
datos, busca = fichas.parsear(texto)
hist = fichas.historial(texto)


def _numero(txt):
    """Extrae un número de texto en formato chileno y devuelve el MÁXIMO.

    'Variable: $1.300.000 – $1.600.000 (máximo $1.600.000)' -> 1600000
    (el escáner oficial también carga el máximo del rango).
    '⚠️ PENDIENTE — no se preguntó' -> 0.0
    """
    if not txt:
        return 0.0
    candidatos = []
    for m in re.finditer(r"\d[\d.]*,?\d*|\d+", str(txt)):
        limpio = m.group(0).replace(".", "").replace(",", ".")
        try:
            candidatos.append(float(limpio))
        except ValueError:
            continue
    return max(candidatos) if candidatos else 0.0


# ------------------------------------------------------------------- datos
renta = _numero(datos.get("Renta líquida"))
ahorro = _numero(datos.get("Capacidad de ahorro"))
deudas = _numero(datos.get("Deudas"))
cap_guardada = _numero(datos.get("Capacidad calculada (UF)"))

c = st.columns(4)
c[0].text_input("Renta líquida", value=datos.get("Renta líquida", ""),
                key="p_renta", help="Viene de la ficha; edítalo si cambió")
c[1].text_input("Ahorro mensual", value=datos.get("Capacidad de ahorro", ""),
                key="p_ahorro")
c[2].text_input("Deudas", value=datos.get("Deudas", ""), key="p_deudas")
proyecto_fav = c[3].text_input("Proyecto favorito",
                               value=datos.get("Proyecto favorito", ""))

st.divider()

# ------------------------------------------------------------------ ejecutar
if st.button("🧮 Preparar todo con los datos de hoy", type="primary"):
    prep = {}
    try:
        prep["cap"] = cap_mod.calcular(renta=renta, deudas=deudas,
                                       ahorro=ahorro, valor_uf=valor_uf,
                                       ignorar_deudas=True)
    except Exception as e:  # noqa: BLE001
        st.warning(f"Escáner: {e}")
    precio = None
    # precio del proyecto seleccionado en Portal, o del favorito en la ficha
    sel = st.session_state.get("proyecto_reunion")
    if sel and sel.get("precio"):
        precio = float(sel["precio"])
        prep["proyecto_sel"] = sel
    elif proyecto_fav and portal:
        try:
            for p in portal.proyectos():
                if fichas.plano(p["name"]) in fichas.plano(proyecto_fav):
                    precio = float(p.get("price_from_uf") or 0) or None
                    prep["proyecto_sel"] = {"id": p["id"], "name": p["name"],
                                            "precio": precio}
                    break
        except Exception:  # noqa: BLE001
            pass
    if precio:
        try:
            prep["cuota"] = cuota_mod.calcular(
                precio=precio, valor_uf=valor_uf, renta=renta or None,
                ahorro=ahorro or None, capacidad=cap_guardada or None,
                escenarios=True, saldos=[5, 10, 15])
        except Exception as e:  # noqa: BLE001
            st.warning(f"Cuota: {e}")
        try:
            prep["proy"] = proy_mod.calcular(precio=precio, valor_uf=valor_uf,
                                             arriendo=None, historico=True)
        except Exception:  # noqa: BLE001
            pass
    st.session_state["prep_resultado"] = prep
    st.session_state["prep_precio"] = precio

prep = st.session_state.get("prep_resultado")
precio = st.session_state.get("prep_precio")

if not prep:
    st.caption("Pulsa **Preparar todo** para dejar la lámina lista con la UF de hoy.")
    st.stop()

st.subheader(f"📋 Resumen para {cliente}")

# 1) ficha
c1, c2 = st.columns([3, 2])
with c1:
    st.markdown("**Qué busca**")
    st.write(busca or "*(sin resumen en la ficha)*")
    if hist:
        fecha, titulo, _cuerpo = hist[-1]
        st.markdown(f"**Última reunión:** {fecha} — {titulo}")
    for k in ("Comunas objetivo", "Tipo de propiedad", "Próxima reunión", "Estado"):
        if datos.get(k):
            st.write(f"**{k}:** {datos[k]}")
with c2:
    if prep.get("cap"):
        cap = prep["cap"]
        st.metric("🩺 Capacidad de crédito", ind.uf(round(cap["capacidad"])),
                  f"≈ {ind.clp(cap['capacidad_pesos'])}")
        st.caption(cap["formula"])
        st.info(f"*\"{cap['frase']}\"*")

# 2) cuota / lámina
if prep.get("cuota"):
    q = prep["cuota"]
    st.subheader(f"🏠 Lámina — {prep.get('proyecto_sel', {}).get('name', '')} "
                 f"({ind.uf(precio, 0)})")
    m = st.columns(4)
    m[0].metric("💰 Dividendo", ind.clp(q["cuota_pesos"]), ind.uf(q["cuota_uf"], 1))
    if q.get("lamina"):
        m[1].metric("% de renta", ind.pct(q["lamina"]["sobre_renta"]))
        if "diferencia" in q["lamina"]:
            if q["lamina"]["cuota_cabe"]:
                m[2].metric("Vs ahorro", "✅ Cabe",
                            ind.clp(q["lamina"]["diferencia"]) + " libre")
            else:
                m[2].metric("Vs ahorro", "⚠️ No cabe",
                            ind.clp(abs(q["lamina"]["diferencia"])))
    m[3].metric("Total pagado", ind.uf(q["total"]))
    if q.get("lamina"):
        st.success(f"*\"{q['lamina']['frase']}\"*")
    br = q.get("brecha")
    if br:
        st.error(f"⚠️ **Brecha:** faltan {ind.uf(br['faltan'])} "
                 f"(capacidad {ind.uf(br['capacidad'])} vs precio)")
        for v in br["vias"]:
            st.markdown(f"- **{v['n']}. {v['titulo']}:** {v['detalle']}")
    if q.get("escenarios"):
        st.dataframe(
            [{"Pie": f"{e['pie_pct']}%", "Cuota UF": ind.uf(e["cuota_uf"], 1),
              "Cuota CLP": ind.clp(e["cuota_pesos"])} for e in q["escenarios"]],
            hide_index=True, width="stretch")

# 3) proyección
if prep.get("proy"):
    p = prep["proy"]
    st.subheader("📈 Proyección (por qué comprar ahora)")
    st.write(f"*\"{p['frase']}\"*")
    if p.get("esperar", {}).get("resumen"):
        st.warning(f"⏳ {p['esperar']['resumen']}")
    if p.get("historico"):
        st.caption(p["historico"]["frase"])

# 4) cifras + frase de cierre
st.subheader("🏢 Cierre con cifras iproppi")
st.info(cifras.FRASE_10_SEGUNDOS)
st.caption("Mínimo 2 menciones por reunión: una al abrir y esta al cerrar.")

# 5) actualizar la ficha con lo calculado
st.divider()
if st.button("💾 Guardar en la ficha capacidad calculada y datos de hoy"):
    cap = prep.get("cap")
    nuevo = texto
    hoy = dt.date.today().isoformat()
    if cap:
        # reemplaza la fila completa (no solo la celda) para no romper la tabla
        nuevo = re.sub(r"^\| Capacidad calculada \(UF\) \|.*$",
                       f"| Capacidad calculada (UF) | **{round(cap['capacidad'])} UF** "
                       f"hoy (UF al {hoy}) |", nuevo, flags=re.M)
        if st.session_state.get("p_renta"):
            nuevo = re.sub(r"^\| Renta líquida \|.*$",
                           f"| Renta líquida | {st.session_state['p_renta']} |",
                           nuevo, flags=re.M)
    texto_leido, sha_leida = store.leer_meta(cliente)
    res = sync.guardar_ficha_ui(store, cliente, nuevo,
                                "preparación de reunión",
                                sha_esperado=sha_leida)
    if res:
        st.success("✅ Ficha actualizada"
                   + (f" — capacidad {ind.uf(round(cap['capacidad']))}"
                      if cap else ""))
        st.rerun()
    elif res is None:
        st.info("📝 En cola de guardado")
    else:
        st.error("⚠️ No se guardó — revisa la barra lateral")

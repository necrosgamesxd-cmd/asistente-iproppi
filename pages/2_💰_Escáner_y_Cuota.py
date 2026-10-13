# -*- coding: utf-8 -*-
"""💰 Escáner de capacidad + Cuota y lámina de cierre."""
import streamlit as st

from core import capacidad as cap_mod
from core import cuota as cuota_mod
from core import indicadores as ind
from core import sync
from core.ui import almacen

st.set_page_config(page_title="Escáner y Cuota", page_icon="💰", layout="wide")
st.title("💰 Escáner de capacidad · Cuota y lámina de cierre")
sync.barra_lateral(almacen())

try:
    valor_uf = ind.get_uf()
except Exception as e:  # noqa: BLE001
    st.error(f"No hay UF disponible: {e}")
    st.stop()

st.caption(f"UF usada: **{ind.clp(valor_uf, 2)}**")

tab1, tab2 = st.tabs(["🩺 Escáner (capacidad)", "🏠 Cuota / lámina de cierre"])

# -------------------------------------------------------------------- escáner
with tab1:
    st.markdown("**Fórmula iproppi:** `Capacidad UF = (Ingreso Neto × 60 ÷ UF) × 1,2`")
    c = st.columns(5)
    renta = c[0].number_input("Renta líquida", min_value=0, value=1_600_000,
                              step=50_000)
    dividendos = c[1].number_input("Dividendos", min_value=0, value=0, step=50_000)
    pensiones = c[2].number_input("Pensiones", min_value=0, value=0, step=50_000)
    arriendos = c[3].number_input("Arriendos", min_value=0, value=0, step=50_000)
    deudas = c[4].number_input("Cuotas de deudas", min_value=0, value=0, step=10_000)
    ign = st.toggle("No descontar deudas (como el escáner oficial de iproppi)",
                    value=deudas == 0,
                    help="El escáner real no descuenta deudas (verificado con 2 "
                         "casos). Actívalo para replicar su número; déjalo apagado "
                         "para el cálculo conservador.")
    ahorro = st.number_input("Capacidad de ahorro mensual", min_value=0, value=0,
                             step=50_000)

    if st.button("🩺 Calcular capacidad", type="primary"):
        try:
            r = cap_mod.calcular(renta=renta, dividendos=dividendos,
                                 pensiones=pensiones, arriendos=arriendos,
                                 deudas=deudas, ahorro=ahorro,
                                 ignorar_deudas=ign, valor_uf=valor_uf)
            st.session_state["cap_resultado"] = r
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

    r = st.session_state.get("cap_resultado")
    if r:
        m1, m2, m3 = st.columns(3)
        m1.metric("Ingreso neto", ind.clp(r["neto"]))
        m2.metric("Capacidad máxima", ind.uf(round(r["capacidad"])),
                  f"≈ {ind.clp(r['capacidad_pesos'])}")
        m3.metric("UF usada", ind.clp(r["uf"], 2), r["fecha"])
        with st.expander("Ver desglose del cálculo"):
            st.code(r["formula"])
            for etiqueta, monto in r["ingresos"]:
                signo = "-" if monto < 0 else ""
                st.write(f"- {etiqueta}: {signo}{ind.clp(abs(monto))}")
            if "cap_sin_deudas" in r:
                st.info(f"📌 Sin descontar deudas la capacidad sería "
                        f"**{ind.uf(r['cap_sin_deudas'])}** "
                        f"(diferencia {ind.uf(r['cap_sin_deudas_dif'])}).")
        st.success(f"💡 *\"{r['frase']}\"*")
        if ahorro:
            st.caption(f"Capacidad de ahorro declarada: {ind.clp(ahorro)} — "
                       f"úsala en la pestaña de Cuota.")

    with st.expander("🧪 Test de calibración (casos reales)"):
        t = cap_mod.tests(valor_uf)
        for nombre, val, esperado, ok in t["casos"]:
            st.write(f"{'✅' if ok else '❌'} {nombre}: **{ind.uf(val)}** "
                     f"(escáner mostró {esperado})")
        st.caption("La fórmula se recalibra con la UF del día; los casos del "
                   "escáner oficial se validan contra el rango 2.650–2.950 UF.")

# ---------------------------------------------------------------------- cuota
with tab2:
    c = st.columns(5)
    precio = c[0].number_input("Precio (UF)", min_value=100.0, value=3500.0,
                               step=50.0)
    pie_pct = c[1].number_input("Pie (% del precio)", min_value=0.0, max_value=90.0,
                                value=0.0, step=5.0)
    bono = c[2].number_input("Bono pie (%)", min_value=0.0, max_value=100.0,
                             value=0.0, step=5.0)
    tasa = c[3].number_input("Tasa anual (%)", min_value=0.0, value=4.5, step=0.1)
    anios = c[4].number_input("Años", min_value=1, max_value=50, value=30, step=1)

    c2 = st.columns(4)
    sistema = c2[0].selectbox("Sistema", ["frances", "aleman"],
                              format_func=lambda x: "Francés (constante)"
                              if x == "frances" else "Alemán (decreciente)")
    gracia = c2[1].number_input("Gracia (años)", min_value=0.0, max_value=10.0,
                                value=0.0, step=0.5)
    renta = c2[2].number_input("Renta líquida", min_value=0, value=1_600_000,
                               step=50_000, key="q_renta")
    ahorro = c2[3].number_input("Capacidad de ahorro", min_value=0, value=0,
                                step=50_000, key="q_ahorro")

    cap_aprob = st.number_input(
        "Capacidad aprobada (UF, del escáner) — para ver la brecha",
        min_value=0.0, value=0.0, step=10.0)
    tasa_sub = st.number_input("Tasa subsidiada (fogaze) — opcional",
                               min_value=0.0, value=0.0, step=0.1)

    c3 = st.columns(3)
    ver_escenarios = c3[0].toggle("Escenarios de pie 0/10/20%", value=True)
    ver_tabla = c3[1].toggle("Tabla de amortización anual")
    ver_saldos = c3[2].toggle("Saldos años 5/10/15", value=True)

    if st.button("🏠 Calcular cuota", type="primary"):
        try:
            q = cuota_mod.calcular(
                precio=precio, pie=pie_pct, bono_pie=bono, tasa=tasa,
                anios=int(anios), sistema=sistema, gracia=gracia,
                renta=renta or None, ahorro=ahorro or None,
                capacidad=cap_aprob or None,
                tasa_subsidiada=tasa_sub or None,
                valor_uf=valor_uf, escenarios=ver_escenarios,
                tabla=ver_tabla, saldos=[5, 10, 15] if ver_saldos else None)
            st.session_state["cuota_resultado"] = q
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

    q = st.session_state.get("cuota_resultado")
    if q:
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💰 Cuota 1ª mensual", ind.clp(q["cuota_pesos"]),
                  ind.uf(q["cuota_uf"], 1))
        m2.metric("Monto a financiar", ind.uf(q["monto"]),
                  ind.clp(q["monto_pesos"]))
        m3.metric("Total pagado", ind.uf(q["total"]), f"interés {ind.uf(q['intereses'])}")
        m4.metric("UF usada", ind.clp(q["uf"], 2))

        # lámina de cierre
        lam = q.get("lamina")
        if lam:
            st.subheader("📌 Lámina de cierre (los 3 datos)")
            L1, L2, L3 = st.columns(3)
            L1.metric("1. Dividendo mensual", ind.clp(lam["cuota_pesos"]),
                      ind.uf(q["cuota_uf"], 1))
            L2.metric("2. % de su renta", ind.pct(lam["sobre_renta"]),
                      f"sobre {ind.clp(lam['renta'])}")
            if "diferencia" in lam:
                if lam["cuota_cabe"]:
                    L3.metric("3. vs capacidad de ahorro", "✅ Cabe",
                              ind.clp(lam["diferencia"]) + " libre")
                else:
                    L3.metric("3. vs capacidad de ahorro",
                              f"⚠️ falta {ind.clp(abs(lam['diferencia']))}",
                              ind.pct(lam["exceso_pct"], 0) + " sobre el ahorro")
            else:
                L3.metric("3. vs capacidad de ahorro", "—",
                          help="Indica la capacidad de ahorro para comparar")
            st.info(f"💬 *\"{lam['frase']}\"*")

        # brecha + 3 vías
        br = q.get("brecha")
        if br:
            st.subheader("⚠️ Brecha de capacidad — 3 vías")
            st.error(f"Capacidad aprobada {ind.uf(br['capacidad'])} vs precio "
                     f"{ind.uf(br['precio'])} → **faltan {ind.uf(br['faltan'])}**")
            st.caption(f"Para este precio se necesita un ingreso neto de "
                       f"{ind.clp(br['neta_necesaria'])} (fórmula iproppi invertida).")
            for v in br["vias"]:
                st.markdown(f"**{v['n']}. {v['titulo']}:** {v['detalle']}")
        elif cap_aprob:
            st.success(f"✅ El precio {ind.uf(precio)} cabe en la capacidad "
                       f"aprobada {ind.uf(cap_aprob)}.")

        if "escenarios" in q:
            st.subheader("📊 Escenarios (mismo precio, tasa y plazo)")
            st.dataframe(
                [{"Pie": f"{e['pie_pct']}%",
                  "Monto UF": ind.uf(e["monto"]),
                  "Cuota UF": ind.uf(e["cuota_uf"], 1),
                  "Cuota CLP": ind.clp(e["cuota_pesos"]),
                  "% renta": ind.pct(e["pct_renta"], 0) if e["pct_renta"] else "—"}
                 for e in q["escenarios"]],
                hide_index=True, width="stretch")

        if "saldos" in q:
            st.subheader("📒 Saldo deudor")
            for s in q["saldos"]:
                st.write(f"- Al año **{s['anio']}**: debe {ind.uf(s['saldo'], 0)} "
                         f"({ind.clp(s['saldo'] * q['uf'])})")

        if "tabla" in q:
            with st.expander("📒 Tabla de amortización anual (UF)"):
                st.dataframe(
                    [{"Año": f["anio"],
                      "Cuota anual": ind.uf(f["cuota"]),
                      "Interés": ind.uf(f["interes"]),
                      "Capital": ind.uf(f["capital"]),
                      "Saldo": ind.uf(f["saldo"])} for f in q["tabla"]],
                    hide_index=True, width="stretch")

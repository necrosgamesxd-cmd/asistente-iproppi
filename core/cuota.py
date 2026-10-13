# -*- coding: utf-8 -*-
"""Cuota mensual (dividendo) + lámina de cierre y brecha con 3 vías.

Port de scripts/cuota.py — amortización francesa/alemana con período de gracia.
"""
from . import indicadores as base


# ------------------------------------------------------------------ crédito
def cuota_frances(monto, tasa_anual, meses, gracia_meses=0):
    """Sistema francés (cuota constante). Devuelve (cuotas[], total, intereses)."""
    r = tasa_anual / 100 / 12
    cuotas = []
    saldo = monto
    for _ in range(gracia_meses):
        cuotas.append(saldo * r)
    restantes = meses - gracia_meses
    if restantes <= 0:
        return cuotas, sum(cuotas), sum(cuotas) - (monto - saldo if saldo else 0)
    if r == 0:
        cuota = saldo / restantes
        cuotas += [cuota] * restantes
    else:
        cuota = saldo * r / (1 - (1 + r) ** (-restantes))
        for _ in range(restantes):
            interes = saldo * r
            saldo -= (cuota - interes)
            cuotas.append(cuota)
    total = sum(cuotas)
    return cuotas, total, total - monto


def cuota_aleman(monto, tasa_anual, meses, gracia_meses=0):
    """Sistema alemán (capital constante, cuota decreciente)."""
    r = tasa_anual / 100 / 12
    cuotas = []
    saldo = monto
    for _ in range(gracia_meses):
        cuotas.append(saldo * r)
    restantes = meses - gracia_meses
    capital = saldo / restantes if restantes else saldo
    for _ in range(restantes):
        cuotas.append(saldo * r + capital)
        saldo -= capital
    total = sum(cuotas)
    return cuotas, total, total - monto


def simular(monto, tasa, anios, sistema, gracia_anios=0):
    meses = int(anios * 12)
    gracia = int(round(gracia_anios * 12))
    if sistema == "aleman":
        cuotas, total, intereses = cuota_aleman(monto, tasa, meses, gracia)
    else:
        cuotas, total, intereses = cuota_frances(monto, tasa, meses, gracia)
    r = tasa / 100 / 12
    saldo = monto
    historial = []
    for i, c in enumerate(cuotas, start=1):
        interes = saldo * r
        capital = c - interes
        saldo -= capital
        historial.append({"mes": i, "cuota": c, "interes": interes,
                          "capital": capital, "saldo": max(saldo, 0)})
    return {"cuotas": cuotas, "primera": cuotas[0], "total": total,
            "intereses": intereses, "historial": historial,
            "saldo_final": historial[-1]["saldo"] if historial else 0}


def saldo_en(historial, mes):
    if mes <= 0:
        return None
    if mes > len(historial):
        return 0.0
    return historial[mes - 1]["saldo"]


# ------------------------------------------------------------------ reporte
def calcular(precio, pie=0, pie_unit="pct", bono_pie=0, tasa=4.5,
             tasa_subsidiada=None, anios=30, gracia=0, sistema="frances",
             renta=None, ahorro=None, capacidad=None, valor_uf=None,
             escenarios=False, tabla=False, saldos=None, refresh=False):
    """Informe completo como dict (para la UI)."""
    if valor_uf is None:
        valor_uf = base.get_uf(refresh)
    data = base.get_indicadores(refresh)
    pie_uf = precio * pie / 100 if pie_unit == "pct" else pie
    bono_uf = precio * bono_pie / 100
    monto = max(precio - pie_uf - bono_uf, 0)
    sim = simular(monto, tasa, anios, sistema, gracia)
    cuota_uf = sim["primera"]
    cuota_pesos = cuota_uf * valor_uf

    out = {
        "fecha": data.get("fecha", ""),
        "uf": valor_uf,
        "precio": precio, "precio_pesos": precio * valor_uf,
        "pie_uf": pie_uf, "pie_pie": pie if pie_unit == "pct" else None,
        "bono_uf": bono_uf,
        "monto": monto, "monto_pesos": monto * valor_uf,
        "tasa": tasa, "anios": anios, "sistema": sistema, "gracia": gracia,
        "cuota_uf": cuota_uf, "cuota_pesos": cuota_pesos,
        "ultima_cuota": sim["cuotas"][-1],
        "total": sim["total"], "total_pesos": sim["total"] * valor_uf,
        "intereses": sim["intereses"],
        "intereses_pesos": sim["intereses"] * valor_uf,
        "historial": sim["historial"],
    }

    # lámina de tres datos
    if renta:
        sobre_renta = cuota_pesos / renta * 100
        lamina = {
            "cuota_pesos": cuota_pesos,
            "sobre_renta": sobre_renta,
            "renta": renta,
            "frase": (f"{base.miles(precio)} UF de {anios} años: dividendo de "
                      f"{base.clp(cuota_pesos)}, el {base.pct(sobre_renta, 0)} "
                      f"de su renta."),
        }
        if ahorro:
            diferencia = ahorro - cuota_pesos
            lamina["ahorro"] = ahorro
            lamina["diferencia"] = diferencia
            lamina["cuota_cabe"] = diferencia >= 0
            lamina["exceso_pct"] = (abs(diferencia) / ahorro * 100) if diferencia < 0 else 0
        out["lamina"] = lamina

    # brecha + 3 vías
    if capacidad and precio > capacidad:
        brecha = precio - capacidad
        neta_necesaria = precio * valor_uf / (60 * 1.2)
        vias = []
        pie_nec = max(precio - capacidad, 0)
        vias.append({
            "n": 1, "titulo": "Aporte de pie",
            "detalle": (f"{base.uf(pie_nec)} ({base.pct(pie_nec / precio * 100, 0)} "
                        f"del precio) y financiar {base.uf(capacidad)}."),
        })
        if renta:
            falta_neta = neta_necesaria - renta
            if falta_neta > 0:
                vias.append({
                    "n": 2, "titulo": "Codeudor o segundo ingreso",
                    "detalle": (f"sumar {base.clp(falta_neta)} de renta líquida "
                                f"(llegar a {base.clp(neta_necesaria)} de ingreso neto)."),
                })
            else:
                vias.append({
                    "n": 2, "titulo": "Codeudor o segundo ingreso",
                    "detalle": "su renta ya alcanza; evaluar otro tipo de apoyo.",
                })
        if tasa_subsidiada:
            sim_sub = simular(monto, tasa_subsidiada, anios, sistema, gracia)
            d_uf = sim_sub["primera"] - cuota_uf
            vias.append({
                "n": 3, "titulo": "Fogaze / subsidio a la tasa",
                "detalle": (f"de {base.pct(tasa, 2)} a {base.pct(tasa_subsidiada, 2)} → "
                            f"cuota {base.uf(d_uf, 1)} más baja "
                            f"({base.clp(d_uf * valor_uf)} al mes)."),
            })
        else:
            vias.append({
                "n": 3, "titulo": "Fogaze / subsidio a la tasa",
                "detalle": "baja la cuota; indicar la tasa subsidiada para calcularlo exacto.",
            })
        out["brecha"] = {"capacidad": capacidad, "precio": precio,
                         "faltan": brecha, "neta_necesaria": neta_necesaria,
                         "vias": vias}

    # escenarios de pie 0/10/20%
    if escenarios:
        filas = []
        for pct_pie in (0, 10, 20):
            p_uf = precio * pct_pie / 100
            m = max(precio - p_uf - bono_uf, 0)
            s = simular(m, tasa, anios, sistema, gracia)
            c_peso = s["primera"] * valor_uf
            filas.append({
                "pie_pct": pct_pie, "pie_uf": p_uf, "monto": m,
                "cuota_uf": s["primera"], "cuota_pesos": c_peso,
                "pct_renta": (c_peso / renta * 100) if renta else None,
            })
        out["escenarios"] = filas

    # tabla anual
    if tabla:
        filas = []
        for anio in range(1, anios + 1):
            mes = anio * 12
            bloque = sim["historial"][mes - 12:mes]
            if not bloque:
                continue
            filas.append({
                "anio": anio,
                "cuota": sum(b["cuota"] for b in bloque),
                "interes": sum(b["interes"] for b in bloque),
                "capital": sum(b["capital"] for b in bloque),
                "saldo": bloque[-1]["saldo"],
            })
        out["tabla"] = filas

    if saldos:
        out["saldos"] = [
            {"anio": a, "saldo": saldo_en(sim["historial"], a * 12)}
            for a in saldos
            if saldo_en(sim["historial"], a * 12) is not None
        ]
    return out

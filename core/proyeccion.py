# -*- coding: utf-8 -*-
"""Proyección de valorización y costo de esperar (proyección negativa).

Port de scripts/proyeccion.py.
"""
import datetime as dt

from . import indicadores as base


def calcular(precio, anio=None, valorizacion=4.7, uf_actual=None, ipc=3.0,
             arriendo=None, cuota=None, historico=False, refresh=False):
    """Informe completo como dict (para la UI)."""
    hoy = dt.date.today()
    anio = anio or hoy.year + 4
    anios = max(anio - hoy.year, 1)
    uf_ahora = uf_actual if uf_actual else base.get_uf(refresh)
    data = base.get_indicadores(refresh)

    precio_fut = precio * (1 + valorizacion / 100) ** anios
    uf_fut = uf_ahora * (1 + ipc / 100) ** anios
    delta_uf = precio_fut - precio

    out = {
        "anio": anio, "anios": anios,
        "valorizacion": valorizacion, "ipc": ipc,
        "uf_hoy": uf_ahora, "uf_fecha": data.get("fecha", ""),
        "uf_futura": uf_fut,
        "precio_hoy": precio, "precio_hoy_pesos": precio * uf_ahora,
        "precio_futuro": precio_fut, "precio_futuro_pesos": precio_fut * uf_fut,
        "ganancia_uf": delta_uf,
        "ganancia_pesos": precio_fut * uf_fut - precio * uf_ahora,
        "frase": (f"Si espera a {anio}, el mismo departamento vale "
                  f"{base.uf(precio_fut)} ({base.clp(precio_fut * uf_fut)}): "
                  f"son {base.uf(delta_uf)} más por esperar."),
    }

    # costo de esperar
    esperar = {}
    if arriendo:
        pagado = arriendo * 12 * anios
        esperar["arriendo_mes"] = arriendo
        esperar["arriendo_total"] = pagado
        out["frase_arriendo"] = (f"Y mientras tanto habrá pagado "
                                 f"{base.clp(pagado)} de arriendo ajeno.")
    if cuota:
        esperar["cuota_mes"] = cuota
        esperar["cuota_total"] = cuota * 12 * anios
    if arriendo:
        esperar["resumen"] = (f"Esperar cuesta {base.clp(esperar['arriendo_total'])} "
                              f"de arriendo + {base.uf(delta_uf)} de precio.")
    elif cuota:
        esperar["resumen"] = f"Esperar cuesta {base.uf(delta_uf)} de precio."
    if esperar:
        out["esperar"] = esperar

    # serie real de la UF
    if historico:
        desde = f"{hoy.year - anios}-{hoy.month:02d}-{min(hoy.day, 28):02d}"
        puntos = base.serie_uf(desde, refresh=refresh)
        if len(puntos) > 1:
            var = (puntos[-1]["valor"] / puntos[0]["valor"] - 1) * 100
            out["historico"] = {
                "desde": puntos[0]["fecha"], "desde_valor": puntos[0]["valor"],
                "hasta": puntos[-1]["fecha"], "hasta_valor": puntos[-1]["valor"],
                "variacion": var, "dias": len(puntos),
                "frase": (f"Real: la UF pasó de {base.clp(puntos[0]['valor'], 2)} "
                          f"({base.fecha_larga(puntos[0]['fecha'])}) a "
                          f"{base.clp(puntos[-1]['valor'], 2)} = {base.pct(var)} "
                          f"en {len(puntos)} días."),
            }
    return out

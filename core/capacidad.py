# -*- coding: utf-8 -*-
"""Escáner financiero iproppi — capacidad de crédito.

    Ingreso Neto = Renta + Dividendos + Pensiones + Arriendos - Cuotas de deudas
    Capacidad UF = ((Ingreso Neto x 60) / UF) x 1.2

Port de scripts/capacidad.py (misma fórmula y misma calibración).
"""
from . import indicadores as base


def capacidad_uf(renta, dividendos=0, pensiones=0, arriendos=0, deudas=0,
                 valor_uf=None, ignorar_deudas=False):
    """Devuelve (ingreso_neto, capacidad en UF)."""
    neto = renta + dividendos + pensiones + arriendos
    if not ignorar_deudas:
        neto -= deudas
    if valor_uf is None:
        valor_uf = base.get_uf()
    return neto, (neto * 60 / valor_uf) * 1.2


def calcular(renta, dividendos=0, pensiones=0, arriendos=0, deudas=0,
             ahorro=0, ignorar_deudas=False, valor_uf=None, refresh=False):
    """Informe completo como dict (para la UI).

    Devuelve claves: fecha, uf, neto, capacidad, capacidad_pesos, formula,
    ingresos[(etiqueta, monto)], frase, cap_sin_deudas (opcional), ahorro.
    """
    if valor_uf is None:
        valor_uf = base.get_uf(refresh)
    data = base.get_indicadores(refresh)
    neto, cap = capacidad_uf(
        renta=renta, dividendos=dividendos, pensiones=pensiones,
        arriendos=arriendos, deudas=deudas, valor_uf=valor_uf,
        ignorar_deudas=ignorar_deudas,
    )
    ingresos = [("Renta líquida", renta)]
    if dividendos:
        ingresos.append(("Dividendos", dividendos))
    if pensiones:
        ingresos.append(("Pensiones", pensiones))
    if arriendos:
        ingresos.append(("Arriendos", arriendos))
    if deudas:
        etiqueta = "Cuotas de deudas" + (" (NO descontadas)" if ignorar_deudas else "")
        ingresos.append((etiqueta, -deudas if not ignorar_deudas else deudas))

    salida = {
        "fecha": data.get("fecha", ""),
        "uf": valor_uf,
        "neto": neto,
        "capacidad": cap,
        "capacidad_pesos": cap * valor_uf,
        "formula": f"({base.clp(neto)} × 60) ÷ {base.clp(valor_uf, 2)} × 1,2",
        "ingresos": ingresos,
        "ahorro": ahorro,
        "frase": (f"Con sus {base.clp(neto)} de ingreso neto, hoy puede optar "
                  f"hasta {base.uf(round(cap))}."),
    }
    if deudas and not ignorar_deudas:
        _, cap_ignorando = capacidad_uf(
            renta, dividendos, pensiones, arriendos, deudas,
            valor_uf, ignorar_deudas=True)
        salida["cap_sin_deudas"] = cap_ignorando
        salida["cap_sin_deudas_dif"] = cap_ignorando - cap
    return salida


def tests(valor_uf=None):
    """Valida contra los números que el escáner real mostró (como --test)."""
    valor_uf = valor_uf or base.get_uf()
    _, d = capacidad_uf(1600000, valor_uf=valor_uf)
    _, dl = capacidad_uf(1600000, deudas=100000, valor_uf=valor_uf, ignorar_deudas=True)
    _, dc = capacidad_uf(1600000, deudas=100000, valor_uf=valor_uf)
    return {
        "uf": valor_uf,
        "casos": [
            ("Daniela — 1.600.000 sin deudas", d, "2.800", 2650 <= d <= 2950),
            ("Luis — 1.600.000 − 100.000 (ignorando deudas)", dl, "2.800",
             2650 <= dl <= 2950),
            ("Luis — 1.600.000 − 100.000 (restando deudas)", dc, "≈2.629", True),
        ],
        "ok": (2650 <= d <= 2950) and (2650 <= dl <= 2950),
    }

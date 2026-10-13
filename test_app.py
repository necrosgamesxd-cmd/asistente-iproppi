# -*- coding: utf-8 -*-
"""Smoke test: ejecuta app.py y cada página con AppTest de Streamlit."""
import sys
import traceback
from pathlib import Path

from streamlit.testing.v1 import AppTest

BASE = Path(__file__).parent
archivos = [BASE / "app.py"] + sorted((BASE / "pages").glob("*.py"))

fallas = []
for archivo in archivos:
    nombre = archivo.name
    try:
        at = AppTest.from_file(str(archivo), default_timeout=90)
        at.run()
        if at.exception:
            exc = at.exception[-1]
            fallas.append((nombre, f"{type(exc).__name__}: "
                                   f"{getattr(exc, 'message', exc)}"))
            continue
        # capturar errores/warnings renderizados
        errores = [e.value for e in at.error]
        print(f"OK   {nombre}" + (f"  ⚠️ error() en UI: {errores}" if errores else ""))
    except Exception:
        fallas.append((nombre, traceback.format_exc()))
        print(f"FALLA {nombre}")

print("\n" + "=" * 60)
if fallas:
    for nombre, tb in fallas:
        print(f"\n--- {nombre} ---\n{tb}")
    sys.exit(1)
print("Todas las páginas corrieron sin excepción.")

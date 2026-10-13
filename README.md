# 🏠 Asistente Inmobiliario — iproppi

Webapp (Streamlit) para asesores de iproppi: replica y amplía la skill
`asistente-inmobiliario` — escáner de capacidad, cuota y lámina de cierre,
proyección, fichas de clientes con sync a GitHub, stock del portal ventas y
chat con LLM.

**Despliegue:** ver [DESPLIEGUE.md](DESPLIEGUE.md) · **Correr en local:**
`streamlit run app.py`

## Qué hace cada página

| Página | Función |
|---|---|
| 🏠 Portada | Indicadores del día, cifras de respaldo iproppi, flujo de compra, errores a evitar |
| 📊 Indicadores | Tablero UF/UTM/dólar/TPM… (mindicador.cl, respaldo SII), conversores UF↔$ y variación histórica |
| 💰 Escáner + Cuota | Capacidad de crédito, dividendo (francés/alemán, con gracia), lámina de cierre de 3 datos, brecha con 3 vías, escenarios de pie 0/10/20 %, tabla de amortización |
| 📈 Proyección | Valorización (4,7 % anual en UF), IPC, costo de esperar (arriendo ajeno), variación real de la UF |
| 👥 Clientes | Fichas `.md` (fuente de verdad), transcripciones, índice `clientes.xlsx`, **💾 Guardar en GitHub** + auto-guardar + barra de estado + detección de conflictos |
| 🏢 Portal iproppi | 46 proyectos, stock por estado/tipo, listas de precio, fases de pago, documentos — vía API con token pegado (nunca se guardan credenciales) |
| 🗓️ Preparar reunión | Resumen ejecutivo en 1 clic: qué busca el cliente, capacidad, lámina, proyección y cifras de cierre |
| 💬 Chat | Groq (Qwen/GPT-OSS) con contexto de indicadores + ficha del cliente + proyecto seleccionado |

## Las fórmulas (idénticas a la skill)

```
Ingreso Neto = Renta + Dividendos + Pensiones + Arriendos − Cuotas de deudas
Capacidad UF = (Ingreso Neto × 60 ÷ UF) × 1,2          ← el escáner oficial NO descuenta deudas
Cuota        = saldo × r / (1 − (1+r)^−n), r = tasa/100/12   (francés; alemán: capital constante)
Proyección   = precio × (1 + 4,7 % anual en UF)^años
Lámina       = dividendo mensual · % de la renta · vs capacidad de ahorro
Brecha       → 3 vías: pie · codeudor/2º ingreso · fogaze (subsidio a la tasa)
```

Validado contra los casos reales del escáner: renta 1.600.000 → **2.800 UF**
(con o sin deudas según el escenario, replicando el comportamiento oficial).

## Estructura

```
app.py                    portada
pages/                    las 8 páginas
core/
  indicadores.py          mindicador.cl + respaldo SII (UF/UTM) + formato chileno
  capacidad.py            escáner financiero
  cuota.py                amortización, lámina, brecha, escenarios
  proyección.py           valorización y costo de esperar
  fichas.py               plantilla/parseo + almacén local o GitHub (Contents API)
  sync.py                 cola de guardado, auto-sync, estado y conflictos
  iproppi_api.py          cliente JWT de soybroker-api-iproppi.onrender.com
  llm.py                  chat Groq (streaming)
  excel.py                índice clientes.xlsx (openpyxl)
  cifras.py               cifras de respaldo iproppi
  ui.py                   sidebar del portal, almacén, errores
test_app.py               smoke test de todas las páginas (AppTest)
```

## Tests

```bash
.venv/bin/python test_app.py          # todas las páginas sin excepción
```

Los motores además se validan contra la CLI original de la skill
(`capacidad.py --test`: 2.800 UF sin deudas / 2.800 ignorando / 2.625
restando deudas con la UF del día).

## Notas de contexto

- `system-prompt.md` guarda la personalidad "Sofía" del concepto anterior
  (open-webui) — úsala como referencia de voz si quieres ajustar el system
  prompt del chat (`core/llm.py`).
- Los cálculos usan la **UF del día** (SII oficial); por eso un número
  calculado hoy puede diferir en unos UF de uno calculado hace días.

#!/usr/bin/env bash
# inicia.sh — levanta el Asistente Inmobiliario (Streamlit)
#
#   ./inicia.sh            → http://localhost:8501
#   ./inicia.sh 8600       → http://localhost:8600
#   ./inicia.sh 8501 --remoto   → expuesto en tu red local (para el celular)
#
set -euo pipefail

CARPETA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUERTO="${1:-8501}"
ARG2="${2:-}"
cd "$CARPETA"

PY="$CARPETA/.venv/bin/python"
ST="$CARPETA/.venv/bin/streamlit"

# ¿existe el venv? si no, lo crea e instala dependencias
if [ ! -x "$ST" ]; then
  echo "🔧 Preparando entorno (.venv) la primera vez…"
  python3 -m venv .venv
  "$CARPETA/.venv/bin/pip" install --quiet --upgrade pip
  "$CARPETA/.venv/bin/pip" install --quiet -r requirements.txt
fi

# ¿faltan secrets? avisa pero igual arranca (los cálculos funcionan sin ellos)
if [ ! -f .streamlit/secrets.toml ]; then
  echo "⚠️  No existe .streamlit/secrets.toml — el chat Groq y el sync a GitHub"
  echo "    no funcionarán. Copia la plantilla y rellénala:"
  echo "    cp .streamlit/secrets.toml.example .streamlit/secrets.toml"
fi

echo "🏠 Asistente Inmobiliario → http://localhost:$PUERTO  (Ctrl+C para parar)"

if [ "$ARG2" = "--remoto" ]; then
  # accesible desde otros dispositivos de tu red
  exec "$ST" run app.py --server.port "$PUERTO" --server.headless true \
       --server.address 0.0.0.0 --browser.gatherUsageStats false
else
  exec "$ST" run app.py --server.port "$PUERTO" --server.headless true \
       --browser.gatherUsageStats false
fi

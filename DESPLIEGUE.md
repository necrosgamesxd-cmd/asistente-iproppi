# 🚀 Despliegue — Asistente Inmobiliario (Streamlit Community Cloud)

La app corre gratis en **Streamlit Community Cloud**. Como la nube no tiene
disco persistente, las fichas de clientes viven en un **repo privado de
GitHub** al que se llega por API.

---

## 1. Ejecutar en local

```bash
cd asistente
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Los secrets locales van en `.streamlit/secrets.toml` (ya existe una copia;
**nunca se sube a git** — está en `.gitignore`).

## 2. Crear el repo de datos (una sola vez)

Crea un repo **privado** nuevo en GitHub, por ejemplo `clientes-iproppi`.
La app escribe dentro de la carpeta `clientes/` de ese repo:

```
clientes-iproppi/
└── clientes/
    ├── Daniela Gallego Ospina/
    │   ├── ficha.md
    │   └── transcripciones/2026-09-29.md
    └── ...
```

> Se recomienda **separar** el repo de datos del repo del código: las fichas
> tienen datos sensibles de clientes y el código no.

## 3. Crear el PAT (token de GitHub)

1. GitHub → Settings → Developer settings → **Personal access tokens** →
   Fine-grained tokens → Generate new.
2. **Repository access**: Only select repositories → el repo de datos.
3. **Permissions**: Contents → **Read and write**.
4. Copia el token (`github_pat_…`).

## 4. Subir el código y desplegar

```bash
cd asistente
git init && git add -A && git commit -m "Asistente inmobiliario v1"
git remote add origin git@github.com:USUARIO/asistente.git
git push -u origin main
```

En [share.streamlit.io](https://share.streamlit.io/):

1. **Deploy a app** → selecciona tu repo → Main file path: `app.py`.
2. **Advanced settings → Secrets** y pega:

```toml
GROQ_API_KEY = "gsk_..."        # ver paso 5
GITHUB_REPO  = "USUARIO/clientes-iproppi"
GITHUB_PAT   = "github_pat_..."
```

3. Deploy. La URL pública queda en `https://USUARIO-asistente.streamlit.app`.

## 5. La API key de Groq

La key vive en los secrets de la app (nunca en el código). La de los
proyectos "nexor" quedó expuesta en una sesión de chat: **créala nueva** en
[console.groq.com](https://console.groq.com/keys) y reemplázala en secrets.

## 6. Cómo conectar el portal en cada sesión

1. Entra a [ventas.iproppi.com](https://ventas.iproppi.com/) e inicia sesión.
2. **F12** → Application → Local Storage → `ventas.iproppi.com`.
3. Copia el valor de **`advisor_refresh_token`** (dura 30 días).
4. Pégalo en **🔑 Portal iproppi** (barra lateral) → Conectar.

La app lo cambia por un access token (60 min) y lo renueva sola.

## 7. Mantenimiento

| Tarea | Cómo |
|---|---|
| Actualizar la app | `git push` — Community Cloud redespliega solo |
| Cambiar secrets | share.streamlit.io → app → Settings → Secrets |
| Ver el estado del sync | Barra lateral: "🟢 Sincronizado — HH:MM:SS" o "⚠️ N sin guardar" |
| Resolver un conflicto | Botón **Force** en la barra lateral (pisa la versión remota) |
| Copia de seguridad de fichas | El repo de datos ya ES la copia (historial git) |

## ⚠️ Notas

- **mindicador.cl** a veces cae: la app usa el **SII** como respaldo para
  UF/UTM (mismos valores oficiales). Los demás indicadores vuelven solos.
- El portal de iproppi corre en Render free tier: el primer llamado tras
  un rato inactivo puede tardar hasta ~50 s.
- La app es **pública** (sin contraseña). Los cálculos no muestran datos de
  clientes (esas fichas solo existen detrás de tu PAT), pero quien tenga la
  URL puede hacer cálculos con los indicadores del día.

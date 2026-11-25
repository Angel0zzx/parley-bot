# Parley Bot

[English](#overview) | [Español](#guía-en-español)

Automated football prediction bot that combines a **Poisson-based statistical model** with live match data and delivers curated picks to Telegram. Ships as a standalone Windows `.exe` with a zero-config setup wizard, and can also run from source or on a schedule through GitHub Actions.

> **Disclaimer:** This project is for educational and informational purposes only. It does not constitute financial, betting, or investment advice. Football outcomes are inherently uncertain, and no model can guarantee results. Always gamble responsibly and only wager what you can afford to lose. If you or someone you know has a gambling problem, seek help.

---

<a id="overview"></a>
## Overview & Statistical Model

Parley Bot fetches recent team form and fixtures from one or two data providers, estimates each team's **expected goals (xG / λ)** from recent scoring and conceding averages, and then derives market probabilities using a **Poisson distribution**.

| Component | Detail |
| --- | --- |
| Expected goals (xG) | `λ_home = (home GF + away GA) / 2`, `λ_away = (away GF + home GA) / 2`, clamped to `[0.3, 4.0]` |
| Over / Under | Independent Poisson lines at **1.5, 2.5 and 3.5** goals |
| BTTS | Both Teams To Score derived from `P(home ≥ 1) × P(away ≥ 1)` |
| Fair odds | `1 / probability` (no bookmaker margin applied) |
| Pick filter | Only probabilities in the **52%–95%** band are surfaced |
| Parley size | Up to **3 selections**, never two picks from the same match |

**Risk tiers** (based on single-selection probability):

| Level | Probability | Description |
| --- | --- | --- |
| **Safe** | ≥ 72% | High-confidence selections |
| **Medium** | ≥ 62% | Balanced risk/reward |
| **Risky** | ≥ 52% | Higher variance, higher fair odds |

The output is grouped into three parleys (`seguro`, `medio`, `arriesgado`) and can be sent to Telegram or printed to the console in debug mode.

> **Disclaimer:** The probabilities above are statistical estimates, not guarantees. Use them at your own risk.

---

## Quick Start (Windows `.exe`)

1. **Download the ZIP** of the latest release and extract it to any folder.
2. Make sure `parley.exe` and the `_internal` folder stay **together** in the same directory — the executable will not run without `_internal`.
3. **Double-click `parley.exe`**. On first launch (or whenever credentials are missing) the interactive setup wizard runs automatically and walks you through **3 steps**:
   - **Step 1 — Football data:** create a free API key at [football-data.org](https://www.football-data.org/client/register) (and, optionally, a [Bzzoiro](https://sports.bzzoiro.com/) key for South American leagues).
   - **Step 2 — Telegram (optional):** create a bot with [@BotFather](https://t.me/BotFather) via `/newbot`, paste the bot token, then send `/start` to your bot. The wizard **auto-detects your `CHAT_ID`** from Telegram updates, or lets you enter it manually if detection fails.
   - **Step 3 — Time zone:** pick a preset (`America/Guayaquil`, `America/Bogota`, `America/Lima`, `America/Argentina/Buenos_Aires`) or type any IANA time zone.

Credentials are saved to a `.env` file next to the executable. Choose option **`4`** from the interactive menu to reconfigure at any time.

---

## Architecture & Developer Setup

The codebase is organized as a modular Python package under `src/parley/`:

```
parley-bot/
├── src/parley/
│   ├── cli.py                 # Unified CLI + interactive menu
│   ├── config.py              # Environment loading & competition constants
│   ├── models/
│   │   ├── poisson.py         # xG, Over/Under and BTTS probabilities
│   │   └── strategy.py        # Pick generation, risk tiers, parley building
│   ├── notifiers/
│   │   └── telegram.py        # Message formatting & Telegram delivery
│   ├── providers/
│   │   ├── base.py            # Provider interface
│   │   ├── football_data.py   # football-data.org client
│   │   └── bzzoiro.py         # Bzzoiro (South America) client
│   └── utils/
│       ├── cache.py           # Persistent 6-hour disk cache
│       └── setup_wizard.py    # Zero-config interactive onboarding
├── tests/                     # Pytest unit tests
├── .github/workflows/         # Scheduled GitHub Actions
├── parley.spec                # PyInstaller build configuration
├── pyproject.toml
└── requirements.txt
```

### Persistent cache

Team form is cached on disk in **`cache.json`** with a **6-hour TTL**, reducing API calls and keeping you within free-tier rate limits. Expired or corrupt caches are transparently rebuilt.

### Running from source

```bash
pip install -r requirements.txt
pip install .
python -m parley.cli --provider fd
```

### CLI options

| Flag | Description |
| --- | --- |
| `--provider {fd,bzzoiro,ambos}` | Data source: football-data.org, Bzzoiro, or both |
| `--fecha YYYY-MM-DD` | Target date (defaults to today) |
| `--debug` | Print picks to the console instead of sending to Telegram |
| `--incluir-pasados` | Include matches that have already kicked off today |

Running the module with **no arguments** opens the interactive menu (used when double-clicking the `.exe`).

### Building the standalone executable

```bash
pip install pyinstaller
pyinstaller parley.spec
```

The distributable is generated in `dist/parley/` (bundle `parley.exe` together with `_internal` when sharing).

### GitHub Actions automation

Scheduled workflows run the bot daily (see `.github/workflows/`). Add the following **repository secrets** under *Settings → Secrets and variables → Actions*:

| Secret | Purpose |
| --- | --- |
| `FOOTBALL_DATA_KEY` | football-data.org API key |
| `BZZOIRO_API_KEY` | Bzzoiro API key (South America) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Target Telegram chat ID |

---

<a id="guía-en-español"></a>
## Guía en Español

Bot de pronósticos de fútbol que combina un **modelo estadístico de Poisson** con datos reales de partidos y envía selecciones curadas a Telegram. Se distribuye como un `.exe` independiente para Windows con un asistente de configuración "zero-config", y también puede ejecutarse desde el código fuente o de forma programada mediante GitHub Actions.

> **Aviso legal:** Este proyecto tiene fines educativos e informativos únicamente. No constituye asesoría financiera, de apuestas ni de inversión. Los resultados del fútbol son inherentemente inciertos y ningún modelo puede garantizar resultados. Apuesta siempre de forma responsable y solo lo que puedas permitirte perder. Si tú o alguien que conoces tiene un problema con el juego, busca ayuda.

### Descripción general y modelo estadístico

Parley Bot obtiene la forma reciente de los equipos y los partidos desde uno o dos proveedores de datos, estima los **goles esperados (xG / λ)** a partir de los promedios recientes de goles a favor y en contra, y deriva las probabilidades de mercado con una **distribución de Poisson**.

| Componente | Detalle |
| --- | --- |
| Goles esperados (xG) | `λ_local = (GF local + GC visitante) / 2`, `λ_visitante = (GF visitante + GC local) / 2`, limitado a `[0.3, 4.0]` |
| Over / Under | Líneas de Poisson independientes en **1.5, 2.5 y 3.5** goles |
| BTTS | "Ambos anotan" derivado de `P(local ≥ 1) × P(visitante ≥ 1)` |
| Cuota justa | `1 / probabilidad` (sin margen de casa de apuestas) |
| Filtro de picks | Solo se muestran probabilidades en la banda **52%–95%** |
| Tamaño del parley | Hasta **3 selecciones**, nunca dos del mismo partido |

**Niveles de riesgo** (según la probabilidad de cada selección):

| Nivel | Probabilidad | Descripción |
| --- | --- | --- |
| **Seguro** | ≥ 72% | Selecciones de alta confianza |
| **Medio** | ≥ 62% | Riesgo/beneficio equilibrado |
| **Arriesgado** | ≥ 52% | Mayor varianza y cuotas más altas |

La salida se agrupa en tres parleys (`seguro`, `medio`, `arriesgado`) y puede enviarse a Telegram o imprimirse en consola en modo debug.

> **Aviso legal:** Las probabilidades son estimaciones estadísticas, no garantías. Úsalas bajo tu propio riesgo.

### Inicio rápido (Windows `.exe`)

1. **Descarga el ZIP** de la última versión y extráelo en cualquier carpeta.
2. Asegúrate de que `parley.exe` y la carpeta `_internal` permanezcan **juntos** en el mismo directorio — el ejecutable no funciona sin `_internal`.
3. **Haz doble clic en `parley.exe`**. En el primer inicio (o cuando falten credenciales) se ejecuta automáticamente el asistente interactivo, que te guía en **3 pasos**:
   - **Paso 1 — Datos de fútbol:** crea una API key gratuita en [football-data.org](https://www.football-data.org/client/register) (y, opcionalmente, una de [Bzzoiro](https://sports.bzzoiro.com/) para ligas sudamericanas).
   - **Paso 2 — Telegram (opcional):** crea un bot con [@BotFather](https://t.me/BotFather) usando `/newbot`, pega el token del bot y luego envía `/start` a tu bot. El asistente **detecta automáticamente tu `CHAT_ID`** desde las actualizaciones de Telegram, o te permite ingresarlo manualmente si la detección falla.
   - **Paso 3 — Zona horaria:** elige un preset (`America/Guayaquil`, `America/Bogota`, `America/Lima`, `America/Argentina/Buenos_Aires`) o escribe cualquier zona horaria IANA.

Las credenciales se guardan en un archivo `.env` junto al ejecutable. Elige la opción **`4`** del menú interactivo para reconfigurar cuando quieras.

### Arquitectura y configuración para desarrolladores

El código está organizado como un paquete modular de Python en `src/parley/` (misma estructura mostrada en la sección en inglés). La forma de los equipos se almacena en caché en disco en **`cache.json`** con un **TTL de 6 horas**, lo que reduce las llamadas a la API y respeta los límites del plan gratuito.

Ejecución desde el código fuente:

```bash
pip install -r requirements.txt
pip install .
python -m parley.cli --provider fd
```

Opciones de CLI: `--provider {fd,bzzoiro,ambos}`, `--fecha YYYY-MM-DD`, `--debug` y `--incluir-pasados`. Ejecutar el módulo **sin argumentos** abre el menú interactivo.

Compilación del ejecutable independiente:

```bash
pip install pyinstaller
pyinstaller parley.spec
```

La automatización con **GitHub Actions** se ejecuta a diario. Agrega estos **secrets** del repositorio (*Settings → Secrets and variables → Actions*): `FOOTBALL_DATA_KEY`, `BZZOIRO_API_KEY`, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.

---

## Credits & Collaboration

This project is **inspired by and builds upon the original work of [@mathiasrodas12345-gif](https://github.com/mathiasrodas12345-gif/asdasd)**. Full credit for the original idea and foundation goes to its author.

This version was refactored and extended with a focus on maintainability and developer experience:

- **Modular architecture** — reorganized into a clean `src/parley/` package with separated models, providers, notifiers and utilities.
- **Persistent cache** — a 6-hour on-disk cache to reduce API calls and rate-limit issues.
- **Unit tests** — a pytest suite covering the statistical model, strategy and providers.
- **Zero-config onboarding** — an interactive setup wizard with automatic Telegram `CHAT_ID` detection.

### Créditos y colaboración

Este proyecto está **inspirado y basado en el trabajo original de [@mathiasrodas12345-gif](https://github.com/mathiasrodas12345-gif/asdasd)**. Todo el crédito por la idea original y la base del proyecto corresponde a su autor.

Esta versión fue refactorizada y ampliada con un enfoque en mantenibilidad y experiencia de desarrollo:

- **Arquitectura modular** — reorganizada en un paquete limpio `src/parley/`, con modelos, proveedores, notificadores y utilidades separados.
- **Caché persistente** — caché en disco de 6 horas para reducir llamadas a la API y problemas de límite de peticiones.
- **Pruebas unitarias** — una suite de pytest que cubre el modelo estadístico, la estrategia y los proveedores.
- **Configuración "zero-config"** — un asistente interactivo con detección automática del `CHAT_ID` de Telegram.

Contributions, issues and pull requests are welcome. ¡Las contribuciones, issues y pull requests son bienvenidos!

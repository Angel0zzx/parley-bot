# Parley Bot

[English](#overview) | [Español](#guía-en-español)

Automated football prediction bot built around a **Dixon-Coles v2 model**, real bookmaker odds with an **EV+ filter**, **PostgreSQL persistence**, a **nightly audit** and **Free/VIP Telegram distribution**. It ships as a standalone Windows `.exe` with a zero-config setup wizard, and can also run from source or on a schedule through GitHub Actions.

> **Disclaimer:** This project is for educational and informational purposes only. It does not constitute financial, betting, or investment advice. Football outcomes are inherently uncertain, and no model can guarantee results. Always gamble responsibly and only wager what you can afford to lose. If you or someone you know has a gambling problem, seek help.

---

<a id="overview"></a>
## Overview & Architecture (v2.0)

Parley Bot fetches fixtures and recent form, estimates each team's scoring strength with a **Dixon-Coles** model, enriches picks with **real decimal odds**, filters by **expected value**, persists everything in **PostgreSQL (Neon)** and audits results automatically every night.

| Layer | What it does |
| --- | --- |
| **Dixon-Coles v2** | Home/away form splits, shrinkage toward league averages, low-score correlation (`rho`). |
| **Markets** | `1X2`, Double Chance, Draw No Bet, Over/Under `1.5/2.5/3.5`, BTTS. |
| **The Odds API** | Best decimal odds across bookmakers, derived DC/DNB prices and 15-minute cache. |
| **EV+ filter** | `EV = (prob/100) * cuota - 1`; picks with real odds are kept only when `EV > MIN_EV`. |
| **Neon PostgreSQL** | Stores `predictions` and `subscribers`; the bot keeps working if `DATABASE_URL` is empty. |
| **Nightly audit** | Resolves pending picks against football-data.org, computes hit rate and flat-stake ROI. |
| **Free/VIP** | VIP receives all three parleys; Free receives the safe parley plus a VIP invitation. |

### Statistical model (Dixon-Coles v2)

| Component | Detail |
| --- | --- |
| Expected goals | Home/away split attack/defence with shrinkage (`SHRINKAGE_K`), anchored to league averages. |
| Correlation | `DIXON_COLES_RHO` adjusts low-score outcomes (0-0, 1-0, 0-1, 1-1). |
| Markets | `1X2`, Double Chance (`1X`, `X2`), DNB, Over/Under 1.5/2.5/3.5 and BTTS. |
| Pick filter | `1X2` from **48%**, other markets from **52%**, capped at **95%**. |
| Risk tiers | Safe `>= 72%`, Medium `>= 62%`, Risky `>= 52%`. |
| Parley size | Up to **3 selections**, never two picks from the same match. |

### Real odds and EV+

The optional **The Odds API v4** integration requests `h2h,totals` in decimal format, selects the best price per outcome across bookmakers, and derives Double Chance / DNB prices from the 1X2 market. The EV filter is applied only when a real price exists; otherwise picks are kept as model-only (`cuota_real = None`, `ev = None`).

### PostgreSQL, audit and subscriptions

- `predictions` stores every morning pick with a unique constraint `(fecha, fixture_id, mercado, seleccion)` to avoid duplicates.
- `subscribers` stores VIP access with `expires_at` and `activo`.
- `python -m parley.cli --audit` resolves pending picks against `FINISHED` football-data.org matches and sends the nightly report.
- `python -m parley.cli --check-subs` expels expired VIPs (`banChatMember` followed by `unbanChatMember`) and marks them inactive.
- `python -m parley.cli --admin-once` (or `--admin-listen`) processes `/vip <user_id> [days]` and `/estado` from the administrator only.

### Free/VIP distribution

| Destination | Content |
| --- | --- |
| `TELEGRAM_VIP_CHAT_ID` | All three parleys (`seguro`, `medio`, `arriesgado`) with odds and EV+. |
| `TELEGRAM_FREE_CHAT_ID` | Only the safe parley plus a VIP invitation mentioning `VIP_CONTACT_USER`. |
| `TELEGRAM_CHAT_ID` | Fallback when neither channel ID is configured. |

The nightly audit is sent to both channels (or to `TELEGRAM_CHAT_ID` as fallback).

---

## Quick Start (Windows `.exe`)

1. **Download the ZIP** of the latest release and extract it to any folder.
2. Keep `parley.exe` and the `_internal` folder **together** in the same directory.
3. **Double-click `parley.exe`**. On first launch the interactive setup wizard runs and walks you through:
   - **Football data:** a free API key from [football-data.org](https://www.football-data.org/client/register) (optionally a [Bzzoiro](https://sports.bzzoiro.com/) key).
   - **Telegram (optional):** create a bot with [@BotFather](https://t.me/BotFather) and paste the token; the wizard auto-detects your `CHAT_ID`.
   - **Time zone:** choose a preset or type any IANA zone.

Credentials are saved to `.env` next to the executable. Choose option **`4`** in the interactive menu to reconfigure.

---

## Architecture & Developer Setup

```
parley-bot/
├── src/parley/
│   ├── cli.py                 # Unified CLI, morning run, audit and admin commands
│   ├── config.py              # Environment loading and constants
│   ├── audit.py               # Nightly result evaluation and ROI report
│   ├── subscriptions.py       # VIP activation, expiry revocation and /vip + /estado
│   ├── db/
│   │   └── repository.py      # PostgreSQL tables, predictions, subscribers and stats
│   ├── models/
│   │   ├── poisson.py         # Dixon-Coles matrix, 1X2, DC, DNB, goals and BTTS
│   │   └── strategy.py        # Pick generation, EV filter and parley building
│   ├── notifiers/
│   │   └── telegram.py        # Message formatting, Free/VIP routing and delivery
│   ├── providers/
│   │   ├── base.py            # Provider interface
│   │   ├── football_data.py   # football-data.org fixtures and finished results
│   │   ├── bzzoiro.py         # Bzzoiro (South America) client
│   │   └── odds_api.py        # The Odds API v4 client and derived markets
│   └── utils/
│       ├── cache.py           # Persistent disk cache
│       └── setup_wizard.py    # Zero-config interactive onboarding
├── tests/                     # Pytest unit tests
├── .github/workflows/         # parley.yml and audit.yml
├── parley.spec                # PyInstaller build configuration
├── pyproject.toml
└── requirements.txt
```

### Running from source

```bash
git clone https://github.com/Angel0zzx/parley-bot.git
cd parley-bot
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
| `--min-ev FLOAT` | Minimum EV for picks with real odds (default `0.0`) |
| `--sin-cuotas` | Ignore The Odds API and use model-only picks |
| `--audit` | Resolve pending picks and send the nightly report |
| `--add-vip USER_ID --days 30 [--username NAME]` | Activate or renew a VIP subscription |
| `--check-subs` | Expel expired VIP subscribers |
| `--admin-once` | Process pending `/vip` and `/estado` commands once |
| `--admin-listen` | Poll admin commands every 3 seconds |

Running the module with **no arguments** opens the interactive menu.

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `FOOTBALL_DATA_KEY` | Yes (FD) | football-data.org API key |
| `BZZOIRO_API_KEY` | No | Bzzoiro API key |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | Admin chat and fallback destination |
| `TELEGRAM_FREE_CHAT_ID` | No | Free public channel |
| `TELEGRAM_VIP_CHAT_ID` | No | VIP channel |
| `VIP_CONTACT_USER` | No | Contact shown in the Free invitation |
| `ODDS_API_KEY` | No | The Odds API key for real odds and EV |
| `ODDS_REGIONS` | No | The Odds API regions (default `eu`) |
| `MIN_EV` | No | Minimum EV filter (default `0.0`) |
| `DATABASE_URL` | No | Neon/PostgreSQL connection string |
| `TZ_LOCAL` | No | IANA time zone (default `America/Guayaquil`) |

If `DATABASE_URL` is empty the bot still generates and sends picks; persistence and the nightly audit are skipped. If the channel IDs are empty, delivery falls back to `TELEGRAM_CHAT_ID`.

### Building the standalone executable

```bash
pip install pyinstaller
pyinstaller parley.spec
```

The distributable is generated in `dist/parley/`.

### GitHub Actions automation

Scheduled workflows live in `.github/workflows/`. Add these **repository secrets** under *Settings → Secrets and variables → Actions*:

| Secret | Purpose |
| --- | --- |
| `FOOTBALL_DATA_KEY` | football-data.org API key |
| `BZZOIRO_API_KEY` | Bzzoiro API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Admin/fallback chat ID |
| `TELEGRAM_FREE_CHAT_ID` | Free public channel ID |
| `TELEGRAM_VIP_CHAT_ID` | VIP channel ID |
| `VIP_CONTACT_USER` | Contact for the Free invitation |
| `ODDS_API_KEY` | The Odds API key |
| `DATABASE_URL` | Neon PostgreSQL connection string |

- `parley.yml` runs the morning distribution at `11:15 UTC`.
- `audit.yml` runs the nightly audit at `04:00 UTC` (23:00 America/Bogota) and then `--check-subs` to expire VIPs.

---

<a id="guía-en-español"></a>
## Guía en Español

Bot de pronósticos de fútbol construido sobre un **modelo Dixon-Coles v2**, cuotas reales con **filtro EV+**, **persistencia en PostgreSQL**, **auditoría nocturna** y **distribución Free/VIP en Telegram**. Se distribuye como `.exe` para Windows con asistente de configuración y también puede ejecutarse desde el código fuente o con GitHub Actions.

> **Aviso legal:** Este proyecto tiene fines educativos e informativos únicamente. No constituye asesoría financiera, de apuestas ni de inversión. Los resultados del fútbol son inherentemente inciertos y ningún modelo puede garantizar resultados. Apuesta siempre de forma responsable y solo lo que puedas permitirte perder. Si tú o alguien que conoces tiene un problema con el juego, busca ayuda.

### Arquitectura v2.0

| Capa | Función |
| --- | --- |
| **Dixon-Coles v2** | Forma local/visitante separada, shrinkage hacia promedios de liga y correlación de marcadores bajos (`rho`). |
| **Mercados** | `1X2`, Doble Oportunidad, DNB, Over/Under `1.5/2.5/3.5` y BTTS. |
| **The Odds API** | Mejor cuota decimal por resultado, cuotas derivadas de DC/DNB y caché de 15 minutos. |
| **Filtro EV+** | `EV = (prob/100) * cuota - 1`; con cuota real solo se conserva el pick si `EV > MIN_EV`. |
| **PostgreSQL (Neon)** | Tablas `predictions` y `subscribers`; si `DATABASE_URL` está vacío el bot sigue funcionando. |
| **Auditoría nocturna** | Resuelve picks pendientes con resultados de football-data.org y calcula acierto y ROI. |
| **Free/VIP** | El VIP recibe los tres parleys; el Free recibe solo el seguro y una invitación al VIP. |

### Modelo estadístico

- Goles esperados con forma local/visitante, shrinkage (`SHRINKAGE_K`) y promedios de liga.
- Correlación Dixon-Coles (`DIXON_COLES_RHO`) para marcadores bajos.
- Filtro de picks: `1X2` desde **48%**, resto desde **52%**, máximo **95%**.
- Niveles: Seguro `>= 72%`, Medio `>= 62%`, Arriesgado `>= 52%`.
- Hasta **3 selecciones** por parley, sin repetir partido.

### Cuotas reales y EV+

La integración opcional con **The Odds API v4** solicita `h2h,totals` en formato decimal, elige la mejor cuota por resultado y deriva Doble Oportunidad y DNB desde el 1X2. El filtro EV solo se aplica cuando existe cuota real; si no, el pick se conserva como modelo puro (`cuota_real = None`, `ev = None`).

### Base de datos, auditoría y suscriptores

- `predictions` guarda cada pick con restricción única `(fecha, fixture_id, mercado, seleccion)`.
- `subscribers` guarda el acceso VIP con `expires_at` y `activo`.
- `python -m parley.cli --audit` resuelve picks pendientes contra partidos `FINISHED` y envía el reporte nocturno.
- `python -m parley.cli --check-subs` expulsa VIPs vencidos (`banChatMember` seguido de `unbanChatMember`) y los marca inactivos.
- `python -m parley.cli --admin-once` (o `--admin-listen`) procesa `/vip <user_id> [dias]` y `/estado` solo del administrador.

### Distribución Free/VIP

| Destino | Contenido |
| --- | --- |
| `TELEGRAM_VIP_CHAT_ID` | Los tres parleys (`seguro`, `medio`, `arriesgado`) con cuotas y EV+. |
| `TELEGRAM_FREE_CHAT_ID` | Solo el parley seguro más una invitación al VIP mencionando `VIP_CONTACT_USER`. |
| `TELEGRAM_CHAT_ID` | Respaldo cuando no hay canales configurados. |

La auditoría nocturna se envía a ambos canales (o a `TELEGRAM_CHAT_ID` como respaldo).

### Inicio rápido (Windows `.exe`)

1. **Descarga el ZIP** de la última versión y extráelo en cualquier carpeta.
2. Mantén `parley.exe` y la carpeta `_internal` **juntos**.
3. **Haz doble clic en `parley.exe`**. El asistente te guía para configurar la API de fútbol, Telegram y la zona horaria.

Las credenciales se guardan en `.env`. Usa la opción **`4`** del menú para reconfigurar.

### Ejecución desde el código fuente

```bash
git clone https://github.com/Angel0zzx/parley-bot.git
cd parley-bot
pip install -r requirements.txt
pip install .
python -m parley.cli --provider fd
```

### Opciones de CLI

| Flag | Descripción |
| --- | --- |
| `--provider {fd,bzzoiro,ambos}` | Fuente de datos |
| `--fecha YYYY-MM-DD` | Fecha objetivo (por defecto hoy) |
| `--debug` | Imprime en consola sin enviar |
| `--incluir-pasados` | Incluye partidos ya iniciados hoy |
| `--min-ev FLOAT` | EV mínimo para picks con cuota real (def. `0.0`) |
| `--sin-cuotas` | Ignora The Odds API y usa solo el modelo |
| `--audit` | Resuelve picks pendientes y envía el reporte nocturno |
| `--add-vip USER_ID --days 30 [--username NAME]` | Activa o renueva un VIP |
| `--check-subs` | Expulsa suscriptores VIP vencidos |
| `--admin-once` | Procesa comandos `/vip` y `/estado` una vez |
| `--admin-listen` | Polling de comandos admin cada 3 segundos |

### Variables de entorno

| Variable | Obligatoria | Uso |
| --- | --- | --- |
| `FOOTBALL_DATA_KEY` | Sí (FD) | API key de football-data.org |
| `BZZOIRO_API_KEY` | No | API key de Bzzoiro |
| `TELEGRAM_BOT_TOKEN` | Sí | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | Sí | Chat del administrador y respaldo |
| `TELEGRAM_FREE_CHAT_ID` | No | Canal público Free |
| `TELEGRAM_VIP_CHAT_ID` | No | Canal VIP |
| `VIP_CONTACT_USER` | No | Contacto en la invitación Free |
| `ODDS_API_KEY` | No | API key de The Odds API |
| `ODDS_REGIONS` | No | Regiones de The Odds API (def. `eu`) |
| `MIN_EV` | No | Filtro EV mínimo (def. `0.0`) |
| `DATABASE_URL` | No | Cadena de conexión PostgreSQL/Neon |
| `TZ_LOCAL` | No | Zona horaria IANA (def. `America/Guayaquil`) |

Si `DATABASE_URL` está vacío, el bot sigue generando y enviando picks; se omiten la persistencia y la auditoría. Si los canales están vacíos, se usa `TELEGRAM_CHAT_ID`.

### GitHub Actions

Agrega estos **secrets** del repositorio (*Settings → Secrets and variables → Actions*): `FOOTBALL_DATA_KEY`, `BZZOIRO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_FREE_CHAT_ID`, `TELEGRAM_VIP_CHAT_ID`, `VIP_CONTACT_USER`, `ODDS_API_KEY` y `DATABASE_URL`.

- `parley.yml` ejecuta la distribución matutina a las `11:15 UTC`.
- `audit.yml` ejecuta la auditoría a las `04:00 UTC` (23:00 America/Bogota) y luego `--check-subs` para vencer suscripciones.

### Compilación del ejecutable

```bash
pip install pyinstaller
pyinstaller parley.spec
```

---

## Credits & Collaboration

This project is **inspired by and builds upon the original work of [@mathiasrodas12345-gif](https://github.com/mathiasrodas12345-gif/asdasd)**. Full credit for the original idea and foundation goes to its author.

This version was refactored and extended with a focus on maintainability and developer experience:

- **Modular architecture** — a clean `src/parley/` package with separated models, providers, notifiers, database and utilities.
- **Dixon-Coles v2** — home/away splits, shrinkage and expanded markets.
- **Real odds and EV+** — The Odds API integration with derived markets.
- **PostgreSQL and audit** — Neon persistence, nightly hit-rate/ROI report and automatic VIP expiry.
- **Free/VIP distribution** — segmented Telegram delivery and admin commands.
- **Unit tests** — a pytest suite covering the model, odds, audit, subscriptions and routing.
- **Zero-config onboarding** — an interactive setup wizard with automatic Telegram `CHAT_ID` detection.

### Créditos y colaboración

Este proyecto está **inspirado y basado en el trabajo original de [@mathiasrodas12345-gif](https://github.com/mathiasrodas12345-gif/asdasd)**. Todo el crédito por la idea original y la base del proyecto corresponde a su autor.

Esta versión fue refactorizada y ampliada con un enfoque en mantenibilidad y experiencia de desarrollo:

- **Arquitectura modular** — paquete limpio `src/parley/` con modelos, proveedores, notificadores, base de datos y utilidades separados.
- **Dixon-Coles v2** — forma local/visitante, shrinkage y mercados ampliados.
- **Cuotas reales y EV+** — integración con The Odds API y mercados derivados.
- **PostgreSQL y auditoría** — persistencia en Neon, reporte nocturno de acierto/ROI y vencimiento automático de VIP.
- **Distribución Free/VIP** — envío segmentado por Telegram y comandos de administración.
- **Pruebas unitarias** — suite de pytest para modelo, cuotas, auditoría, suscripciones y enrutamiento.
- **Configuración "zero-config"** — asistente interactivo con detección automática del `CHAT_ID`.

Contributions, issues and pull requests are welcome. ¡Las contribuciones, issues y pull requests son bienvenidos!

"""
Central configuration module for parley-bot.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Determine base directory depending on whether running as compiled .exe or script
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"

if not ENV_PATH.exists():
    print(f"⚠️ Archivo .env no encontrado en {ENV_PATH}.")
    if ENV_EXAMPLE_PATH.exists():
        try:
            ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"✅ Se ha creado automáticamente un archivo .env basado en .env.example.")
        except Exception as e:
            print(f"❌ No se pudo crear el archivo .env: {e}")
    else:
        try:
            ENV_PATH.write_text(
                "FOOTBALL_DATA_KEY=\nBZZOIRO_API_KEY=\nTELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nTZ_LOCAL=America/Guayaquil\n",
                encoding="utf-8"
            )
            print(f"✅ Se ha creado un archivo .env en blanco.")
        except Exception:
            pass

    print("\n------------------------------------------------------------")
    print(f"POR FAVOR, edita el archivo .env ubicado en:\n{ENV_PATH}")
    print("Coloca tus API keys de Football-Data / Bzzoiro y Telegram.")
    print("------------------------------------------------------------\n")
    if getattr(sys, 'frozen', False):
        input("Presiona Enter para salir y configurar tus credenciales...")
        sys.exit(0)

load_dotenv(ENV_PATH)

FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "")
BZZOIRO_API_KEY = os.getenv("BZZOIRO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIMEZONE = os.getenv("TZ_LOCAL", "America/Guayaquil")

COMPETICIONES_FD = {
    "PL":  "Premier League",
    "PD":  "La Liga",
    "SA":  "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL":  "Champions League",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "BSA": "Brasileirao",
    "CLI": "Copa Libertadores",
}

LIGAS_SUDAMERICA = {
    85: "Liga Profesional Argentina",
}

RECENT_MATCHES = 10
MIN_MATCHES_REQUIRED = 3

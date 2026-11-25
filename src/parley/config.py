"""
Central configuration module for parley-bot.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

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

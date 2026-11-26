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

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "")
BZZOIRO_API_KEY = os.getenv("BZZOIRO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIMEZONE = os.getenv("TZ_LOCAL", "America/Guayaquil")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# --- Statistical model v2.0 ---
DIXON_COLES_RHO = float(os.getenv("DIXON_COLES_RHO", "-0.10"))
SHRINKAGE_K = float(os.getenv("SHRINKAGE_K", "4.5"))
LEAGUE_AVG_HOME_GOALS = float(os.getenv("LEAGUE_AVG_HOME_GOALS", "1.50"))
LEAGUE_AVG_AWAY_GOALS = float(os.getenv("LEAGUE_AVG_AWAY_GOALS", "1.20"))
CACHE_VERSION = 2

# --- The Odds API (optional) ---
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "eu")
MIN_EV = float(os.getenv("MIN_EV", "0.0"))
ODDS_TTL = 900  # 15 minutes

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

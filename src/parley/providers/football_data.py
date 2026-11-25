"""
Football-data.org provider implementation.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
import requests

from parley.providers.base import BaseProvider
from parley.config import COMPETICIONES_FD, RECENT_MATCHES, MIN_MATCHES_REQUIRED

log = logging.getLogger("parley.fd")
BASE_URL = "https://api.football-data.org/v4"
PAUSA_API = 6.5


class FootballDataProvider(BaseProvider):
    """Provider for football-data.org API v4."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._last_call = 0.0

    def _api_get(self, path: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Optional[Any]:
        wait = PAUSA_API - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        url = f"{BASE_URL}{path}"
        headers = {"X-Auth-Token": self.api_key}

        for intento in range(1, retries + 1):
            try:
                self._last_call = time.time()
                r = requests.get(url, headers=headers, params=params, timeout=30)
                if r.status_code == 429:
                    log.warning("Rate limit (429). Esperando 60s...")
                    time.sleep(60)
                    continue
                if r.status_code == 403:
                    log.error("API key de Football-Data inválida o sin permisos (403).")
                    return None
                r.raise_for_status()
                return r.json()
            except requests.RequestException as exc:
                log.warning("Petición falló (%d/%d): %s", intento, retries, type(exc).__name__)
                time.sleep(2 * intento)
        return None

    def get_matches(self, fecha_str: str, tz: ZoneInfo, solo_futuros: bool = True) -> List[Dict[str, Any]]:
        f_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        date_from = (f_obj - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to = (f_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        ahora_utc = datetime.now(timezone.utc)
        partidos = []

        for code, nombre in COMPETICIONES_FD.items():
            data = self._api_get(f"/competitions/{code}/matches", params={"dateFrom": date_from, "dateTo": date_to})
            if not data:
                continue

            for m in data.get("matches", []):
                status = m.get("status", "")
                if status not in ("SCHEDULED", "TIMED"):
                    continue
                utc_date = m.get("utcDate")
                if not utc_date:
                    continue
                try:
                    kickoff = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
                except ValueError:
                    continue

                kickoff_local = kickoff.astimezone(tz)
                if kickoff_local.strftime("%Y-%m-%d") != fecha_str:
                    continue

                if solo_futuros and kickoff <= ahora_utc:
                    continue

                partidos.append({
                    "id": m.get("id"),
                    "kickoff": kickoff,
                    "liga": nombre,
                    "liga_code": code,
                    "home_id": m.get("homeTeam", {}).get("id"),
                    "home": m.get("homeTeam", {}).get("name", "?"),
                    "away_id": m.get("awayTeam", {}).get("id"),
                    "away": m.get("awayTeam", {}).get("name", "?"),
                })

        log.info("Partidos Football-Data en %s: %d", fecha_str, len(partidos))
        return partidos

    def get_team_form(self, team_id: Any, cache: Dict[str, Any]) -> Optional[Dict[str, float]]:
        key = str(team_id)
        if key in cache.get("form", {}):
            return cache["form"][key]

        data = self._api_get(f"/teams/{team_id}/matches", params={"status": "FINISHED", "limit": RECENT_MATCHES})
        if not data:
            cache.setdefault("form", {})[key] = None
            return None

        partidos = data.get("matches", [])
        partidos.sort(key=lambda m: m.get("utcDate", ""), reverse=True)
        partidos = partidos[:RECENT_MATCHES]

        gf, ga = [], []
        for m in partidos:
            score = m.get("score", {}).get("fullTime", {})
            h = score.get("home")
            a = score.get("away")
            if h is None or a is None:
                continue
            es_local = m.get("homeTeam", {}).get("id") == team_id
            gf.append(h if es_local else a)
            ga.append(a if es_local else h)

        if len(gf) < MIN_MATCHES_REQUIRED:
            cache.setdefault("form", {})[key] = None
            return None

        form = {"gf": sum(gf) / len(gf), "ga": sum(ga) / len(ga), "n": len(gf)}
        cache.setdefault("form", {})[key] = form
        return form

"""
Bzzoiro Sports Data provider implementation with disk cache and prefixed keys.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
import requests

from parley.providers.base import BaseProvider
from parley.config import LIGAS_SUDAMERICA, RECENT_MATCHES, MIN_MATCHES_REQUIRED
from parley.utils.cache import load_cache, save_cache

log = logging.getLogger("parley.bzzoiro")
BASE_URL = "https://sports.bzzoiro.com/api/v2"
PAUSA_API = 0.2
STATUS_EXCLUIDOS = {"cancelled", "postponed", "unresolved", "abandoned"}


class BzzoiroProvider(BaseProvider):
    """Provider for Bzzoiro Sports Data API v2."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._last_call = 0.0

    def _api_get(self, path: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Optional[Any]:
        wait = PAUSA_API - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        url = f"{BASE_URL}{path}"
        headers = {"Authorization": f"Token {self.api_key}"}

        for intento in range(1, retries + 1):
            try:
                self._last_call = time.time()
                r = requests.get(url, headers=headers, params=params, timeout=30)
                if r.status_code == 429:
                    log.warning("Rate limit Bzzoiro (429). Esperando 5s...")
                    time.sleep(5)
                    continue
                if r.status_code == 401:
                    log.error("API key de Bzzoiro inválida (401).")
                    return None
                r.raise_for_status()
                return r.json()
            except requests.RequestException as exc:
                log.warning("Petición Bzzoiro falló (%d/%d): %s", intento, retries, type(exc).__name__)
                time.sleep(2 * intento)
        return None

    def get_matches(self, fecha_str: str, tz: ZoneInfo, solo_futuros: bool = True) -> List[Dict[str, Any]]:
        f_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        date_from = (f_obj - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to = (f_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        ahora_utc = datetime.now(timezone.utc)
        partidos = []

        for league_id, nombre in LIGAS_SUDAMERICA.items():
            data = self._api_get("/events/", params={"league_id": league_id, "date_from": date_from, "date_to": date_to})
            if not data:
                continue

            for m in data.get("results", []):
                status = (m.get("status") or "").lower()
                if status in STATUS_EXCLUIDOS:
                    continue

                event_date = m.get("event_date")
                if not event_date:
                    continue
                try:
                    kickoff = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
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
                    "home_id": m.get("home_team_id"),
                    "home": m.get("home_team", "?"),
                    "away_id": m.get("away_team_id"),
                    "away": m.get("away_team", "?"),
                })

        log.info("Partidos Bzzoiro en %s: %d", fecha_str, len(partidos))
        return partidos

    def get_team_form(self, team_id: Any, cache: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, float]]:
        if cache is None:
            cache = load_cache()

        key = f"bzz_{team_id}"
        if key in cache.get("form", {}):
            return cache["form"][key]

        hoy = datetime.now(timezone.utc).date()
        date_from = (hoy - timedelta(days=180)).strftime("%Y-%m-%d")
        date_to = hoy.strftime("%Y-%m-%d")

        data = self._api_get("/events/", params={"team_id": team_id, "status": "finished", "date_from": date_from, "date_to": date_to})
        if not data:
            cache.setdefault("form", {})[key] = None
            save_cache(cache)
            return None

        partidos = data.get("results", [])
        if len(partidos) < MIN_MATCHES_REQUIRED:
            cache.setdefault("form", {})[key] = None
            save_cache(cache)
            return None

        partidos.sort(key=lambda m: m.get("event_date", ""), reverse=True)
        partidos = partidos[:RECENT_MATCHES]

        gf, ga = [], []
        for m in partidos:
            hs = m.get("home_score")
            as_ = m.get("away_score")
            if hs is None or as_ is None:
                continue
            es_local = m.get("home_team_id") == team_id
            gf.append(hs if es_local else as_)
            ga.append(as_ if es_local else hs)

        if len(gf) < MIN_MATCHES_REQUIRED:
            cache.setdefault("form", {})[key] = None
            save_cache(cache)
            return None

        form = {"gf": sum(gf) / len(gf), "ga": sum(ga) / len(ga), "n": len(gf)}
        cache.setdefault("form", {})[key] = form
        save_cache(cache)
        return form

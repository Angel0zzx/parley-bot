"""
The Odds API client: real decimal odds, best-price selection, derived markets and cache.
"""

import logging
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import requests

from parley.config import ODDS_API_KEY, ODDS_REGIONS, ODDS_TTL
from parley.utils.cache import load_cache, save_cache

log = logging.getLogger("parley.odds")

BASE_URL = "https://api.the-odds-api.com/v4/sports"
MARKETS = "h2h,totals"
MATCH_THRESHOLD = 0.80
KICKOFF_WINDOW = timedelta(hours=4)

SPORT_KEYS = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "SA": "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "BSA": "soccer_brazil_campeonato",
    "CLI": "soccer_conmebol_copa_libertadores",
}

_SUFFIXES = (" fc", " cf", " sc", " afc", " club", " de futbol", " futbol club")


def normalize_team(name: str) -> str:
    """Normalize a team name for fuzzy matching."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    for suffix in _SUFFIXES:
        text = text.replace(suffix, "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_team(a), normalize_team(b)).ratio()


def match_event(partido: Dict[str, Any], events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the odds event matching a fixture by normalized names and kickoff window."""
    kickoff = partido.get("kickoff")
    if kickoff is not None and kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    best_event = None
    best_score = 0.0
    for event in events:
        if kickoff is not None and event.get("commence_time"):
            try:
                commence = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if abs((commence - kickoff).total_seconds()) > KICKOFF_WINDOW.total_seconds():
                continue

        home_ratio = _ratio(partido.get("home", ""), event.get("home_team", ""))
        away_ratio = _ratio(partido.get("away", ""), event.get("away_team", ""))
        if home_ratio < MATCH_THRESHOLD or away_ratio < MATCH_THRESHOLD:
            continue

        score = (home_ratio + away_ratio) / 2.0
        if score > best_score:
            best_score = score
            best_event = event
    return best_event


def classify_h2h(name: str, event: Dict[str, Any]) -> Optional[str]:
    """Map an h2h outcome name to home/draw/away."""
    normalized = normalize_team(name)
    if normalized in ("draw", "tie", "empate", "x"):
        return "draw"
    if not normalized:
        return None
    home_ratio = _ratio(name, event.get("home_team", ""))
    away_ratio = _ratio(name, event.get("away_team", ""))
    if max(home_ratio, away_ratio) < 0.6:
        return None
    return "home" if home_ratio >= away_ratio else "away"


def _best_entry(current: Optional[Dict[str, Any]], price: Any, casa: str) -> Optional[Dict[str, Any]]:
    if not isinstance(price, (int, float)) or price <= 1.0:
        return current
    if current is None or price > current["cuota"]:
        return {"cuota": float(price), "casa": casa, "derivada": False}
    return current


def best_h2h(event: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return the best decimal odds per outcome across bookmakers."""
    result: Dict[str, Dict[str, Any]] = {"home": None, "draw": None, "away": None}
    for bookmaker in event.get("bookmakers", []):
        casa = bookmaker.get("title") or bookmaker.get("key") or "?"
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                side = classify_h2h(outcome.get("name", ""), event)
                if side:
                    result[side] = _best_entry(result[side], outcome.get("price"), casa)
    return {key: value for key, value in result.items() if value}


def best_totals(event: Dict[str, Any]) -> Dict[float, Dict[str, Dict[str, Any]]]:
    """Return the best decimal odds per totals line and side across bookmakers."""
    result: Dict[float, Dict[str, Dict[str, Any]]] = {}
    for bookmaker in event.get("bookmakers", []):
        casa = bookmaker.get("title") or bookmaker.get("key") or "?"
        for market in bookmaker.get("markets", []):
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []):
                point = outcome.get("point")
                if point is None:
                    continue
                try:
                    point = float(point)
                except (TypeError, ValueError):
                    continue
                name = (outcome.get("name") or "").lower()
                if name.startswith("over"):
                    side = "over"
                elif name.startswith("under"):
                    side = "under"
                else:
                    continue
                slot = result.setdefault(point, {})
                slot[side] = _best_entry(slot.get(side), outcome.get("price"), casa)
    return {point: sides for point, sides in result.items() if sides}


def derive_double_chance(h2h: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Derive 1X and X2 odds from 1X2 decimal odds."""
    home = (h2h.get("home") or {}).get("cuota")
    draw = (h2h.get("draw") or {}).get("cuota")
    away = (h2h.get("away") or {}).get("cuota")
    derived: Dict[str, Dict[str, Any]] = {}
    if home and draw:
        derived["1X"] = {"cuota": 1.0 / (1.0 / home + 1.0 / draw), "casa": "derivada", "derivada": True}
    if draw and away:
        derived["X2"] = {"cuota": 1.0 / (1.0 / draw + 1.0 / away), "casa": "derivada", "derivada": True}
    return derived


def derive_dnb(h2h: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Derive draw-no-bet odds from 1X2 decimal odds."""
    home = (h2h.get("home") or {}).get("cuota")
    draw = (h2h.get("draw") or {}).get("cuota")
    away = (h2h.get("away") or {}).get("cuota")
    derived: Dict[str, Dict[str, Any]] = {}
    if home and draw:
        derived["home"] = {"cuota": home * (1.0 - 1.0 / draw), "casa": "derivada", "derivada": True}
    if away and draw:
        derived["away"] = {"cuota": away * (1.0 - 1.0 / draw), "casa": "derivada", "derivada": True}
    return derived


def build_event_odds(event: Dict[str, Any]) -> Dict[str, Any]:
    """Build the normalized odds payload for a single event."""
    h2h = best_h2h(event)
    return {
        "h2h": h2h,
        "dc": derive_double_chance(h2h),
        "dnb": derive_dnb(h2h),
        "totals": best_totals(event),
    }


class OddsApiClient:
    """Client for The Odds API with optional key and 15-minute cache."""

    def __init__(self, api_key: Optional[str] = None, regions: Optional[str] = None):
        self.api_key = ODDS_API_KEY if api_key is None else api_key
        self.regions = regions or ODDS_REGIONS

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def get_odds_for_matches(self, partidos: List[Dict[str, Any]], cache: Optional[Dict[str, Any]] = None) -> Dict[Any, Dict[str, Any]]:
        """Return odds keyed by fixture id. Empty dict when disabled or unmatched."""
        if not self.enabled or not partidos:
            return {}

        if cache is None:
            cache = load_cache()

        by_sport: Dict[str, List[Dict[str, Any]]] = {}
        for partido in partidos:
            sport_key = SPORT_KEYS.get(partido.get("liga_code"))
            if sport_key:
                by_sport.setdefault(sport_key, []).append(partido)

        result: Dict[Any, Dict[str, Any]] = {}
        for sport_key, fixtures in by_sport.items():
            events = self._get_events(sport_key, cache)
            for partido in fixtures:
                event = match_event(partido, events)
                if event:
                    result[partido.get("id")] = build_event_odds(event)
        return result

    def _get_events(self, sport_key: str, cache: Dict[str, Any]) -> List[Dict[str, Any]]:
        entry = cache.get("odds", {}).get(sport_key)
        if entry and time.time() - entry.get("timestamp", 0) <= ODDS_TTL:
            return entry.get("events", [])

        events = self._fetch(sport_key)
        if events is not None:
            cache.setdefault("odds", {})[sport_key] = {"timestamp": time.time(), "events": events}
            save_cache(cache)
        return events or []

    def _fetch(self, sport_key: str) -> Optional[List[Dict[str, Any]]]:
        url = f"{BASE_URL}/{sport_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": MARKETS,
            "oddsFormat": "decimal",
        }
        try:
            response = requests.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            log.warning("The Odds API no respondió (%s): %s", sport_key, type(exc).__name__)
            return None

        remaining = response.headers.get("x-requests-remaining")
        if remaining is not None:
            log.info("The Odds API créditos restantes: %s", remaining)

        if response.status_code == 401:
            log.error("ODDS_API_KEY inválida o sin permisos (401).")
            return None
        if response.status_code in (404, 422):
            log.warning("The Odds API sin datos para %s (%s).", sport_key, response.status_code)
            return []
        if not response.ok:
            log.warning("The Odds API error %s para %s.", response.status_code, sport_key)
            return None

        try:
            return response.json()
        except ValueError:
            log.warning("Respuesta no JSON de The Odds API para %s.", sport_key)
            return None

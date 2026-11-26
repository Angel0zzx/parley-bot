"""
Base abstract provider interface and shared form helpers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from parley.config import (
    LEAGUE_AVG_HOME_GOALS,
    LEAGUE_AVG_AWAY_GOALS,
    MIN_MATCHES_REQUIRED,
    SHRINKAGE_K,
)


class BaseProvider(ABC):
    """Abstract base class for sports data providers."""

    @abstractmethod
    def get_matches(self, fecha_str: str, tz: ZoneInfo, solo_futuros: bool = True) -> List[Dict[str, Any]]:
        """Fetch scheduled matches for a specific date in local timezone."""
        pass

    @abstractmethod
    def get_team_form(self, team_id: Any, cache: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch recent home/away form for a team."""
        pass


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _shrink(rate: float, n: int, prior: float) -> float:
    """Bayesian shrinkage toward the league baseline for small samples."""
    if n >= MIN_MATCHES_REQUIRED:
        return rate
    return (n * rate + SHRINKAGE_K * prior) / (n + SHRINKAGE_K)


def summarize_form(
    home_gf: List[float],
    home_ga: List[float],
    away_gf: List[float],
    away_ga: List[float],
) -> Dict[str, Any]:
    """Build home/away/overall form, shrinking small samples toward league baselines."""
    home_n = len(home_gf)
    away_n = len(away_gf)
    all_gf = list(home_gf) + list(away_gf)
    all_ga = list(home_ga) + list(away_ga)
    overall_n = len(all_gf)

    return {
        "home": {
            "gf": _shrink(_avg(home_gf), home_n, LEAGUE_AVG_HOME_GOALS),
            "ga": _shrink(_avg(home_ga), home_n, LEAGUE_AVG_AWAY_GOALS),
            "n": home_n,
        },
        "away": {
            "gf": _shrink(_avg(away_gf), away_n, LEAGUE_AVG_AWAY_GOALS),
            "ga": _shrink(_avg(away_ga), away_n, LEAGUE_AVG_HOME_GOALS),
            "n": away_n,
        },
        "overall": {
            "gf": _avg(all_gf),
            "ga": _avg(all_ga),
            "n": overall_n,
        },
        "n": overall_n,
    }

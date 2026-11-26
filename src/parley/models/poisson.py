"""
Poisson / Dixon-Coles probability model and expected goals calculations.
"""

import math
from typing import Dict, Tuple, Optional, List, Any

from parley.config import (
    DIXON_COLES_RHO,
    LEAGUE_AVG_HOME_GOALS,
    LEAGUE_AVG_AWAY_GOALS,
)

LAMBDA_MIN = 0.2
LAMBDA_MAX = 4.5
MAX_GOALS = 10


def poisson_pmf(k: int, lam: float) -> float:
    """Calculate Poisson probability mass function for exactly k events given rate lam."""
    if lam < 0:
        return 0.0
    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except OverflowError:
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def tau(x: int, y: int, lam_home: float, lam_away: float, rho: float) -> float:
    """Dixon-Coles low-score dependency adjustment."""
    if x == 0 and y == 0:
        return 1.0 - lam_home * lam_away * rho
    if x == 0 and y == 1:
        return 1.0 + lam_home * rho
    if x == 1 and y == 0:
        return 1.0 + lam_away * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam_home: float, lam_away: float, rho: Optional[float] = None, max_goals: int = MAX_GOALS) -> List[List[float]]:
    """Return a normalized (max_goals+1)x(max_goals+1) scoreline probability matrix."""
    rho = DIXON_COLES_RHO if rho is None else rho
    lam_home = max(float(lam_home), 0.0)
    lam_away = max(float(lam_away), 0.0)

    matrix = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]
    total = 0.0
    for x in range(max_goals + 1):
        px = poisson_pmf(x, lam_home)
        for y in range(max_goals + 1):
            py = poisson_pmf(y, lam_away)
            value = px * py * tau(x, y, lam_home, lam_away, rho)
            if value < 0.0:
                value = 0.0
            matrix[x][y] = value
            total += value

    if total > 0.0:
        for x in range(max_goals + 1):
            for y in range(max_goals + 1):
                matrix[x][y] /= total
    return matrix


def prob_1x2(lam_home: float, lam_away: float, rho: Optional[float] = None, max_goals: int = MAX_GOALS) -> Dict[str, float]:
    """Return home/draw/away win probabilities from the Dixon-Coles matrix."""
    matrix = score_matrix(lam_home, lam_away, rho, max_goals)
    p_home = p_draw = p_away = 0.0
    for x in range(len(matrix)):
        for y in range(len(matrix[x])):
            if x > y:
                p_home += matrix[x][y]
            elif x == y:
                p_draw += matrix[x][y]
            else:
                p_away += matrix[x][y]
    return {"home": p_home, "draw": p_draw, "away": p_away}


def prob_double_chance(lam_home: float, lam_away: float, rho: Optional[float] = None, max_goals: int = MAX_GOALS) -> Dict[str, float]:
    """Return double-chance probabilities (1X, X2, 12)."""
    p = prob_1x2(lam_home, lam_away, rho, max_goals)
    return {
        "1X": p["home"] + p["draw"],
        "X2": p["draw"] + p["away"],
        "12": p["home"] + p["away"],
    }


def prob_dnb(lam_home: float, lam_away: float, rho: Optional[float] = None, max_goals: int = MAX_GOALS) -> Dict[str, float]:
    """Return draw-no-bet probabilities, normalized without the draw."""
    p = prob_1x2(lam_home, lam_away, rho, max_goals)
    denom = p["home"] + p["away"]
    if denom <= 0.0:
        return {"home": 0.0, "away": 0.0}
    return {"home": p["home"] / denom, "away": p["away"] / denom}


def prob_over(lam: float, linea: float, lam_away: Optional[float] = None, rho: Optional[float] = None, max_goals: int = MAX_GOALS) -> float:
    """Over probability.

    With a single lambda it keeps the legacy univariate Poisson behavior.
    When ``lam_away`` is provided it is derived from the Dixon-Coles matrix.
    """
    if lam_away is None:
        umbral = int(linea)
        acum = sum(poisson_pmf(k, lam) for k in range(umbral + 1))
        return _clamp(1.0 - acum, 0.0, 1.0)

    matrix = score_matrix(lam, lam_away, rho, max_goals)
    total = sum(
        matrix[x][y]
        for x in range(len(matrix))
        for y in range(len(matrix[x]))
        if x + y > linea
    )
    return _clamp(total, 0.0, 1.0)


def prob_btts(lam_home: float, lam_away: float, rho: Optional[float] = None, max_goals: int = MAX_GOALS) -> float:
    """Both-teams-to-score probability derived from the Dixon-Coles matrix."""
    matrix = score_matrix(lam_home, lam_away, rho, max_goals)
    total = sum(
        matrix[x][y]
        for x in range(1, len(matrix))
        for y in range(1, len(matrix[x]))
    )
    return _clamp(total, 0.0, 1.0)


def expected_goals(home_form: Dict[str, float], away_form: Dict[str, float]) -> Tuple[float, float]:
    """Legacy aggregate model (kept for backward compatibility)."""
    lam_h = (home_form.get("gf", 0.0) + away_form.get("ga", 0.0)) / 2.0
    lam_a = (away_form.get("gf", 0.0) + home_form.get("ga", 0.0)) / 2.0

    lam_h = min(max(lam_h, 0.3), 4.0)
    lam_a = min(max(lam_a, 0.3), 4.0)
    return lam_h, lam_a


def _pick_side(form: Optional[Dict[str, Any]], side: str, default: Dict[str, float]) -> Dict[str, float]:
    if not form:
        return default
    value = form.get(side)
    if isinstance(value, dict) and "gf" in value and "ga" in value:
        return value
    overall = form.get("overall")
    if isinstance(overall, dict) and "gf" in overall and "ga" in overall:
        return overall
    if "gf" in form and "ga" in form:
        return form
    return default


def expected_goals_v2(
    home_form: Optional[Dict[str, Any]],
    away_form: Optional[Dict[str, Any]],
    mu_home: float = LEAGUE_AVG_HOME_GOALS,
    mu_away: float = LEAGUE_AVG_AWAY_GOALS,
) -> Tuple[float, float]:
    """Split home/away expected goals using league baselines and strength ratings."""
    h = _pick_side(home_form, "home", {"gf": mu_home, "ga": mu_away})
    a = _pick_side(away_form, "away", {"gf": mu_away, "ga": mu_home})

    att_home = h.get("gf", mu_home) / mu_home if mu_home else 1.0
    def_home = h.get("ga", mu_away) / mu_away if mu_away else 1.0
    att_away = a.get("gf", mu_away) / mu_away if mu_away else 1.0
    def_away = a.get("ga", mu_home) / mu_home if mu_home else 1.0

    lam_home = att_home * def_away * mu_home
    lam_away = att_away * def_home * mu_away

    return _clamp(lam_home, LAMBDA_MIN, LAMBDA_MAX), _clamp(lam_away, LAMBDA_MIN, LAMBDA_MAX)

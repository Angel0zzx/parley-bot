"""
Poisson probability distribution and expected goals calculations.
"""

import math
from typing import Dict, Tuple, Optional


def poisson_pmf(k: int, lam: float) -> float:
    """Calculate Poisson probability mass function for exactly k events given rate lam."""
    if lam < 0:
        return 0.0
    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except OverflowError:
        return 0.0


def prob_over(lam_total: float, linea: float) -> float:
    """Calculate probability of total goals over a given line (e.g. 1.5, 2.5, 3.5)."""
    umbral = int(linea)
    acum = sum(poisson_pmf(k, lam_total) for k in range(umbral + 1))
    return max(0.0, min(1.0, 1.0 - acum))


def prob_btts(lam_home: float, lam_away: float) -> float:
    """Calculate probability that both teams score (BTTS)."""
    p_home_0 = poisson_pmf(0, lam_home)
    p_away_0 = poisson_pmf(0, lam_away)
    return (1.0 - p_home_0) * (1.0 - p_away_0)


def expected_goals(home_form: Dict[str, float], away_form: Dict[str, float]) -> Tuple[float, float]:
    """Calculate expected goals (lambda) for home and away teams based on recent form."""
    lam_h = (home_form.get("gf", 0.0) + away_form.get("ga", 0.0)) / 2.0
    lam_a = (away_form.get("gf", 0.0) + home_form.get("ga", 0.0)) / 2.0
    
    lam_h = min(max(lam_h, 0.3), 4.0)
    lam_a = min(max(lam_a, 0.3), 4.0)
    return lam_h, lam_a

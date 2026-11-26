"""
Strategy module: pick generation, risk classification, EV filtering and parley building.
"""

from typing import Dict, List, Any, Optional
from parley.config import DIXON_COLES_RHO, MIN_EV
from parley.models.poisson import (
    expected_goals_v2,
    prob_1x2,
    prob_double_chance,
    prob_dnb,
    prob_over,
    prob_btts,
)

LINEAS_GOLES = [1.5, 2.5, 3.5]
RIESGO_SEGURO_MIN = 72.0
RIESGO_MEDIO_MIN = 62.0
RIESGO_BAJO_MIN = 48.0
MIN_PROB = 52.0
MIN_PROB_1X2 = 48.0
PROB_MAX = 95.0
PARLEY_MAX = 3


def _odds_entry_for_pick(pick: Dict[str, Any], odds: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    mercado = pick.get("mercado")
    seleccion = pick.get("seleccion", "")

    if mercado == "1X2":
        key = {"Local (1)": "home", "Empate (X)": "draw", "Visitante (2)": "away"}.get(seleccion)
        return odds.get("h2h", {}).get(key) if key else None

    if mercado == "Doble Oportunidad":
        if seleccion.startswith("1X"):
            key = "1X"
        elif seleccion.startswith("X2"):
            key = "X2"
        else:
            key = None
        return odds.get("dc", {}).get(key) if key else None

    if mercado == "DNB":
        if seleccion.startswith("Local"):
            key = "home"
        elif seleccion.startswith("Visitante"):
            key = "away"
        else:
            key = None
        return odds.get("dnb", {}).get(key) if key else None

    if mercado == "Goles":
        parts = seleccion.split()
        if len(parts) == 2:
            side = parts[0].lower()
            try:
                linea = float(parts[1])
            except ValueError:
                return None
            return odds.get("totals", {}).get(linea, {}).get(side)

    return None


def attach_odds(pick: Dict[str, Any], odds: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach real/derived odds to a pick when available."""
    if not odds:
        return pick
    entry = _odds_entry_for_pick(pick, odds)
    if entry and entry.get("cuota"):
        pick["cuota_real"] = float(entry["cuota"])
        pick["casa"] = entry.get("casa")
        pick["derivada"] = bool(entry.get("derivada"))
    return pick


def filter_by_ev(picks: List[Dict[str, Any]], min_ev: Optional[float] = None) -> List[Dict[str, Any]]:
    """Compute EV/edge and keep picks with real odds only when EV > min_ev."""
    min_ev = MIN_EV if min_ev is None else min_ev
    kept: List[Dict[str, Any]] = []
    for pick in picks:
        cuota = pick.get("cuota_real")
        if cuota:
            prob = pick["prob"] / 100.0
            ev = prob * cuota - 1.0
            edge = prob - (1.0 / cuota)
            pick["ev"] = ev
            pick["edge"] = edge
            if ev > min_ev:
                kept.append(pick)
        else:
            pick["ev"] = None
            pick["edge"] = None
            kept.append(pick)
    return kept


def generar_picks(
    partido: Dict[str, Any],
    home_form: Optional[Dict[str, Any]],
    away_form: Optional[Dict[str, Any]],
    rho: Optional[float] = None,
    odds: Optional[Dict[str, Any]] = None,
    min_ev: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Generate picks for all v2.0 markets from the Dixon-Coles model."""
    if not home_form or not away_form:
        return []

    rho = DIXON_COLES_RHO if rho is None else rho
    lam_h, lam_a = expected_goals_v2(home_form, away_form)

    picks: List[Dict[str, Any]] = []
    partido_str = f"{partido.get('home', '?')} vs {partido.get('away', '?')}"
    liga = partido.get("liga", "?")
    kickoff = partido.get("kickoff")

    def add(prob_fraction: float, seleccion: str, mercado: str, min_prob: float) -> None:
        pct = prob_fraction * 100.0
        if min_prob <= pct <= PROB_MAX:
            picks.append({
                "partido": partido_str,
                "liga": liga,
                "fixture_id": partido.get("id"),
                "tier": clasificar_riesgo(pct),
                "seleccion": seleccion,
                "mercado": mercado,
                "prob": pct,
                "cuota_justa": (1.0 / prob_fraction) if prob_fraction > 0 else 0.0,
                "cuota_real": None,
                "casa": None,
                "derivada": False,
                "ev": None,
                "edge": None,
                "kickoff": kickoff,
            })

    p_1x2 = prob_1x2(lam_h, lam_a, rho)
    add(p_1x2["home"], "Local (1)", "1X2", MIN_PROB_1X2)
    add(p_1x2["draw"], "Empate (X)", "1X2", MIN_PROB_1X2)
    add(p_1x2["away"], "Visitante (2)", "1X2", MIN_PROB_1X2)

    p_dc = prob_double_chance(lam_h, lam_a, rho)
    add(p_dc["1X"], "1X (Local o Empate)", "Doble Oportunidad", MIN_PROB)
    add(p_dc["X2"], "X2 (Empate o Visitante)", "Doble Oportunidad", MIN_PROB)

    p_dnb = prob_dnb(lam_h, lam_a, rho)
    add(p_dnb["home"], "Local DNB", "DNB", MIN_PROB)
    add(p_dnb["away"], "Visitante DNB", "DNB", MIN_PROB)

    for linea in LINEAS_GOLES:
        p_over = prob_over(lam_h, linea, lam_away=lam_a, rho=rho)
        p_under = 1.0 - p_over
        add(p_over, f"Over {linea}", "Goles", MIN_PROB)
        add(p_under, f"Under {linea}", "Goles", MIN_PROB)

    p_btts = prob_btts(lam_h, lam_a, rho=rho)
    add(p_btts, "Ambos anotan: SÍ", "BTTS", MIN_PROB)

    if odds:
        for pick in picks:
            attach_odds(pick, odds)

    return filter_by_ev(picks, min_ev)


def clasificar_riesgo(prob: float) -> Optional[str]:
    """Classify risk level based on percentage probability."""
    if prob >= RIESGO_SEGURO_MIN:
        return "seguro"
    if prob >= RIESGO_MEDIO_MIN:
        return "medio"
    if prob >= RIESGO_BAJO_MIN:
        return "arriesgado"
    return None


def tomar_mejores(candidatos: List[Dict[str, Any]], max_sel: int = PARLEY_MAX) -> List[Dict[str, Any]]:
    """Select best picks ensuring no duplicate matches within the same parley."""
    ordenados = sorted(candidatos, key=lambda x: -x["prob"])
    seleccion = []
    partidos = set()
    for p in ordenados:
        if p["partido"] in partidos:
            continue
        seleccion.append(p)
        partidos.add(p["partido"])
        if len(seleccion) >= max_sel:
            break
    return seleccion


def armar_parleys(picks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Build parleys categorized by risk level."""
    por_riesgo = {"seguro": [], "medio": [], "arriesgado": []}
    for p in picks:
        nivel = clasificar_riesgo(p["prob"])
        if nivel:
            p["riesgo"] = nivel
            por_riesgo[nivel].append(p)
    return {nivel: tomar_mejores(lista) for nivel, lista in por_riesgo.items()}


def prob_conjunta(parley: List[Dict[str, Any]]) -> float:
    """Calculate combined probability percentage for a parley."""
    if not parley:
        return 0.0
    p = 1.0
    for x in parley:
        p *= x["prob"] / 100.0
    return p * 100.0


def cuota_conjunta(parley: List[Dict[str, Any]]) -> float:
    """Calculate combined fair odds for a parley."""
    if not parley:
        return 0.0
    c = 1.0
    for x in parley:
        if x["cuota_justa"] > 0:
            c *= x["cuota_justa"]
    return c

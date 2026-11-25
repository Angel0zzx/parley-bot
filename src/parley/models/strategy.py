"""
Strategy module: pick generation, risk classification, and parley building.
"""

from typing import Dict, List, Any, Optional
from parley.models.poisson import expected_goals, prob_over, prob_btts

LINEAS_GOLES = [1.5, 2.5, 3.5]
RIESGO_SEGURO_MIN = 72.0
RIESGO_MEDIO_MIN = 62.0
RIESGO_BAJO_MIN = 52.0
PROB_MAX = 95.0
PARLEY_MAX = 3


def generar_picks(partido: Dict[str, Any], home_form: Optional[Dict[str, float]], away_form: Optional[Dict[str, float]]) -> List[Dict[str, Any]]:
    """Generate betting picks for a match based on expected goals and Poisson probabilities."""
    if not home_form or not away_form:
        return []

    lam_h, lam_a = expected_goals(home_form, away_form)
    lam_total = lam_h + lam_a

    picks = []
    partido_str = f"{partido.get('home', '?')} vs {partido.get('away', '?')}"
    liga = partido.get("liga", "?")
    kickoff = partido.get("kickoff")

    for linea in LINEAS_GOLES:
        p_over = prob_over(lam_total, linea)
        p_under = 1.0 - p_over

        if RIESGO_BAJO_MIN <= p_over * 100 <= PROB_MAX:
            picks.append({
                "partido": partido_str,
                "liga": liga,
                "seleccion": f"Over {linea}",
                "mercado": "Goles",
                "prob": p_over * 100,
                "cuota_justa": 1 / p_over if p_over > 0 else 0,
                "kickoff": kickoff,
            })

        if RIESGO_BAJO_MIN <= p_under * 100 <= PROB_MAX:
            picks.append({
                "partido": partido_str,
                "liga": liga,
                "seleccion": f"Under {linea}",
                "mercado": "Goles",
                "prob": p_under * 100,
                "cuota_justa": 1 / p_under if p_under > 0 else 0,
                "kickoff": kickoff,
            })

    p_btts = prob_btts(lam_h, lam_a)
    if RIESGO_BAJO_MIN <= p_btts * 100 <= PROB_MAX:
        picks.append({
            "partido": partido_str,
            "liga": liga,
            "seleccion": "Ambos anotan: SÍ",
            "mercado": "BTTS",
            "prob": p_btts * 100,
            "cuota_justa": 1 / p_btts if p_btts > 0 else 0,
            "kickoff": kickoff,
        })

    return picks


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

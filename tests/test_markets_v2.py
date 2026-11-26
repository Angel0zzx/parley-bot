"""
Tests for the expanded v2.0 market set and thresholds.
"""

from parley.models.strategy import (
    generar_picks,
    MIN_PROB,
    MIN_PROB_1X2,
)


def _form(home_gf, home_ga, away_gf, away_ga, n=8):
    return {
        "home": {"gf": home_gf, "ga": home_ga, "n": n},
        "away": {"gf": away_gf, "ga": away_ga, "n": n},
        "overall": {"gf": (home_gf + away_gf) / 2, "ga": (home_ga + away_ga) / 2, "n": n * 2},
        "n": n * 2,
    }


def test_new_markets_and_backward_compatible_fields():
    partido = {"home": "Strong", "away": "Weak", "liga": "Test", "kickoff": None}
    home_form = _form(2.2, 1.2, 0.0, 0.0)
    away_form = _form(0.0, 0.0, 1.0, 1.5)

    picks = generar_picks(partido, home_form, away_form)
    mercados = {p["mercado"] for p in picks}

    assert {"1X2", "Doble Oportunidad", "DNB", "Goles", "BTTS"} <= mercados
    assert all(p["cuota_real"] is None and p["ev"] is None for p in picks)
    assert all(48.0 <= p["prob"] <= 95.0 for p in picks)
    assert all(52.0 <= p["prob"] <= 95.0 for p in picks if p["mercado"] != "1X2")


def test_thresholds():
    assert MIN_PROB_1X2 == 48.0
    assert MIN_PROB == 52.0


def test_no_picks_without_form():
    assert generar_picks({"home": "A", "away": "B"}, None, None) == []

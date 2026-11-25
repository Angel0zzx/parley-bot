"""
Unit tests for strategy, pick generation, and parley building.
"""

import pytest
from parley.models.strategy import (
    generar_picks,
    clasificar_riesgo,
    tomar_mejores,
    armar_parleys,
    prob_conjunta,
    cuota_conjunta,
)


def test_clasificar_riesgo():
    assert clasificar_riesgo(75.0) == "seguro"
    assert clasificar_riesgo(65.0) == "medio"
    assert clasificar_riesgo(55.0) == "arriesgado"
    assert clasificar_riesgo(40.0) is None


def test_generar_picks_empty_form():
    partido = {"home": "A", "away": "B", "liga": "Test"}
    picks = generar_picks(partido, None, None)
    assert picks == []


def test_tomar_mejores_no_duplicate_matches():
    picks = [
        {"partido": "Team A vs Team B", "prob": 80.0, "seleccion": "Over 2.5", "cuota_justa": 1.25},
        {"partido": "Team A vs Team B", "prob": 85.0, "seleccion": "Over 1.5", "cuota_justa": 1.18},
        {"partido": "Team C vs Team D", "prob": 78.0, "seleccion": "Over 2.5", "cuota_justa": 1.28},
    ]
    mejores = tomar_mejores(picks, max_sel=3)
    # Should pick Team A vs Team B (prob 85), then Team C vs Team D (prob 78), avoiding second pick from Team A vs Team B
    assert len(mejores) == 2
    assert mejores[0]["seleccion"] == "Over 1.5"
    assert mejores[1]["partido"] == "Team C vs Team D"


def test_parleys_calculations():
    parley = [
        {"prob": 80.0, "cuota_justa": 1.25},
        {"prob": 50.0, "cuota_justa": 2.0},
    ]
    assert pytest.approx(prob_conjunta(parley), 0.01) == 40.0
    assert pytest.approx(cuota_conjunta(parley), 0.01) == 2.5

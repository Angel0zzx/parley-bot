"""
Tests for the nightly audit: market evaluation, NULA handling and ROI.
"""

import pytest

from parley.audit import evaluar_pick
from parley.db import repository


@pytest.mark.parametrize(
    "seleccion,home_goals,away_goals,esperado",
    [
        ("Local (1)", 2, 0, "GANADA"),
        ("Local (1)", 1, 1, "PERDIDA"),
        ("Empate (X)", 1, 1, "GANADA"),
        ("Empate (X)", 2, 1, "PERDIDA"),
        ("Visitante (2)", 0, 2, "GANADA"),
        ("Visitante (2)", 2, 2, "PERDIDA"),
    ],
)
def test_evaluar_1x2(seleccion, home_goals, away_goals, esperado):
    assert evaluar_pick("1X2", seleccion, home_goals, away_goals) == esperado


@pytest.mark.parametrize(
    "seleccion,home_goals,away_goals,esperado",
    [
        ("1X (Local o Empate)", 2, 0, "GANADA"),
        ("1X (Local o Empate)", 1, 1, "GANADA"),
        ("1X (Local o Empate)", 0, 1, "PERDIDA"),
        ("X2 (Empate o Visitante)", 0, 1, "GANADA"),
        ("X2 (Empate o Visitante)", 1, 1, "GANADA"),
        ("X2 (Empate o Visitante)", 1, 0, "PERDIDA"),
    ],
)
def test_evaluar_doble_oportunidad(seleccion, home_goals, away_goals, esperado):
    assert evaluar_pick("Doble Oportunidad", seleccion, home_goals, away_goals) == esperado


def test_evaluar_dnb_draw_is_nula():
    assert evaluar_pick("DNB", "Local DNB", 1, 1) == "NULA"
    assert evaluar_pick("DNB", "Visitante DNB", 2, 2) == "NULA"


@pytest.mark.parametrize(
    "seleccion,home_goals,away_goals,esperado",
    [
        ("Local DNB", 2, 0, "GANADA"),
        ("Local DNB", 0, 2, "PERDIDA"),
        ("Visitante DNB", 0, 2, "GANADA"),
        ("Visitante DNB", 2, 0, "PERDIDA"),
    ],
)
def test_evaluar_dnb(seleccion, home_goals, away_goals, esperado):
    assert evaluar_pick("DNB", seleccion, home_goals, away_goals) == esperado


@pytest.mark.parametrize(
    "seleccion,home_goals,away_goals,esperado",
    [
        ("Over 2.5", 2, 1, "GANADA"),
        ("Over 2.5", 1, 1, "PERDIDA"),
        ("Under 2.5", 1, 1, "GANADA"),
        ("Under 2.5", 2, 1, "PERDIDA"),
        ("Over 1.5", 1, 0, "PERDIDA"),
        ("Under 1.5", 1, 0, "GANADA"),
    ],
)
def test_evaluar_goles(seleccion, home_goals, away_goals, esperado):
    assert evaluar_pick("Goles", seleccion, home_goals, away_goals) == esperado


def test_evaluar_goles_push_is_nula():
    assert evaluar_pick("Goles", "Over 3.0", 2, 1) == "NULA"


@pytest.mark.parametrize(
    "seleccion,home_goals,away_goals,esperado",
    [
        ("Ambos anotan: SÍ", 1, 1, "GANADA"),
        ("Ambos anotan: SÍ", 1, 0, "PERDIDA"),
        ("Ambos anotan: NO", 1, 0, "GANADA"),
        ("Ambos anotan: NO", 2, 2, "PERDIDA"),
    ],
)
def test_evaluar_btts(seleccion, home_goals, away_goals, esperado):
    assert evaluar_pick("BTTS", seleccion, home_goals, away_goals) == esperado


def test_evaluar_unsupported_market():
    assert evaluar_pick("Otro", "X", 1, 0) is None


def test_roi_calculation():
    rows = [
        {"estado": "GANADA", "cuota": 2.0},
        {"estado": "GANADA", "cuota": 1.5},
        {"estado": "PERDIDA", "cuota": 2.0},
        {"estado": "NULA", "cuota": 1.8},
    ]

    stats = repository.calcular_stats(rows)

    assert stats["total"] == 3
    assert stats["ganadas"] == 2
    assert stats["perdidas"] == 1
    assert stats["nulas"] == 1
    assert stats["acierto_pct"] == pytest.approx(200.0 / 3.0)
    assert stats["roi_pct"] == pytest.approx(50.0 / 3.0)


def test_roi_empty():
    stats = repository.calcular_stats([])
    assert stats["total"] == 0
    assert stats["acierto_pct"] == 0.0
    assert stats["roi_pct"] == 0.0


def test_save_predictions_without_database_url():
    picks = [{"fixture_id": "1", "mercado": "1X2", "seleccion": "Local (1)", "prob": 60.0}]
    assert repository.save_predictions(picks, "2026-11-26", database_url="") == 0

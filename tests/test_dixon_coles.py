"""
Unit tests for the Dixon-Coles score matrix and derived markets.
"""

import pytest

from parley.models.poisson import (
    poisson_pmf,
    score_matrix,
    prob_1x2,
    prob_double_chance,
    prob_dnb,
    prob_over,
    prob_btts,
    expected_goals_v2,
)


def _independent_matrix(lam_h: float, lam_a: float, max_goals: int = 10):
    sx = sum(poisson_pmf(x, lam_h) for x in range(max_goals + 1))
    sy = sum(poisson_pmf(y, lam_a) for y in range(max_goals + 1))
    return [
        [poisson_pmf(x, lam_h) * poisson_pmf(y, lam_a) / (sx * sy) for y in range(max_goals + 1)]
        for x in range(max_goals + 1)
    ]


def test_score_matrix_sums_to_one():
    matrix = score_matrix(1.6, 1.2, rho=-0.10)
    assert pytest.approx(sum(sum(row) for row in matrix), abs=1e-9) == 1.0


def test_matrix_equals_independent_poisson_when_rho_zero():
    lam_h, lam_a = 1.4, 1.1
    matrix = score_matrix(lam_h, lam_a, rho=0.0)
    expected = _independent_matrix(lam_h, lam_a)
    for x in range(11):
        for y in range(11):
            assert matrix[x][y] == pytest.approx(expected[x][y], abs=1e-12)


def test_dixon_coles_increases_low_draws():
    lam_h, lam_a = 1.3, 1.1
    base = score_matrix(lam_h, lam_a, rho=0.0)
    adjusted = score_matrix(lam_h, lam_a, rho=-0.15)
    assert adjusted[0][0] > base[0][0]
    assert adjusted[1][1] > base[1][1]


def test_prob_1x2_sums_to_one():
    p = prob_1x2(1.5, 1.2, rho=-0.10)
    assert pytest.approx(p["home"] + p["draw"] + p["away"], abs=1e-9) == 1.0


def test_double_chance_and_dnb():
    lam_h, lam_a = 1.5, 1.2
    p = prob_1x2(lam_h, lam_a, rho=-0.10)
    dc = prob_double_chance(lam_h, lam_a, rho=-0.10)
    dnb = prob_dnb(lam_h, lam_a, rho=-0.10)

    assert dc["1X"] == pytest.approx(p["home"] + p["draw"])
    assert dc["X2"] == pytest.approx(p["draw"] + p["away"])
    assert dnb["home"] == pytest.approx(p["home"] / (p["home"] + p["away"]))
    assert dnb["home"] + dnb["away"] == pytest.approx(1.0)


def test_prob_over_and_btts_come_from_matrix():
    lam_h, lam_a = 1.5, 1.2
    matrix = score_matrix(lam_h, lam_a, rho=-0.10)
    over = sum(matrix[x][y] for x in range(11) for y in range(11) if x + y > 2.5)
    btts = sum(matrix[x][y] for x in range(1, 11) for y in range(1, 11))

    assert prob_over(lam_h, 2.5, lam_away=lam_a, rho=-0.10) == pytest.approx(over)
    assert prob_btts(lam_h, lam_a, rho=-0.10) == pytest.approx(btts)


def test_expected_goals_v2_uses_split_form():
    home_form = {
        "home": {"gf": 2.4, "ga": 0.5, "n": 8},
        "away": {"gf": 1.0, "ga": 1.8, "n": 8},
        "overall": {"gf": 1.7, "ga": 1.15, "n": 16},
        "n": 16,
    }
    away_form = {
        "home": {"gf": 1.5, "ga": 1.0, "n": 8},
        "away": {"gf": 0.8, "ga": 2.0, "n": 8},
        "overall": {"gf": 1.15, "ga": 1.5, "n": 16},
        "n": 16,
    }

    lam_h, lam_a = expected_goals_v2(home_form, away_form)
    assert lam_h > lam_a
    assert 0.2 <= lam_h <= 4.5
    assert 0.2 <= lam_a <= 4.5


def test_expected_goals_v2_accepts_legacy_flat_form():
    lam_h, lam_a = expected_goals_v2({"gf": 2.0, "ga": 1.0}, {"gf": 1.0, "ga": 2.0})
    assert lam_h > lam_a

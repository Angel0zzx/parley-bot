"""
Unit tests for Poisson model functions.
"""

import pytest
from parley.models.poisson import poisson_pmf, prob_over, prob_btts, expected_goals


def test_poisson_pmf():
    # PMF for k=0, lambda=1.5 should be exp(-1.5)
    val = poisson_pmf(0, 1.5)
    assert pytest.approx(val, 0.001) == 0.2231

    # Negative lambda should return 0.0
    assert poisson_pmf(2, -1.0) == 0.0


def test_prob_over():
    p = prob_over(2.5, 2.5)
    assert 0.0 <= p <= 1.0


def test_prob_btts():
    p = prob_btts(1.5, 1.2)
    assert 0.0 <= p <= 1.0


def test_expected_goals_edge_cases():
    # Test clamping limits [0.3, 4.0]
    hf = {"gf": 0.0, "ga": 0.0}
    af = {"gf": 0.0, "ga": 0.0}
    lam_h, lam_a = expected_goals(hf, af)
    assert lam_h == 0.3
    assert lam_a == 0.3

    hf_high = {"gf": 10.0, "ga": 10.0}
    af_high = {"gf": 10.0, "ga": 10.0}
    lam_h, lam_a = expected_goals(hf_high, af_high)
    assert lam_h == 4.0
    assert lam_a == 4.0

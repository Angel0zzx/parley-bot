"""
Tests for home/away form split and shrinkage fallback in providers.
"""

import pytest
from unittest.mock import patch, MagicMock

from parley.config import (
    LEAGUE_AVG_HOME_GOALS,
    LEAGUE_AVG_AWAY_GOALS,
    SHRINKAGE_K,
)
from parley.providers.football_data import FootballDataProvider


@patch("parley.providers.football_data.save_cache")
@patch("parley.providers.football_data.time.sleep", return_value=None)
@patch("parley.providers.football_data.requests.get")
def test_football_data_split_form_and_shrinkage(mock_get, mock_sleep, mock_save_cache):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "matches": [
            {"utcDate": "2026-05-01T15:00:00Z", "score": {"fullTime": {"home": 2, "away": 1}},
             "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 2, "name": "B"}},
            {"utcDate": "2026-05-02T15:00:00Z", "score": {"fullTime": {"home": 3, "away": 0}},
             "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 3, "name": "C"}},
            {"utcDate": "2026-05-03T15:00:00Z", "score": {"fullTime": {"home": 1, "away": 1}},
             "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 4, "name": "D"}},
            {"utcDate": "2026-05-04T15:00:00Z", "score": {"fullTime": {"home": 0, "away": 2}},
             "homeTeam": {"id": 5, "name": "E"}, "awayTeam": {"id": 1, "name": "A"}},
        ]
    }
    mock_get.return_value = resp

    provider = FootballDataProvider("fake_key")
    form = provider.get_team_form(1, {"form": {}})

    assert form["n"] == 4
    assert form["home"]["n"] == 3
    assert form["away"]["n"] == 1

    # Enough home sample -> raw averages
    assert form["home"]["gf"] == pytest.approx(2.0)
    assert form["home"]["ga"] == pytest.approx((1 + 0 + 1) / 3)

    # Small away sample -> shrunk toward the league baselines
    expected_away_gf = (1 * 2.0 + SHRINKAGE_K * LEAGUE_AVG_AWAY_GOALS) / (1 + SHRINKAGE_K)
    expected_away_ga = (1 * 0.0 + SHRINKAGE_K * LEAGUE_AVG_HOME_GOALS) / (1 + SHRINKAGE_K)
    assert form["away"]["gf"] == pytest.approx(expected_away_gf)
    assert form["away"]["ga"] == pytest.approx(expected_away_ga)

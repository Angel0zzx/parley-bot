"""
Unit tests for providers with HTTP response mocking (rate limits, null scores) and mocked time.sleep.
"""

import pytest
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from parley.providers.football_data import FootballDataProvider
from parley.providers.bzzoiro import BzzoiroProvider


@patch("parley.providers.football_data.time.sleep", return_value=None)
@patch("parley.providers.football_data.requests.get")
def test_football_data_rate_limit_and_null_scores(mock_get, mock_sleep):
    # Mock response sequence: 429 then 200 OK
    resp_429 = MagicMock()
    resp_429.status_code = 429

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "matches": [
            {
                "utcDate": "2026-06-01T15:00:00Z",
                "score": {"fullTime": {"home": None, "away": None}},
                "homeTeam": {"id": 1, "name": "Team A"},
                "awayTeam": {"id": 2, "name": "Team B"},
            },
            {
                "utcDate": "2026-05-01T15:00:00Z",
                "score": {"fullTime": {"home": 2, "away": 1}},
                "homeTeam": {"id": 1, "name": "Team A"},
                "awayTeam": {"id": 3, "name": "Team C"},
            },
            {
                "utcDate": "2026-05-02T15:00:00Z",
                "score": {"fullTime": {"home": 1, "away": 1}},
                "homeTeam": {"id": 4, "name": "Team D"},
                "awayTeam": {"id": 1, "name": "Team A"},
            },
            {
                "utcDate": "2026-05-03T15:00:00Z",
                "score": {"fullTime": {"home": 3, "away": 0}},
                "homeTeam": {"id": 1, "name": "Team A"},
                "awayTeam": {"id": 5, "name": "Team E"},
            }
        ]
    }

    mock_get.side_effect = [resp_429, resp_200]

    provider = FootballDataProvider("fake_key")
    cache = {"form": {}}
    
    form = provider.get_team_form(1, cache)
    assert form is not None
    assert form["n"] == 3


@patch("parley.providers.bzzoiro.time.sleep", return_value=None)
@patch("parley.providers.bzzoiro.requests.get")
def test_bzzoiro_provider(mock_get, mock_sleep):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "results": [
            {
                "id": 100,
                "event_date": "2026-06-01T18:00:00Z",
                "status": "notstarted",
                "home_team_id": 10,
                "home_team": "Boca",
                "away_team_id": 20,
                "away_team": "River",
            }
        ]
    }
    mock_get.return_value = resp

    provider = BzzoiroProvider("fake_key")
    tz = ZoneInfo("America/Guayaquil")
    matches = provider.get_matches("2026-06-01", tz, solo_futuros=False)
    assert len(matches) == 1
    assert matches[0]["home"] == "Boca"

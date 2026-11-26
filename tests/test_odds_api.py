"""
Tests for The Odds API client: matching, best odds, derivations, cache and EV filter.
"""

from datetime import datetime, timezone

import pytest

from parley.models.strategy import attach_odds, filter_by_ev
from parley.providers import odds_api
from parley.providers.odds_api import (
    OddsApiClient,
    best_h2h,
    best_totals,
    build_event_odds,
    derive_dnb,
    derive_double_chance,
    match_event,
    normalize_team,
)


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"x-requests-remaining": "499"}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload


def _event(home="Manchester City", away="Arsenal", commence="2026-11-26T18:00:00Z", bookmakers=None):
    return {
        "home_team": home,
        "away_team": away,
        "commence_time": commence,
        "bookmakers": bookmakers or [],
    }


def _bookmaker(title, h2h=None, totals=None):
    markets = []
    if h2h:
        markets.append({"key": "h2h", "outcomes": [{"name": n, "price": p} for n, p in h2h]})
    if totals:
        markets.append({
            "key": "totals",
            "outcomes": [{"name": n, "price": p, "point": pt} for n, p, pt in totals],
        })
    return {"title": title, "markets": markets}


def _pick(prob=60.0, **extra):
    data = {"prob": prob, "cuota_real": None, "ev": None, "edge": None}
    data.update(extra)
    return data


def test_normalize_team():
    assert normalize_team("Manchester City FC") == "manchester city"
    assert normalize_team("Atlético de Madrid") == "atletico de madrid"


def test_match_event_by_name_and_kickoff():
    partido = {
        "home": "Manchester City FC",
        "away": "Arsenal",
        "kickoff": datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc),
    }
    event = _event()
    assert match_event(partido, [event]) is event


def test_match_event_rejects_far_kickoff_and_different_teams():
    partido = {
        "home": "Manchester City",
        "away": "Arsenal",
        "kickoff": datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc),
    }
    far = _event(commence="2026-11-27T18:00:00Z")
    other = _event(home="Chelsea", away="Arsenal")
    assert match_event(partido, [far, other]) is None


def test_best_h2h_and_totals_across_bookmakers():
    event = _event(bookmakers=[
        _bookmaker(
            "Book A",
            h2h=[("Manchester City", 2.0), ("Draw", 3.4), ("Arsenal", 4.0)],
            totals=[("Over", 1.9, 2.5), ("Under", 1.9, 2.5)],
        ),
        _bookmaker(
            "Book B",
            h2h=[("Manchester City", 2.2), ("Draw", 3.2), ("Arsenal", 4.2)],
            totals=[("Over", 2.0, 2.5), ("Under", 1.8, 2.5)],
        ),
    ])
    h2h = best_h2h(event)
    assert h2h["home"]["cuota"] == 2.2
    assert h2h["home"]["casa"] == "Book B"
    assert h2h["draw"]["cuota"] == 3.4
    assert h2h["draw"]["casa"] == "Book A"
    assert h2h["away"]["cuota"] == 4.2
    assert h2h["away"]["casa"] == "Book B"

    totals = best_totals(event)
    assert totals[2.5]["over"]["cuota"] == 2.0
    assert totals[2.5]["over"]["casa"] == "Book B"
    assert totals[2.5]["under"]["cuota"] == 1.9
    assert totals[2.5]["under"]["casa"] == "Book A"


def test_derived_double_chance_and_dnb():
    h2h = {
        "home": {"cuota": 2.0},
        "draw": {"cuota": 4.0},
        "away": {"cuota": 5.0},
    }
    dc = derive_double_chance(h2h)
    assert dc["1X"]["derivada"] is True
    assert dc["1X"]["cuota"] == pytest.approx(1 / (1 / 2.0 + 1 / 4.0))
    assert dc["X2"]["cuota"] == pytest.approx(1 / (1 / 4.0 + 1 / 5.0))

    dnb = derive_dnb(h2h)
    assert dnb["home"]["derivada"] is True
    assert dnb["home"]["cuota"] == pytest.approx(2.0 * (1 - 1 / 4.0))
    assert dnb["away"]["cuota"] == pytest.approx(5.0 * (1 - 1 / 4.0))


def test_build_event_odds_payload():
    event = _event(bookmakers=[
        _bookmaker(
            "Book",
            h2h=[("Manchester City", 2.0), ("Draw", 4.0), ("Arsenal", 5.0)],
            totals=[("Over", 1.9, 2.5), ("Under", 1.9, 2.5)],
        ),
    ])
    odds = build_event_odds(event)
    assert odds["h2h"]["home"]["derivada"] is False
    assert odds["dc"]["1X"]["derivada"] is True
    assert odds["dnb"]["home"]["derivada"] is True
    assert 2.5 in odds["totals"]


def test_client_without_key_returns_empty(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("requests.get should not be called without a key")

    monkeypatch.setattr(odds_api.requests, "get", boom)
    client = OddsApiClient(api_key="")
    assert client.enabled is False
    assert client.get_odds_for_matches([{"id": 1, "liga_code": "PL"}]) == {}


def test_client_caches_events(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _FakeResponse([_event()])

    monkeypatch.setattr(odds_api.requests, "get", fake_get)
    monkeypatch.setattr(odds_api, "save_cache", lambda cache: None)

    client = OddsApiClient(api_key="test")
    cache = {}
    first = client._get_events("soccer_epl", cache)
    second = client._get_events("soccer_epl", cache)
    assert first == second
    assert len(calls) == 1
    assert cache["odds"]["soccer_epl"]["events"] == first


def test_filter_by_ev_keeps_positive_and_model_only():
    positive = _pick(prob=60.0, cuota_real=2.0)
    negative = _pick(prob=50.0, cuota_real=1.5)
    model_only = _pick(prob=55.0)

    kept = filter_by_ev([positive, negative, model_only], min_ev=0.0)

    assert positive in kept
    assert model_only in kept
    assert negative not in kept
    assert positive["ev"] == pytest.approx(0.2)
    assert positive["edge"] == pytest.approx(0.1)
    assert model_only["ev"] is None


def test_filter_by_ev_respects_threshold():
    pick = _pick(prob=60.0, cuota_real=2.0)
    assert filter_by_ev([pick], min_ev=0.25) == []


def test_attach_odds_maps_all_supported_markets():
    odds = {
        "h2h": {"home": {"cuota": 2.1, "casa": "Book", "derivada": False}},
        "dc": {"1X": {"cuota": 1.3, "casa": "derivada", "derivada": True}},
        "dnb": {"home": {"cuota": 1.7, "casa": "derivada", "derivada": True}},
        "totals": {2.5: {"over": {"cuota": 1.9, "casa": "Book", "derivada": False}}},
    }

    pick = attach_odds({"mercado": "1X2", "seleccion": "Local (1)", "cuota_real": None}, odds)
    assert pick["cuota_real"] == 2.1
    assert pick["derivada"] is False

    pick = attach_odds({"mercado": "Doble Oportunidad", "seleccion": "1X (Local o Empate)", "cuota_real": None}, odds)
    assert pick["cuota_real"] == 1.3
    assert pick["derivada"] is True

    pick = attach_odds({"mercado": "DNB", "seleccion": "Local DNB", "cuota_real": None}, odds)
    assert pick["cuota_real"] == 1.7
    assert pick["derivada"] is True

    pick = attach_odds({"mercado": "Goles", "seleccion": "Over 2.5", "cuota_real": None}, odds)
    assert pick["cuota_real"] == 1.9
    assert pick["derivada"] is False

    pick = attach_odds({"mercado": "BTTS", "seleccion": "Ambos anotan: SÍ", "cuota_real": None}, odds)
    assert pick["cuota_real"] is None

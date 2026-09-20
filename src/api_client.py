import requests
import json
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Outcome:
    name: str
    price: float # Decimal odds
    point: Optional[float] = None # For spreads/totals

@dataclass
class Market:
    key: str # e.g. 'h2h', 'spreads', 'totals'
    outcomes: List[Outcome]

@dataclass
class Bookmaker:
    key: str
    title: str
    last_update: str
    markets: List[Market]

@dataclass
class Event:
    id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: str
    bookmakers: List[Bookmaker]

import os

class OddsAPIClient:
    """
    Client for The-Odds-API (https://the-odds-api.com/).
    """
    BASE_URL = "https://api.the-odds-api.com/v4/sports"

    def __init__(self, api_key: str = None, use_mock: bool = False):
        self.api_key = api_key or os.environ.get("ODDS_API_KEY")
        self.use_mock = use_mock

    @property
    def is_mock(self) -> bool:
        return bool(self.use_mock or not self.api_key)

    def get_odds(self, sport: str = "upcoming", regions: str = "us", markets: str = "h2h") -> List[Event]:
        if self.use_mock or not self.api_key:
            if not self.use_mock:
                print("WARNING: No API key provided. Falling back to mock data.")
            return self._get_mock_data()

        url = f"{self.BASE_URL}/{sport}/odds/"
        params = {
            "api_key": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        return self._parse_events(data)

    def get_match_results(self, sport: str = None, daysFrom: int = 3, event_ids: Optional[List[str]] = None) -> Dict:
        """
        Fetches match results to settle pending trades.
        Returns a dict mapping event_id to its completed status and scores.

        The Odds API scores endpoint requires a real sport key (not "upcoming").
        """
        if self.use_mock or not self.api_key:
            scores = self._get_mock_scores()
            if event_ids:
                wanted = set(event_ids)
                return {k: v for k, v in scores.items() if k in wanted}
            return scores

        if not sport or sport == "upcoming":
            raise ValueError("A specific sport key is required to fetch scores")

        url = f"{self.BASE_URL}/{sport}/scores/"
        params = {
            "api_key": self.api_key,
            "daysFrom": daysFrom,
        }
        if event_ids:
            params["eventIds"] = ",".join(event_ids)

        response = requests.get(url, params=params)
        response.raise_for_status()

        results = {}
        for event in response.json():
            results[event["id"]] = {
                "completed": event.get("completed", False),
                "scores": event.get("scores") or [],
            }
        return results

    def _parse_events(self, data: List[Dict]) -> List[Event]:
        events = []
        for e in data:
            bookmakers = []
            for b in e.get("bookmakers", []):
                markets = []
                for m in b.get("markets", []):
                    outcomes = [
                        Outcome(name=o["name"], price=o["price"], point=o.get("point"))
                        for o in m.get("outcomes", [])
                    ]
                    markets.append(Market(key=m["key"], outcomes=outcomes))
                
                bookmakers.append(Bookmaker(
                    key=b["key"],
                    title=b["title"],
                    last_update=b["last_update"],
                    markets=markets
                ))

            event = Event(
                id=e["id"],
                sport_key=e["sport_key"],
                home_team=e["home_team"],
                away_team=e["away_team"],
                commence_time=e["commence_time"],
                bookmakers=bookmakers
            )
            events.append(event)
        return events

    def _get_mock_data(self) -> List[Event]:
        """
        Returns mock data demonstrating an arbitrage opportunity.
        DraftKings has Team A at 2.10, FanDuel has Team B at 2.05
        Implied probability = 1/2.10 + 1/2.05 = 0.476 + 0.487 = 0.963 (Arbitrage!)
        """
        mock_json = [
            {
                "id": "mock_game_1",
                "sport_key": "basketball_nba",
                "home_team": "Los Angeles Lakers",
                "away_team": "Golden State Warriors",
                "commence_time": "2026-10-24T00:00:00Z",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "title": "DraftKings",
                        "last_update": "2026-09-14T12:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Los Angeles Lakers", "price": 2.10},
                                    {"name": "Golden State Warriors", "price": 1.75}
                                ]
                            }
                        ]
                    },
                    {
                        "key": "fanduel",
                        "title": "FanDuel",
                        "last_update": "2026-09-14T12:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Los Angeles Lakers", "price": 1.80},
                                    {"name": "Golden State Warriors", "price": 2.05}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "mock_game_2",
                "sport_key": "americanfootball_nfl",
                "home_team": "Kansas City Chiefs",
                "away_team": "New York Jets",
                "commence_time": "2026-10-25T17:00:00Z",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "title": "DraftKings",
                        "last_update": "2026-09-14T12:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Kansas City Chiefs", "price": 1.25},
                                    {"name": "New York Jets", "price": 4.80}
                                ]
                            }
                        ]
                    },
                    {
                        "key": "fanduel",
                        "title": "FanDuel",
                        "last_update": "2026-09-14T12:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Kansas City Chiefs", "price": 1.22},
                                    {"name": "New York Jets", "price": 5.00}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
        return self._parse_events(mock_json)

    def _get_mock_scores(self) -> Dict:
        """
        Returns mock scores to simulate settling trades.
        """
        return {
            "mock_game_1": {
                "completed": True,
                "scores": [
                    {"name": "Los Angeles Lakers", "score": "112"},
                    {"name": "Golden State Warriors", "score": "109"}
                ]
            },
            "mock_game_2": {
                "completed": True,
                "scores": [
                    {"name": "Kansas City Chiefs", "score": "27"},
                    {"name": "New York Jets", "score": "13"}
                ]
            }
        }

if __name__ == "__main__":
    client = OddsAPIClient(use_mock=True)
    events = client.get_odds()
    print(f"Fetched {len(events)} events.")
    for e in events:
        print(f"{e.home_team} vs {e.away_team}")
        for b in e.bookmakers:
            print(f"  {b.title}: {b.markets[0].outcomes}")

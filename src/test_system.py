import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import OddsAPIClient
from database import TradeDatabase
from ev_scanner import EVScanner
from scanner import ArbitrageScanner
from matched_betting import MatchedBettingScanner


class TestEVScannerContract(unittest.TestCase):
    def test_two_way_vs_three_way_does_not_emit_draw(self):
        from api_client import Bookmaker, Event, Market, Outcome

        class ListOddsClient:
            def __init__(self, events):
                self._events = events
            def get_odds(self, *a, **k):
                return self._events

        event = Event(
            id="mix_1",
            sport_key="soccer_test",
            home_team="Home",
            away_team="Away",
            commence_time="2026-09-21T00:00:00Z",
            bookmakers=[
                Bookmaker(
                    key="draftkings",
                    title="DraftKings",
                    last_update="t",
                    markets=[
                        Market(
                            key="h2h",
                            outcomes=[
                                Outcome(name="Home", price=1.90),
                                Outcome(name="Away", price=2.00),
                            ],
                        )
                    ],
                ),
                Bookmaker(
                    key="fanduel",
                    title="FanDuel",
                    last_update="t",
                    markets=[
                        Market(
                            key="h2h",
                            outcomes=[
                                Outcome(name="Home", price=1.85),
                                Outcome(name="Away", price=2.05),
                                Outcome(name="Draw", price=66.0),
                            ],
                        )
                    ],
                ),
            ],
        )
        scanner = EVScanner(ListOddsClient([event]))
        scanner.bankroll = 1000
        opps = scanner.scan(min_edge=0.01, kelly_fraction=0.25, fee_percentage=0.0)
        self.assertFalse(any(o["bet_on"] == "Draw" for o in opps))

    def test_insane_draw_odds_are_rejected(self):
        from api_client import Bookmaker, Event, Market, Outcome

        class ListOddsClient:
            def __init__(self, events):
                self._events = events
            def get_odds(self, *a, **k):
                return self._events

        event = Event(
            id="draw_junk",
            sport_key="soccer_test",
            home_team="A",
            away_team="B",
            commence_time="2026-09-21T00:00:00Z",
            bookmakers=[
                Bookmaker(
                    key="draftkings",
                    title="DraftKings",
                    last_update="t",
                    markets=[
                        Market(
                            key="h2h",
                            outcomes=[
                                Outcome(name="A", price=2.10),
                                Outcome(name="B", price=3.40),
                                Outcome(name="Draw", price=3.50),
                            ],
                        )
                    ],
                ),
                Bookmaker(
                    key="fanduel",
                    title="FanDuel",
                    last_update="t",
                    markets=[
                        Market(
                            key="h2h",
                            outcomes=[
                                Outcome(name="A", price=2.05),
                                Outcome(name="B", price=3.30),
                                Outcome(name="Draw", price=66.0),
                            ],
                        )
                    ],
                ),
            ],
        )
        scanner = EVScanner(ListOddsClient([event]))
        scanner.bankroll = 1000
        opps = scanner.scan(min_edge=0.01, kelly_fraction=0.25, fee_percentage=0.0)
        self.assertFalse(any(o["bet_on"] == "Draw" for o in opps))

    def test_opportunities_include_event_id_and_sport_key(self):
        scanner = EVScanner(OddsAPIClient(use_mock=True))
        opps = scanner.scan(min_edge=0.01, kelly_fraction=0.25, fee_percentage=0.0)

        self.assertTrue(opps, "Mock market should produce at least one +EV opportunity")
        self.assertIn("event_id", opps[0])
        self.assertEqual(opps[0]["event_id"], "mock_game_1")
        self.assertEqual(opps[0]["sport_key"], "basketball_nba")
        self.assertIn("kelly_stake", opps[0])


class TestArbitrageScanner(unittest.TestCase):
    def test_mock_market_contains_arbitrage(self):
        scanner = ArbitrageScanner(OddsAPIClient(use_mock=True))
        opps = scanner.scan()

        self.assertTrue(opps, "Mock DK/FanDuel split should be an arbitrage")
        self.assertGreater(opps[0]["guaranteed_profit"], 0)
        self.assertEqual(len(opps[0]["legs"]), 2)


class TestMatchedBettingScanner(unittest.TestCase):
    def test_mock_market_contains_free_bet_conversion(self):
        scanner = MatchedBettingScanner(OddsAPIClient(use_mock=True))
        opps = scanner.find_free_bet_conversions(
            "FanDuel", "DraftKings", free_bet_amount=50.0, min_conversion=0.65
        )
        self.assertTrue(opps, "Mock data should include a convertible free-bet market")
        self.assertGreaterEqual(opps[0]["conversion_rate"], 65.0)


class TestSettlement(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_path = path
        self.db = TradeDatabase(path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_settle_won_trade_by_event_id(self):
        from settlement import settle_pending_trades

        trade_id = self.db.log_trade(
            "mock_game_1",
            "Los Angeles Lakers vs Golden State Warriors",
            "Los Angeles Lakers",
            2.50,
            0.45,
            0.125,
            10.0,
            sport_key="basketball_nba",
        )
        self.db.update_closing_line(trade_id, 2.40, 0.46)

        settled = settle_pending_trades(
            self.db,
            {
                "mock_game_1": {
                    "completed": True,
                    "scores": [
                        {"name": "Los Angeles Lakers", "score": "112"},
                        {"name": "Golden State Warriors", "score": "109"},
                    ],
                }
            },
        )

        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["outcome"], "WON")
        self.assertAlmostEqual(settled[0]["profit_loss"], 14.7)

        stored = self.db.get_all_closed_trades()
        self.assertEqual(stored[0]["outcome"], "WON")
        self.assertAlmostEqual(stored[0]["profit_loss"], 14.7)

    def test_settle_lost_and_unmatched_stay_pending(self):
        from settlement import settle_pending_trades

        lost_id = self.db.log_trade(
            "mock_game_1",
            "Lakers vs Warriors",
            "Golden State Warriors",
            1.90,
            0.55,
            0.045,
            10.0,
        )
        self.db.update_closing_line(lost_id, 1.85, 0.57)

        unmatched_id = self.db.log_trade(
            "some_other_event",
            "Celtics vs Heat",
            "Miami Heat",
            2.10,
            0.50,
            0.05,
            10.0,
        )
        self.db.update_closing_line(unmatched_id, 2.00, 0.52)

        settle_pending_trades(
            self.db,
            {
                "mock_game_1": {
                    "completed": True,
                    "scores": [
                        {"name": "Los Angeles Lakers", "score": "112"},
                        {"name": "Golden State Warriors", "score": "109"},
                    ],
                }
            },
        )

        by_id = {t["id"]: t for t in self.db.get_all_closed_trades()}
        self.assertEqual(by_id[lost_id]["outcome"], "LOST")
        self.assertAlmostEqual(by_id[lost_id]["profit_loss"], -10.0)
        self.assertEqual(by_id[unmatched_id]["outcome"], "PENDING")

    def test_legacy_match_name_event_id_still_settles(self):
        from settlement import settle_pending_trades

        trade_id = self.db.log_trade(
            "Los Angeles Lakers vs Golden State Warriors",
            "Los Angeles Lakers vs Golden State Warriors",
            "Los Angeles Lakers",
            2.50,
            0.45,
            0.125,
            10.0,
        )
        self.db.update_closing_line(trade_id, 2.40, 0.46)

        settled = settle_pending_trades(
            self.db,
            {
                "mock_game_1": {
                    "completed": True,
                    "scores": [
                        {"name": "Los Angeles Lakers", "score": "112"},
                        {"name": "Golden State Warriors", "score": "109"},
                    ],
                }
            },
        )
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["outcome"], "WON")

    def test_push_returns_stake(self):
        from settlement import settle_pending_trades

        trade_id = self.db.log_trade(
            "mock_game_1", "Lakers vs Warriors", "Los Angeles Lakers", 2.50, 0.45, 0.12, 10.0
        )
        self.db.update_closing_line(trade_id, 2.40, 0.46)

        settled = settle_pending_trades(
            self.db,
            {
                "mock_game_1": {
                    "completed": True,
                    "scores": [
                        {"name": "Los Angeles Lakers", "score": "100"},
                        {"name": "Golden State Warriors", "score": "100"},
                    ],
                }
            },
        )
        self.assertEqual(settled[0]["outcome"], "PUSH")
        self.assertAlmostEqual(settled[0]["profit_loss"], 0.0)

    def test_paper_trades_ignore_mock_scores(self):
        from settlement import settle_pending_trades

        trade_id = self.db.log_trade(
            "mock_game_1",
            "Lakers vs Warriors",
            "Golden State Warriors",
            2.05,
            0.54,
            0.10,
            25.0,
            mode="paper",
        )
        self.db.update_closing_line(trade_id, 2.05, 0.54)

        settled = settle_pending_trades(
            self.db,
            {
                "mock_game_1": {
                    "completed": True,
                    "scores": [
                        {"name": "Los Angeles Lakers", "score": "112"},
                        {"name": "Golden State Warriors", "score": "109"},
                    ],
                }
            },
        )
        self.assertEqual(settled, [])
        stored = {t["id"]: t for t in self.db.get_all_closed_trades()}
        self.assertEqual(stored[trade_id]["outcome"], "PENDING")

    def test_paper_settlement_uses_true_probability(self):
        from settlement import settle_paper_trades

        class AlwaysWin:
            def random(self):
                return 0.0

        class AlwaysLose:
            def random(self):
                return 0.999

        win_id = self.db.log_trade("p1", "A vs B", "A", 2.10, 0.55, 0.10, 10.0, mode="paper")
        self.db.update_closing_line(win_id, 2.10, 0.55)
        won = settle_paper_trades(self.db, fee_percentage=0.0, rng=AlwaysWin())
        self.assertEqual(won[0]["outcome"], "WON")
        self.assertAlmostEqual(won[0]["profit_loss"], 11.0)

        lose_id = self.db.log_trade("p2", "A vs B", "B", 2.10, 0.55, 0.10, 10.0, mode="paper")
        self.db.update_closing_line(lose_id, 2.10, 0.55)
        lost = settle_paper_trades(self.db, fee_percentage=0.0, rng=AlwaysLose())
        self.assertEqual(lost[0]["outcome"], "LOST")
        self.assertAlmostEqual(lost[0]["profit_loss"], -10.0)

    def test_paper_win_applies_two_percent_fee(self):
        from settlement import settle_paper_trades

        class AlwaysWin:
            def random(self):
                return 0.0

        trade_id = self.db.log_trade("p-fee", "A vs B", "A", 2.10, 0.55, 0.10, 10.0, mode="paper")
        self.db.update_closing_line(trade_id, 2.10, 0.55)
        won = settle_paper_trades(self.db, fee_percentage=0.02, rng=AlwaysWin())
        self.assertEqual(won[0]["outcome"], "WON")
        self.assertAlmostEqual(won[0]["profit_loss"], 10.78)


class TestPaperEngine(unittest.TestCase):
    def test_walk_forward_is_profitable_with_fixed_seed(self):
        from paper_engine import PaperEngine

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db = TradeDatabase(path)
            engine = PaperEngine(db, rng=__import__("random").Random(42))
            result = engine.run_batch(num_games=2500)
            self.assertGreater(result["bets_placed"], 20)
            self.assertGreater(result["pnl"], 0)
            self.assertGreater(db.get_system_params()["bankroll"], 1000)
        finally:
            if os.path.exists(path):
                os.remove(path)


class TestDatabaseParams(unittest.TestCase):
    def test_has_trade_prevents_duplicate_positions(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db = TradeDatabase(path)
            self.assertFalse(db.has_trade("mock_game_1", "Golden State Warriors"))
            db.log_trade("mock_game_1", "Lakers vs Warriors", "Golden State Warriors", 2.05, 0.54, 0.10, 25.0)
            self.assertTrue(db.has_trade("mock_game_1", "Golden State Warriors"))
            self.assertTrue(db.has_event_position("mock_game_1"))
            self.assertFalse(db.has_trade("mock_game_1", "Los Angeles Lakers"))
            self.assertFalse(db.has_event_position("other_event"))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_fresh_db_has_default_params(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db = TradeDatabase(path)
            params = db.get_system_params()
            self.assertIn("min_ev_threshold", params)
            self.assertIn("kelly_fraction", params)
            self.assertIn("bankroll", params)
            self.assertGreater(params["min_ev_threshold"], 0)
            self.assertEqual(params["bankroll"], 1000.0)
        finally:
            if os.path.exists(path):
                os.remove(path)


class TestTradingMode(unittest.TestCase):
    def test_default_is_live_paper_not_simulator(self):
        from trading_mode import get_trading_mode, is_sim, uses_real_odds

        os.environ.pop("TRADING_MODE", None)
        self.assertEqual(get_trading_mode(), "live_paper")
        self.assertTrue(uses_real_odds())
        self.assertFalse(is_sim())

    def test_paper_alias_is_simulator(self):
        from trading_mode import get_trading_mode, is_sim

        os.environ["TRADING_MODE"] = "paper"
        try:
            self.assertEqual(get_trading_mode(), "sim")
            self.assertTrue(is_sim())
        finally:
            os.environ.pop("TRADING_MODE", None)


class TestAPI(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_path = path
        from api import create_app

        self.app = create_app(
            db=TradeDatabase(path),
            odds_client=OddsAPIClient(use_mock=True),
        )
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_health_and_status(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ok")

        status = self.client.get("/api/system_status")
        self.assertEqual(status.status_code, 200)
        body = status.get_json()
        self.assertEqual(body["status"], "ONLINE")
        self.assertIn("kelly_fraction", body)
        self.assertIn("realized_pnl", body)
        self.assertIn("bankroll", body)
        self.assertIn("trading_mode", body)
        self.assertAlmostEqual(body["win_fee_percentage"], 0.02)
        open_bets = self.client.get("/api/open_bets")
        self.assertEqual(open_bets.status_code, 200)
        self.assertIsInstance(open_bets.get_json(), list)

    def test_opportunity_endpoints_return_lists(self):
        for path in (
            "/api/opportunities/ev",
            "/api/opportunities/arbitrage",
            "/api/opportunities/matched_betting",
        ):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertIsInstance(res.get_json(), list, path)

    def test_broadcast_caches_opportunities_for_next_get(self):
        payload = [{"event": "Cached Match", "event_id": "c1", "kelly_stake": 5.0, "ev_percentage": 3.1}]
        post = self.client.post("/api/broadcast_opportunities", json=payload)
        self.assertEqual(post.status_code, 200)

        cached = self.client.get("/api/opportunities/ev")
        self.assertEqual(cached.get_json(), payload)


if __name__ == "__main__":
    unittest.main()

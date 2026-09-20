import time
import os
import requests
from collections import defaultdict
from datetime import datetime
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import OddsAPIClient
from ev_scanner import EVScanner
from scanner import ArbitrageScanner
from database import TradeDatabase
from learning_module import LearningModule
from kalshi_client import KalshiClient
from matched_betting import MatchedBettingScanner
from account_health import AccountHealthManager
from settlement import settle_pending_trades
from paper_engine import PaperEngine
from fees import win_fee_percentage
from trading_mode import get_trading_mode, is_sim, uses_real_odds


def _normalize_api_url(raw: str) -> str:
    raw = (raw or "http://127.0.0.1:5000").rstrip("/")
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"http://{raw}"


class Daemon:
    def __init__(self):
        self.odds_client = OddsAPIClient(use_mock=False)
        self.db = TradeDatabase()
        self.learner = LearningModule()
        self.execution_client = KalshiClient(paper_trade=True)

        self.ev_scanner = EVScanner(self.odds_client)
        self.arb_scanner = ArbitrageScanner(self.odds_client)
        self.mb_scanner = MatchedBettingScanner(self.odds_client)
        self.health_manager = AccountHealthManager(prop_cap=50.0, main_line_cap=500.0, mug_bet_chance=0.05)
        self.paper_engine = PaperEngine(self.db, fee_percentage=win_fee_percentage())

        self.sleep_interval = int(os.environ.get("SCAN_INTERVAL_SECONDS", "900"))
        self.paper_games = int(os.environ.get("PAPER_GAMES_PER_CYCLE", "20"))
        self.max_bets_per_cycle = int(os.environ.get("MAX_BETS_PER_CYCLE", "10"))
        self.discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "MOCK_URL")
        self.api_base_url = _normalize_api_url(os.environ.get("API_URL", "http://127.0.0.1:5000"))
        self.trading_mode = get_trading_mode()

    def _send_discord_alert(self, message: str):
        print(f"\n     [DISCORD ALERT] Sending to webhook: {message}")
        if self.discord_webhook_url != "MOCK_URL":
            try:
                requests.post(self.discord_webhook_url, json={"content": message}, timeout=10)
            except Exception as e:
                print(f"Failed to send Discord alert: {e}")

    def _broadcast(self, path: str, payload):
        try:
            requests.post(f"{self.api_base_url}{path}", json=payload, timeout=10)
        except Exception as e:
            print(f"     [WEBSOCKET ERROR] Failed to broadcast {path}: {e}")

    def _settle_live(self):
        pending = [
            t for t in self.db.get_all_closed_trades()
            if (t.get("outcome") or "PENDING") == "PENDING"
            and (t.get("mode") or "live") != "paper"
        ]
        if not pending:
            return

        by_sport = defaultdict(list)
        for trade in pending:
            sport = trade.get("sport_key") or "_unknown"
            by_sport[sport].append(trade)

        results = {}
        for sport, trades in by_sport.items():
            event_ids = [t["event_id"] for t in trades]
            try:
                if sport == "_unknown":
                    chunk = self.odds_client.get_match_results(event_ids=event_ids)
                else:
                    chunk = self.odds_client.get_match_results(
                        sport=sport, daysFrom=3, event_ids=event_ids
                    )
                results.update(chunk)
            except Exception as e:
                print(f"     [SETTLE ERROR] Could not fetch scores for {sport}: {e}")

        settled = settle_pending_trades(self.db, results)
        for item in settled:
            self.db.adjust_bankroll(item["profit_loss"])
            print(f"     [SETTLED] Trade {item['id']}: {item['outcome']} (${item['profit_loss']:.2f})")

    def _scan_for_dashboard(self, params):
        print("  -> Scanning display markets (EV / arb / matched betting)...")
        try:
            ev_opportunities = self.ev_scanner.scan(
                min_edge=params["min_ev_threshold"],
                kelly_fraction=params["kelly_fraction"],
                fee_percentage=win_fee_percentage(),
            )
        except Exception as e:
            print(f"     [SCAN ERROR] EV: {e}")
            ev_opportunities = []
        try:
            arb_opportunities = self.arb_scanner.scan()
        except Exception as e:
            print(f"     [SCAN ERROR] Arb: {e}")
            arb_opportunities = []
        try:
            mb_opportunities = self.mb_scanner.find_free_bet_conversions(
                "FanDuel", "DraftKings", free_bet_amount=50.0, min_conversion=0.65
            )
        except Exception as e:
            print(f"     [SCAN ERROR] Matched betting: {e}")
            mb_opportunities = []

        self._broadcast("/api/broadcast_opportunities", ev_opportunities)
        self._broadcast("/api/broadcast_arbitrage", arb_opportunities)
        self._broadcast("/api/broadcast_matched_betting", mb_opportunities)
        return ev_opportunities

    def _execute_live_opportunities(self, ev_opportunities):
        if not ev_opportunities:
            print("     No +EV bets found.")
            return
        print(f"     [ALERT] Found {len(ev_opportunities)} +EV bets!")
        placed = 0
        for opp in ev_opportunities:
            print(f"       * {opp['bet_on']} @ {opp['soft_odds']} (EV: +{opp['ev_percentage']}%)")
            if opp["ev_percentage"] > 5.0:
                self._send_discord_alert(
                    f"🚨 MASSIVE EDGE DETECTED 🚨\n{opp['bet_on']} @ {opp['soft_odds']} in {opp['event']}\n"
                    f"Edge: +{opp['ev_percentage']}%\nRecommended Stake: ${opp['kelly_stake']}"
                )
            try:
                event_id = opp.get("event_id")
                if not event_id:
                    print("     [EXECUTION ERROR] Opportunity missing event_id; skipping log")
                    continue
                if self.db.has_trade(event_id, opp["bet_on"]):
                    print(f"     [SKIP] Already have a position on {opp['bet_on']} ({event_id})")
                    continue

                market_key = opp.get("market_key", "h2h")
                final_stake = self.health_manager.apply_cunning_strategy(opp["kelly_stake"], market_key)
                order_id = None
                if not self.execution_client.paper_trade:
                    contract_count = max(1, int(final_stake))
                    yes_price = max(1, min(99, int((1.0 / opp["soft_odds"]) * 100)))
                    order = self.execution_client.submit_order(
                        ticker=opp["event"].replace(" ", "_").upper(),
                        action="buy",
                        count=contract_count,
                        yes_price=yes_price,
                    )
                    order_id = order.get("order_id")

                self.db.log_trade(
                    event_id=event_id,
                    match_name=opp["event"],
                    bet_on=opp["bet_on"],
                    placed_odds=opp["soft_odds"],
                    true_prob=opp["true_probability"] / 100.0,
                    ev=opp["ev_percentage"] / 100.0,
                    stake=final_stake,
                    exchange_order_id=order_id,
                    sport_key=opp.get("sport_key"),
                    mode="live_paper",
                )
                placed += 1
                print(f"     [LIVE PAPER] {opp['bet_on']} ${final_stake} — waiting for real scores")
                if placed >= self.max_bets_per_cycle:
                    break
            except Exception as e:
                print(f"     [EXECUTION ERROR] {e}")

    def run(self):
        print(f"Starting Autonomous Daemon in {self.trading_mode.upper()} mode...")
        while True:
            try:
                self._run_cycle()
            except Exception as e:
                print(f"[ERROR] Daemon encountered an issue: {e}")

            print(f"Sleeping for {self.sleep_interval} seconds...\n")
            time.sleep(self.sleep_interval)

    def _run_cycle(self):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time}] Executing Scanning Cycle ({self.trading_mode})...")

        params = self.db.get_system_params()
        self.ev_scanner.bankroll = float(params.get("bankroll") or 1000.0)

        if is_sim(self.trading_mode):
            print(f"  -> SIMULATOR (invented games) — {self.paper_games} per cycle")
            summary = self.paper_engine.run_batch(self.paper_games)
            print(
                f"     Sim batch: {summary['bets_placed']} bets, "
                f"P&L ${summary['pnl']:.2f}, bankroll ${summary['bankroll']:.2f}"
            )
        elif uses_real_odds(self.trading_mode):
            if self.odds_client.is_mock:
                print("  -> BLOCKED: ODDS_API_KEY is not set. Not inventing games. Add the key and restart.")
                print(f"[{current_time}] Cycle Complete.")
                return
            print("  -> Settling live-paper trades from real scores...")
            self._settle_live()
        else:
            print(f"  -> Unknown TRADING_MODE={self.trading_mode}")
            return

        print("  -> Evaluating realized performance...")
        self.learner.evaluate_performance()
        params = self.db.get_system_params()

        ev_opportunities = self._scan_for_dashboard(params)
        if uses_real_odds(self.trading_mode) and not self.odds_client.is_mock:
            print(
                f"  -> Logging real-market paper bets "
                f"(Min Edge: {params['min_ev_threshold']*100:.2f}%, Kelly: {params['kelly_fraction']}x)..."
            )
            self._execute_live_opportunities(ev_opportunities)

        print(f"[{current_time}] Cycle Complete.")


if __name__ == "__main__":
    daemon = Daemon()
    daemon.run()

import uuid

from calculators import calculate_kelly_criterion
from settlement import settle_paper_trades


class PaperEngine:
    """Walk-forward +EV paper trader.

    Each game is unique. The bet is sized with Kelly and settled with the
    modeled true probability — the law of large numbers, not one mock box score.
    """

    def __init__(self, db, rng=None, fee_percentage: float = 0.0):
        import random

        self.db = db
        self.rng = rng or random.Random()
        self.fee_percentage = fee_percentage

    def _one_game(self, index: int) -> dict:
        true_home = self.rng.uniform(0.25, 0.75)
        true_away = 1.0 - true_home
        error = self.rng.gauss(0.0, 0.04)
        soft_home_p = min(0.99, max(0.01, true_home + error))
        soft_away_p = 1.0 - soft_home_p
        soft_vig = 0.05
        implied_home = min(0.99, soft_home_p * (1.0 + soft_vig / 2.0))
        implied_away = min(0.99, soft_away_p * (1.0 + soft_vig / 2.0))
        odds_home = 1.0 / implied_home
        odds_away = 1.0 / implied_away

        profit_home = (odds_home - 1.0) * (1.0 - self.fee_percentage)
        profit_away = (odds_away - 1.0) * (1.0 - self.fee_percentage)
        ev_home = (true_home * profit_home) - (1.0 - true_home)
        ev_away = (true_away * profit_away) - (1.0 - true_away)

        if ev_home >= ev_away:
            return {
                "event_id": f"paper_{uuid.uuid4().hex[:12]}_{index}",
                "event": f"Home {index} vs Away {index}",
                "bet_on": f"Home {index}",
                "odds": odds_home,
                "true_prob": true_home,
                "ev": ev_home,
            }
        return {
            "event_id": f"paper_{uuid.uuid4().hex[:12]}_{index}",
            "event": f"Home {index} vs Away {index}",
            "bet_on": f"Away {index}",
            "odds": odds_away,
            "true_prob": true_away,
            "ev": ev_away,
        }

    def run_batch(self, num_games: int = 80) -> dict:
        params = self.db.get_system_params()
        bankroll = float(params.get("bankroll") or 1000.0)
        min_edge = float(params.get("min_ev_threshold") or 0.02)
        kelly_fraction = float(params.get("kelly_fraction") or 0.25)

        committed = 0.0
        placed = 0
        for i in range(num_games):
            game = self._one_game(i)
            if game["ev"] < min_edge:
                continue
            remaining = bankroll - committed
            if remaining < 1.0:
                break
            kelly_pct = calculate_kelly_criterion(
                game["odds"], game["true_prob"], fraction=kelly_fraction
            )
            stake = min(bankroll * kelly_pct, remaining)
            if stake < 1.0:
                continue

            trade_id = self.db.log_trade(
                event_id=game["event_id"],
                match_name=game["event"],
                bet_on=game["bet_on"],
                placed_odds=game["odds"],
                true_prob=game["true_prob"],
                ev=game["ev"],
                stake=round(stake, 2),
                exchange_order_id=f"paper_{uuid.uuid4().hex[:10]}",
                sport_key="synthetic",
                mode="paper",
            )
            self.db.update_closing_line(trade_id, game["odds"], game["true_prob"])
            committed += stake
            placed += 1

        settled = settle_paper_trades(
            self.db, fee_percentage=self.fee_percentage, rng=self.rng
        )
        pnl = round(sum(item["profit_loss"] for item in settled), 2)
        updated = self.db.get_system_params()
        return {
            "games_scanned": num_games,
            "bets_placed": placed,
            "bets_settled": len(settled),
            "pnl": pnl,
            "bankroll": updated.get("bankroll", bankroll),
        }

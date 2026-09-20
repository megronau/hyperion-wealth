from typing import Dict, List, Any
import random

from fees import winning_profit, win_fee_percentage


def _parse_scores(scores: List[Dict]) -> List[Dict[str, Any]]:
    parsed = []
    for row in scores:
        name = row.get("name")
        raw = row.get("score")
        if name is None or raw is None:
            continue
        parsed.append({"name": name, "score": int(raw)})
    return parsed


def _lookup_result(trade: Dict, results: Dict[str, Dict]):
    event_id = trade.get("event_id")
    if event_id in results:
        return results[event_id]

    # Older rows stored the match title as event_id. Match against score team names.
    haystack = f"{trade.get('event_id') or ''} {trade.get('match_name') or ''}".lower()
    for result in results.values():
        names = [str(s.get("name", "")).lower() for s in (result.get("scores") or []) if s.get("name")]
        if names and all(name in haystack for name in names):
            return result
    return None


def settle_pending_trades(db, results: Dict[str, Dict], fee_percentage: float = None) -> List[Dict]:
    """Settle CLOSED trades whose outcome is still PENDING using match scores.

    `results` is a mapping of Odds API event_id -> {completed, scores}.
    """
    settled = []
    closed = db.get_all_closed_trades()
    pending = [t for t in closed if (t.get("outcome") or "PENDING") == "PENDING"]

    for trade in pending:
        if (trade.get("mode") or "live") == "paper":
            continue
        result = _lookup_result(trade, results)
        if not result or not result.get("completed"):
            continue

        scores = _parse_scores(result.get("scores") or [])
        if len(scores) < 2:
            continue

        top_score = max(s["score"] for s in scores)
        winners = [s["name"] for s in scores if s["score"] == top_score]
        if len(winners) > 1:
            outcome = "PUSH"
            profit = 0.0
        elif trade.get("bet_on") in winners:
            outcome = "WON"
            profit = winning_profit(
                trade["placed_odds"],
                trade["stake"],
                fee_percentage if fee_percentage is not None else win_fee_percentage(),
            )
        else:
            outcome = "LOST"
            profit = -float(trade["stake"])

        db.settle_trade(trade["id"], outcome, profit)
        settled.append({
            "id": trade["id"],
            "outcome": outcome,
            "profit_loss": round(profit, 2),
        })

    return settled


def settle_paper_trades(db, fee_percentage: float = None, rng=None) -> List[Dict]:
    """Settle paper trades with a Bernoulli draw at modeled true probability.

    This is how the +EV model is supposed to realize: unique bets, each resolved
    by p(win) = true_prob_at_placement, not by repeating one mock box score.
    """
    rng = rng or random.Random()
    fee = win_fee_percentage() if fee_percentage is None else fee_percentage
    settled = []
    closed = db.get_all_closed_trades()
    pending = [
        t for t in closed
        if (t.get("outcome") or "PENDING") == "PENDING"
        and (t.get("mode") or "live") == "paper"
    ]

    for trade in pending:
        p = float(trade.get("true_prob_at_placement") or 0.0)
        p = min(0.999, max(0.001, p))
        stake = float(trade["stake"])
        odds = float(trade["placed_odds"])

        if rng.random() < p:
            outcome = "WON"
            profit = winning_profit(odds, stake, fee)
        else:
            outcome = "LOST"
            profit = -stake

        profit = round(profit, 2)
        db.settle_trade(trade["id"], outcome, profit)
        if hasattr(db, "adjust_bankroll"):
            db.adjust_bankroll(profit)
        settled.append({
            "id": trade["id"],
            "outcome": outcome,
            "profit_loss": profit,
        })

    return settled

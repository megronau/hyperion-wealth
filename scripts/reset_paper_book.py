"""Wipe trades and reset bankroll, then run a paper walk-forward.

Usage (PowerShell):
  $env:STARTING_BANKROLL = "100"
  $env:PAPER_GAMES_PER_CYCLE = "20"
  py -3 scripts/reset_paper_book.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from database import TradeDatabase
from paper_engine import PaperEngine


def main():
    starting = float(os.environ.get("STARTING_BANKROLL", "1000"))
    games = int(os.environ.get("PAPER_GAMES_PER_CYCLE", "400"))
    db = TradeDatabase()
    print(f"Resetting paper book to ${starting:.2f} and wiping poisoned trades...")
    db.reset_paper_book(starting)
    engine = PaperEngine(db)
    result = engine.run_batch(games)
    print(
        f"Seed walk-forward complete: {result['bets_placed']} bets, "
        f"P&L ${result['pnl']:.2f}, bankroll ${result['bankroll']:.2f}"
    )


if __name__ == "__main__":
    main()

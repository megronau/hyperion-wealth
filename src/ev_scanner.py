from api_client import OddsAPIClient
from calculators import calculate_kelly_criterion, decimal_to_implied_probability
from typing import List, Dict

class EVScanner:
    def __init__(self, api_client: OddsAPIClient):
        self.api_client = api_client
        self.bankroll = 500.0
        # Pinnacle is the industry standard 'sharp' book.
        # If it's not in the data feed, we will fall back to DraftKings as our baseline for testing.
        self.sharp_books = ["pinnacle", "draftkings"] 
        self.soft_books = ["fanduel", "betmgm", "caesars", "bet365"]

    def _remove_vig(self, odds: List[float]) -> List[float]:
        """
        Removes the bookmaker's margin (vig) from a set of mutually exclusive odds
        to calculate the 'True Probability' of each outcome.
        """
        implied_probs = [decimal_to_implied_probability(o) for o in odds]
        total_implied = sum(implied_probs)
        
        # Normalize probabilities so they sum exactly to 1.0
        true_probs = [p / total_implied for p in implied_probs]
        return true_probs

    def scan(self, min_edge: float = 0.02, kelly_fraction: float = 0.25, fee_percentage: float = 0.0) -> List[Dict]:
        """
        Scans for Positive Expected Value (+EV) bets.
        min_edge = 0.02 means we only want bets with a >2% mathematical edge.
        kelly_fraction is passed dynamically from the machine learning module.
        fee_percentage represents exchange transaction fees (e.g., 0.01 for 1%).
        """
        events = self.api_client.get_odds()
        opportunities = []

        for event in events:
            # Step 1: Find the Sharp Book's odds to determine True Probability
            sharp_odds_markets = {}
            for s_book in self.sharp_books:
                for bookmaker in event.bookmakers:
                    if s_book.lower() == bookmaker.key.lower():
                        for market in bookmaker.markets:
                            sharp_odds_markets[market.key] = {outcome.name: outcome.price for outcome in market.outcomes}
                if sharp_odds_markets:
                    break

            if not sharp_odds_markets:
                continue # Skip if no sharp data

            true_probs_markets = {}
            for m_key, sharp_odds_map in sharp_odds_markets.items():
                if len(sharp_odds_map) < 2:
                    continue
                outcomes = list(sharp_odds_map.keys())
                sharp_odds_list = [sharp_odds_map[out] for out in outcomes]
                try:
                    true_probs_list = self._remove_vig(sharp_odds_list)
                    true_probs_markets[m_key] = {outcomes[i]: true_probs_list[i] for i in range(len(outcomes))}
                except ValueError:
                    continue

            # Step 2: Compare against Soft Books
            for bookmaker in event.bookmakers:
                if bookmaker.key.lower() in self.soft_books:
                    for market in bookmaker.markets:
                        if market.key in true_probs_markets:
                            true_probs_map = true_probs_markets[market.key]
                            for outcome in market.outcomes:
                                name = outcome.name
                                soft_odds = outcome.price
                                
                                if name in true_probs_map:
                                    true_prob = true_probs_map[name]
                                    
                                    # Expected Value Calculation
                                    # EV = (Probability of Winning * Profit if Win) - Probability of Losing
                                    # Deduct fee from profit if win
                                    profit_if_win = (soft_odds - 1.0) * (1.0 - fee_percentage)
                                    prob_lose = 1.0 - true_prob
                                    
                                    # Deduct fee from the stake lost if lose (some exchanges charge on all trades)
                                    # For simplicity, assuming fee is only on profit like typical betting exchanges
                                    ev = (true_prob * profit_if_win) - prob_lose
                                    
                                    if ev >= min_edge:
                                        # Use Kelly Criterion to size the bet (using dynamically learned fraction)
                                        kelly_pct = calculate_kelly_criterion(soft_odds, true_prob, fraction=kelly_fraction)
                                        recommended_stake = self.bankroll * kelly_pct
                                        
                                        if recommended_stake > 1.0: # Minimum $1 bet
                                            opportunities.append({
                                                "event_id": event.id,
                                                "sport_key": event.sport_key,
                                                "event": f"{event.home_team} vs {event.away_team}",
                                                "market_key": market.key,
                                                "bet_on": name,
                                                "soft_book": bookmaker.title,
                                                "soft_odds": soft_odds,
                                                "true_probability": round(true_prob * 100, 2),
                                                "ev_percentage": round(ev * 100, 2),
                                                "kelly_stake": round(recommended_stake, 2)
                                            })

        # Sort by highest EV
        opportunities.sort(key=lambda x: x["ev_percentage"], reverse=True)
        return opportunities

if __name__ == "__main__":
    print("Initializing +EV Scanner...")
    client = OddsAPIClient(use_mock=False)
    scanner = EVScanner(client)
    
    print("\n--- POSITIVE EV OPPORTUNITIES ---")
    ev_bets = scanner.scan(min_edge=0.01) # Look for >1% edge
    if not ev_bets:
        print("No +EV bets found right now.")
    else:
        for bet in ev_bets[:5]: # Show top 5
            print(f"Match: {bet['event']}")
            print(f"  Bet On: {bet['bet_on']} @ {bet['soft_odds']} (on {bet['soft_book']})")
            print(f"  True Prob: {bet['true_probability']}% | Edge (EV): +{bet['ev_percentage']}%")
            print(f"  Recommended Stake (Quarter-Kelly): ${bet['kelly_stake']}\n")

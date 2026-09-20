from api_client import OddsAPIClient
from calculators import calculate_sportsbook_free_bet_conversion, calculate_arbitrage_percentage
from typing import List, Dict

class MatchedBettingScanner:
    def __init__(self, api_client: OddsAPIClient):
        self.api_client = api_client

    def find_qualifying_bets(self, target_book: str, hedge_book: str, max_loss_pct: float = 0.05) -> List[Dict]:
        """
        Finds the best events to place a Qualifying Bet to unlock a bonus.
        We want the 'Arbitrage Percentage' to be slightly over 1.0 (meaning a small guaranteed loss).
        A max_loss_pct of 0.05 means we are willing to lose up to 5% of our stake to get the bonus.
        """
        events = self.api_client.get_odds()
        opportunities = []

        for event in events:
            # Extract odds specifically for target_book and hedge_book
            target_odds_map = {}
            hedge_odds_map = {}

            for bookmaker in event.bookmakers:
                title = bookmaker.title.lower()
                if target_book.lower() in title:
                    for market in bookmaker.markets:
                        if market.key == 'h2h':
                            for outcome in market.outcomes:
                                target_odds_map[outcome.name] = outcome.price
                elif hedge_book.lower() in title:
                    for market in bookmaker.markets:
                        if market.key == 'h2h':
                            for outcome in market.outcomes:
                                hedge_odds_map[outcome.name] = outcome.price

            # Check if both books offer the same outcomes
            common_outcomes = set(target_odds_map.keys()).intersection(set(hedge_odds_map.keys()))
            
            if len(common_outcomes) == 2:
                outcomes = list(common_outcomes)
                
                # Scenario 1: Bet outcome 0 on Target, outcome 1 on Hedge
                odds_s1 = [target_odds_map[outcomes[0]], hedge_odds_map[outcomes[1]]]
                try:
                    arb_pct = calculate_arbitrage_percentage(odds_s1)
                    loss_pct = arb_pct - 1.0
                    
                    if 0.0 <= loss_pct <= max_loss_pct:
                        opportunities.append({
                            "event": f"{event.home_team} vs {event.away_team}",
                            "target_bet": f"{outcomes[0]} @ {odds_s1[0]} (on {target_book})",
                            "hedge_bet": f"{outcomes[1]} @ {odds_s1[1]} (on {hedge_book})",
                            "loss_percentage": round(loss_pct * 100, 2),
                            "arb_percentage": round(arb_pct, 4)
                        })
                except ValueError:
                    pass

                # Scenario 2: Bet outcome 1 on Target, outcome 0 on Hedge
                odds_s2 = [target_odds_map[outcomes[1]], hedge_odds_map[outcomes[0]]]
                try:
                    arb_pct = calculate_arbitrage_percentage(odds_s2)
                    loss_pct = arb_pct - 1.0
                    
                    if 0.0 <= loss_pct <= max_loss_pct:
                        opportunities.append({
                            "event": f"{event.home_team} vs {event.away_team}",
                            "target_bet": f"{outcomes[1]} @ {odds_s2[0]} (on {target_book})",
                            "hedge_bet": f"{outcomes[0]} @ {odds_s2[1]} (on {hedge_book})",
                            "loss_percentage": round(loss_pct * 100, 2),
                            "arb_percentage": round(arb_pct, 4)
                        })
                except ValueError:
                    pass

        # Sort by smallest loss
        opportunities.sort(key=lambda x: x["loss_percentage"])
        return opportunities

    def find_free_bet_conversions(self, target_book: str, hedge_book: str, free_bet_amount: float = 100.0, min_conversion: float = 0.65) -> List[Dict]:
        """
        Finds the best events to place a Free Bet (SNR) to maximize guaranteed cash return.
        """
        events = self.api_client.get_odds()
        opportunities = []

        for event in events:
            target_odds_map = {}
            hedge_odds_map = {}

            for bookmaker in event.bookmakers:
                title = bookmaker.title.lower()
                if target_book.lower() in title:
                    for market in bookmaker.markets:
                        if market.key == 'h2h':
                            for outcome in market.outcomes:
                                target_odds_map[outcome.name] = outcome.price
                elif hedge_book.lower() in title:
                    for market in bookmaker.markets:
                        if market.key == 'h2h':
                            for outcome in market.outcomes:
                                hedge_odds_map[outcome.name] = outcome.price

            common_outcomes = set(target_odds_map.keys()).intersection(set(hedge_odds_map.keys()))
            
            if len(common_outcomes) == 2:
                outcomes = list(common_outcomes)
                
                # Check Scenario 1: Free bet on outcome 0, Hedge on outcome 1
                back_odds = target_odds_map[outcomes[0]]
                lay_odds = hedge_odds_map[outcomes[1]]
                
                conversion = calculate_sportsbook_free_bet_conversion(free_bet_amount, back_odds, lay_odds)
                if conversion["conversion_rate"] >= min_conversion:
                    opportunities.append({
                        "event": f"{event.home_team} vs {event.away_team}",
                        "free_bet": f"{outcomes[0]} @ {back_odds} (on {target_book})",
                        "hedge_bet": f"{outcomes[1]} @ {lay_odds} (on {hedge_book})",
                        "lay_stake_needed": conversion["hedge_stake"],
                        "guaranteed_profit": conversion["guaranteed_profit"],
                        "conversion_rate": round(conversion["conversion_rate"] * 100, 2)
                    })

                # Check Scenario 2: Free bet on outcome 1, Hedge on outcome 0
                back_odds_2 = target_odds_map[outcomes[1]]
                lay_odds_2 = hedge_odds_map[outcomes[0]]
                
                conversion_2 = calculate_sportsbook_free_bet_conversion(free_bet_amount, back_odds_2, lay_odds_2)
                if conversion_2["conversion_rate"] >= min_conversion:
                    opportunities.append({
                        "event": f"{event.home_team} vs {event.away_team}",
                        "free_bet": f"{outcomes[1]} @ {back_odds_2} (on {target_book})",
                        "hedge_bet": f"{outcomes[0]} @ {lay_odds_2} (on {hedge_book})",
                        "lay_stake_needed": conversion_2["hedge_stake"],
                        "guaranteed_profit": conversion_2["guaranteed_profit"],
                        "conversion_rate": round(conversion_2["conversion_rate"] * 100, 2)
                    })

        # Sort by highest conversion rate
        opportunities.sort(key=lambda x: x["conversion_rate"], reverse=True)
        return opportunities

if __name__ == "__main__":
    print("Initializing Matched Betting Scanner...")
    client = OddsAPIClient(use_mock=False)
    scanner = MatchedBettingScanner(client)
    
    # We want to extract a sign-up bonus from FanDuel, using DraftKings as our hedge
    book_a = "FanDuel"
    book_b = "DraftKings"
    
    print(f"\n--- QUALIFYING BET OPPORTUNITIES ({book_a} vs {book_b}) ---")
    qualifying_bets = scanner.find_qualifying_bets(book_a, book_b, max_loss_pct=0.03)
    if not qualifying_bets:
        print("No qualifying bets found under 3% loss.")
    else:
        for q in qualifying_bets[:3]: # Show top 3
            print(f"Match: {q['event']}")
            print(f"  Target: {q['target_bet']}")
            print(f"  Hedge : {q['hedge_bet']}")
            print(f"  Loss %: {q['loss_percentage']}%\n")

    print(f"\n--- FREE BET CONVERSION OPPORTUNITIES ({book_a} vs {book_b}) ---")
    free_bets = scanner.find_free_bet_conversions(book_a, book_b, free_bet_amount=100.0, min_conversion=0.65)
    if not free_bets:
        print("No free bet conversions found above 65%.")
    else:
        for fb in free_bets[:3]:
            print(f"Match: {fb['event']}")
            print(f"  Free Bet: {fb['free_bet']}")
            print(f"  Hedge   : {fb['hedge_bet']} | Hedge Stake: ${fb['lay_stake_needed']}")
            print(f"  Guaranteed Cash: ${fb['guaranteed_profit']} (Conversion: {fb['conversion_rate']}%)\n")

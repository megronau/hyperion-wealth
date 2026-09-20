from api_client import OddsAPIClient, Event
from calculators import calculate_arbitrage_percentage, calculate_arbitrage_stakes
from typing import List, Dict, Tuple

class ArbitrageScanner:
    def __init__(self, api_client: OddsAPIClient):
        self.api_client = api_client
        self.investment_amount = 500.0 # Starting bankroll

    def scan(self) -> List[Dict]:
        """
        Scans all available events for arbitrage opportunities.
        """
        events = self.api_client.get_odds()
        opportunities = []

        for event in events:
            # We are looking for H2H (head-to-head) markets first
            best_odds = {} # map of outcome_name -> {"price": float, "bookmaker": str}
            
            for bookmaker in event.bookmakers:
                for market in bookmaker.markets:
                    if market.key == 'h2h':
                        for outcome in market.outcomes:
                            name = outcome.name
                            price = outcome.price
                            
                            if name not in best_odds or price > best_odds[name]["price"]:
                                best_odds[name] = {
                                    "price": price,
                                    "bookmaker": bookmaker.title
                                }
            
            # Now we check if combining the best odds creates an arbitrage
            if len(best_odds) >= 2: # Usually 2 (e.g. Team A vs Team B) or 3 (Team A, Draw, Team B)
                odds_values = [v["price"] for v in best_odds.values()]
                names = list(best_odds.keys())
                
                try:
                    arb_pct = calculate_arbitrage_percentage(odds_values)
                    if arb_pct < 1.0: # Arbitrage exists!
                        stakes = calculate_arbitrage_stakes(self.investment_amount, odds_values)
                        
                        legs = []
                        profit = 0
                        
                        for i, name in enumerate(names):
                            leg_info = {
                                "outcome": name,
                                "bookmaker": best_odds[name]["bookmaker"],
                                "odds": best_odds[name]["price"],
                                "stake": stakes[i]
                            }
                            legs.append(leg_info)
                            
                        # Calculate profit based on the first leg (guaranteed equal across all legs)
                        profit = (stakes[0] * odds_values[0]) - self.investment_amount
                        
                        opp = {
                            "event_id": event.id,
                            "match": f"{event.home_team} vs {event.away_team}",
                            "arbitrage_percentage": arb_pct,
                            "guaranteed_profit": round(profit, 2),
                            "roi_percentage": round((profit / self.investment_amount) * 100, 2),
                            "legs": legs
                        }
                        opportunities.append(opp)
                except ValueError:
                    # Ignore errors related to odd values like <= 1.0
                    pass
                    
        return opportunities

if __name__ == "__main__":
    print("Initializing Scanner to hunt for live Arbitrage Opportunities...")
    # Initialize the client. It will automatically grab the ODDS_API_KEY from the environment.
    client = OddsAPIClient(use_mock=False)
    scanner = ArbitrageScanner(client)
    
    opportunities = scanner.scan()
    
    if not opportunities:
        print("No arbitrage opportunities found.")
    else:
        print(f"\nFound {len(opportunities)} Arbitrage Opportunities!\n")
        for opp in opportunities:
            print("-" * 40)
            print(f"Match: {opp['match']}")
            print(f"Arb %: {opp['arbitrage_percentage']*100:.2f}%")
            print(f"ROI  : +{opp['roi_percentage']}%")
            print(f"Guaranteed Profit: ${opp['guaranteed_profit']}")
            print("Legs to bet:")
            for leg in opp['legs']:
                print(f"  - Bet ${leg['stake']} on {leg['outcome']} @ {leg['odds']} at {leg['bookmaker']}")
            print("-" * 40)

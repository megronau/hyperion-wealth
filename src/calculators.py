def decimal_to_implied_probability(odds: float) -> float:
    """
    Converts decimal odds to implied probability.
    e.g., 2.00 -> 0.50 (50%)
    """
    if odds <= 1.0:
        raise ValueError("Decimal odds must be greater than 1.0")
    return 1.0 / odds

def american_to_decimal(american_odds: int) -> float:
    """
    Converts American odds (e.g. -110, +150) to decimal odds.
    """
    if american_odds > 0:
        return (american_odds / 100.0) + 1.0
    elif american_odds < 0:
        return (100.0 / abs(american_odds)) + 1.0
    else:
        raise ValueError("American odds cannot be zero")

def calculate_arbitrage_percentage(odds_list: list[float]) -> float:
    """
    Calculates the total implied probability across all mutually exclusive outcomes.
    If the sum is < 1.0, an arbitrage opportunity exists.
    """
    return sum([decimal_to_implied_probability(o) for o in odds_list])

def calculate_arbitrage_stakes(total_investment: float, odds_list: list[float]) -> list[float]:
    """
    Calculates how much to stake on each outcome to guarantee an equal profit
    regardless of the outcome, assuming an arbitrage opportunity exists.
    """
    arb_perc = calculate_arbitrage_percentage(odds_list)
    if arb_perc >= 1.0:
        raise ValueError(f"No arbitrage exists. Implied probability sum is {arb_perc}")
    
    stakes = []
    for odds in odds_list:
        implied_prob = decimal_to_implied_probability(odds)
        stake = (total_investment * implied_prob) / arb_perc
        stakes.append(round(stake, 2))
    return stakes

def calculate_kelly_criterion(decimal_odds: float, true_probability: float, fraction: float = 1.0) -> float:
    """
    Calculates the Kelly Criterion fraction of bankroll to wager on a positive EV bet.
    
    f* = (bp - q) / b
    where:
    b = decimal_odds - 1 (the net fractional odds)
    p = true_probability of winning
    q = probability of losing (1 - p)
    fraction = fractional Kelly (e.g., 0.5 for half-Kelly to reduce variance)
    
    Returns the percentage of bankroll to wager (e.g. 0.05 for 5%).
    """
    if true_probability <= 0 or true_probability >= 1:
        raise ValueError("True probability must be strictly between 0 and 1.")
        
    b = decimal_odds - 1.0
    p = true_probability
    q = 1.0 - p
    
    kelly_fraction = (b * p - q) / b
    
    # If edge is negative or zero, we don't bet
    if kelly_fraction <= 0:
        return 0.0
        
    return max(0.0, kelly_fraction * fraction)

def calculate_free_bet_conversion(free_bet_amount: float, back_odds: float, lay_odds: float, lay_commission: float = 0.0) -> dict:
    """
    Calculates the optimal lay stake to extract guaranteed cash from a free bet (SNR - Stake Not Returned).
    Used in matched betting.
    
    back_odds: The decimal odds on the sportsbook where you have the free bet.
    lay_odds: The decimal odds on the betting exchange (or another sportsbook).
    lay_commission: The commission charged by the exchange (e.g. 0.02 for 2%).
    """
    # For a SNR free bet, the profit if it wins is: free_bet_amount * (back_odds - 1)
    back_profit_if_win = free_bet_amount * (back_odds - 1)
    
    # We want our net profit to be exactly the same whether the back wins or the lay wins.
    # If back wins: Net Profit = back_profit_if_win - lay_liability
    # If lay wins: Net Profit = lay_stake_after_commission
    
    # lay_liability = lay_stake * (lay_odds - 1)
    # lay_stake_after_commission = lay_stake * (1 - lay_commission)
    
    # back_profit_if_win - (lay_stake * (lay_odds - 1)) = lay_stake * (1 - lay_commission)
    # back_profit_if_win = lay_stake * (lay_odds - 1 + 1 - lay_commission)
    # back_profit_if_win = lay_stake * (lay_odds - lay_commission)
    
    lay_stake = back_profit_if_win / (lay_odds - lay_commission)
    lay_liability = lay_stake * (lay_odds - 1)
    
    guaranteed_profit = lay_stake * (1 - lay_commission)
    conversion_rate = guaranteed_profit / free_bet_amount
    
    return {
        "lay_stake": round(lay_stake, 2),
        "lay_liability": round(lay_liability, 2),
        "guaranteed_profit": round(guaranteed_profit, 2),
        "conversion_rate": round(conversion_rate, 4)
    }

def calculate_sportsbook_free_bet_conversion(free_bet_amount: float, free_bet_odds: float, hedge_odds: float) -> dict:
    """
    Calculates the optimal hedge stake to extract cash from a free bet using another sportsbook (Dutching).
    This is different from lay betting on an exchange.
    """
    free_bet_profit = free_bet_amount * (free_bet_odds - 1.0)
    
    # We want: hedge_profit = free_bet_profit - hedge_stake
    # hedge_stake * (hedge_odds - 1) = free_bet_profit - hedge_stake
    # hedge_stake * hedge_odds = free_bet_profit
    hedge_stake = free_bet_profit / hedge_odds
    
    guaranteed_profit = hedge_stake * (hedge_odds - 1.0)
    conversion_rate = guaranteed_profit / free_bet_amount
    
    return {
        "hedge_stake": round(hedge_stake, 2),
        "guaranteed_profit": round(guaranteed_profit, 2),
        "conversion_rate": round(conversion_rate, 4)
    }

if __name__ == "__main__":
    # Test Arbitrage
    # FanDuel offers Team A at +110 (2.10). DraftKings offers Team B at +105 (2.05).
    print("--- Arbitrage Example ---")
    odds = [2.10, 2.05]
    arb_pct = calculate_arbitrage_percentage(odds)
    print(f"Odds: {odds} -> Arbitrage %: {arb_pct:.4f}")
    if arb_pct < 1.0:
        stakes = calculate_arbitrage_stakes(500.0, odds)
        print(f"Stakes for $500 total: {stakes}")
        profit = (stakes[0] * odds[0]) - 500.0
        print(f"Guaranteed Profit: ${profit:.2f} ({(profit/500)*100:.2f}%)")
    
    print("\n--- Free Bet Conversion Example ---")
    # We have a $50 free bet. We find a market: Back at +400 (5.00), Lay at +420 (5.20)
    fb = calculate_free_bet_conversion(50.0, 5.0, 5.20, 0.0)
    print(f"Converting $50 Free Bet at 5.0 back, 5.2 lay:")
    print(fb)

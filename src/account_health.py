import math
import random

class AccountHealthManager:
    """
    Manages account health by obfuscating algorithmic betting patterns.
    Implements stake rounding, market-aware capping, and camouflage bets.
    """
    def __init__(self, prop_cap: float = 50.0, main_line_cap: float = 500.0, mug_bet_chance: float = 0.05):
        self.prop_cap = prop_cap
        self.main_line_cap = main_line_cap
        self.mug_bet_chance = mug_bet_chance

    def apply_cunning_strategy(self, raw_stake: float, market_key: str) -> float:
        """
        Applies cunning limits and rounds the stake.
        """
        if raw_stake <= 0:
            return 0.0

        # 1. Apply Market-Aware Capping
        if 'player' in market_key.lower() or 'prop' in market_key.lower():
            capped_stake = min(raw_stake, self.prop_cap)
        else:
            capped_stake = min(raw_stake, self.main_line_cap)

        # 2. Rounding (Round to nearest $5 for stakes > $10, otherwise nearest $1)
        if capped_stake >= 10.0:
            final_stake = float(math.floor(capped_stake / 5.0) * 5)
        else:
            final_stake = float(math.floor(capped_stake))
            
        # Ensure minimum $1
        return max(1.0, final_stake)

    def should_place_mug_bet(self) -> bool:
        """
        Randomly signals whether a mug (camouflage) bet should be placed.
        """
        return random.random() < self.mug_bet_chance

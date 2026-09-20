import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calculators import (
    decimal_to_implied_probability,
    american_to_decimal,
    calculate_arbitrage_percentage,
    calculate_arbitrage_stakes,
    calculate_kelly_criterion,
    calculate_free_bet_conversion
)

class TestCalculators(unittest.TestCase):

    def test_decimal_to_implied_probability(self):
        self.assertAlmostEqual(decimal_to_implied_probability(2.0), 0.5)
        self.assertAlmostEqual(decimal_to_implied_probability(4.0), 0.25)
        with self.assertRaises(ValueError):
            decimal_to_implied_probability(0.5)

    def test_american_to_decimal(self):
        self.assertAlmostEqual(american_to_decimal(150), 2.50)
        self.assertAlmostEqual(american_to_decimal(-150), 1.666666, places=5)
        self.assertAlmostEqual(american_to_decimal(100), 2.00)
        with self.assertRaises(ValueError):
            american_to_decimal(0)

    def test_calculate_arbitrage_percentage(self):
        # 2.10 (47.6%) and 2.05 (48.8%) = 96.4%
        pct = calculate_arbitrage_percentage([2.10, 2.05])
        self.assertAlmostEqual(pct, 0.96399, places=4)
        
        # 1.50 (66.6%) and 3.00 (33.3%) = 100% (No arb)
        pct2 = calculate_arbitrage_percentage([1.50, 3.00])
        self.assertAlmostEqual(pct2, 1.0)

    def test_calculate_arbitrage_stakes(self):
        odds = [2.10, 2.05]
        stakes = calculate_arbitrage_stakes(500.0, odds)
        # Total stake should be roughly 500
        self.assertAlmostEqual(sum(stakes), 500.0, delta=1.0) # Delta because of rounding
        
        # Payout should be equal on both sides
        payout1 = stakes[0] * odds[0]
        payout2 = stakes[1] * odds[1]
        
        self.assertAlmostEqual(payout1, payout2, delta=2.0)
        self.assertTrue(payout1 > 500.0) # Guaranteed profit

    def test_kelly_criterion(self):
        # Coin flip paying +110 (2.10). True prob = 50%.
        # b = 1.1, p = 0.5, q = 0.5
        # f = (1.1 * 0.5 - 0.5) / 1.1 = (0.55 - 0.5) / 1.1 = 0.05 / 1.1 = 0.04545 (4.54%)
        kelly = calculate_kelly_criterion(2.10, 0.5)
        self.assertAlmostEqual(kelly, 0.04545, places=4)
        
        # Negative EV, should return 0
        kelly_neg = calculate_kelly_criterion(1.90, 0.5)
        self.assertEqual(kelly_neg, 0.0)

    def test_free_bet_conversion(self):
        # Back at 5.0, Lay at 5.2, 0% commission, $50 FB
        # Back profit if win = 50 * 4 = 200
        # Lay stake = 200 / 5.2 = 38.46
        # Guaranteed profit = 38.46
        res = calculate_free_bet_conversion(50.0, 5.0, 5.20)
        self.assertAlmostEqual(res["lay_stake"], 38.46, places=2)
        self.assertAlmostEqual(res["guaranteed_profit"], 38.46, places=2)
        self.assertAlmostEqual(res["conversion_rate"], 0.7692, places=4)

if __name__ == '__main__':
    unittest.main()

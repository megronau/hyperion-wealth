import os

DEFAULT_WIN_FEE = 0.02


def win_fee_percentage() -> float:
    """Commission taken from winning profit (Kalshi-style). Losses are not fee'd."""
    raw = os.environ.get("FEE_PERCENTAGE", str(DEFAULT_WIN_FEE))
    try:
        return max(0.0, min(0.5, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_WIN_FEE


def net_decimal_odds(decimal_odds: float, fee_percentage: float = None) -> float:
    """Odds after a win-only commission, for Kelly/EV sizing."""
    fee = DEFAULT_WIN_FEE if fee_percentage is None else fee_percentage
    return 1.0 + (float(decimal_odds) - 1.0) * (1.0 - fee)


def winning_profit(decimal_odds: float, stake: float, fee_percentage: float = None) -> float:
    fee = DEFAULT_WIN_FEE if fee_percentage is None else fee_percentage
    return (float(decimal_odds) - 1.0) * float(stake) * (1.0 - fee)

import os

SIM_MODES = {"sim", "paper"}
REAL_ODDS_MODES = {"live_paper", "live"}


def get_trading_mode() -> str:
    """sim = invented games. live_paper = real odds, paper fills. live = same until Kalshi is real."""
    forced = (os.environ.get("TRADING_MODE") or "").strip().lower()
    if forced in ("paper", "sim"):
        return "sim"
    if forced in REAL_ODDS_MODES:
        return forced
    return "live_paper"


def is_sim(mode: str = None) -> bool:
    return (mode or get_trading_mode()) in SIM_MODES or (mode or get_trading_mode()) == "sim"


def uses_real_odds(mode: str = None) -> bool:
    return (mode or get_trading_mode()) in REAL_ODDS_MODES

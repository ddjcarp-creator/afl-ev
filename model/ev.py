"""
Calculates expected value for a bet given your model's probability and the
bookmaker's offered decimal odds, plus Kelly-based stake sizing.
"""
import numpy as np


def calculate_ev(model_prob: float, decimal_odds: float, stake: float = 1.0) -> float:
    """
    EV per unit staked. Positive EV means the bookmaker's price offers more
    value than your model thinks is fair.

    EV = (model_prob * (decimal_odds - 1) * stake) - ((1 - model_prob) * stake)
    """
    if np.isnan(model_prob) or decimal_odds <= 1:
        return np.nan
    profit_if_win = (decimal_odds - 1) * stake
    return (model_prob * profit_if_win) - ((1 - model_prob) * stake)


def ev_percentage(model_prob: float, decimal_odds: float) -> float:
    """EV as a percentage of stake - the standard way +EV is usually quoted."""
    ev = calculate_ev(model_prob, decimal_odds, stake=1.0)
    return ev if np.isnan(ev) else ev * 100


def edge(model_prob: float, fair_implied_prob: float) -> float:
    """Simple edge: your probability minus the devigged market probability."""
    if np.isnan(model_prob) or np.isnan(fair_implied_prob):
        return np.nan
    return model_prob - fair_implied_prob


def kelly_fraction(model_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly stake as a fraction of bankroll.
    f* = (b*p - q) / b, where b = decimal_odds - 1, p = win prob, q = 1 - p.
    Returns 0 if the Kelly formula suggests no bet (negative edge).
    """
    if np.isnan(model_prob) or decimal_odds <= 1:
        return 0.0
    b = decimal_odds - 1
    p = model_prob
    q = 1 - p
    f = (b * p - q) / b
    return max(f, 0.0)


def suggested_stake(model_prob: float, decimal_odds: float, bankroll: float,
                     kelly_fraction_multiplier: float = 0.25) -> float:
    """
    Suggested stake using fractional Kelly (default: quarter Kelly) to reduce
    variance versus full Kelly, which is aggressive and sensitive to model error.
    """
    f = kelly_fraction(model_prob, decimal_odds)
    return round(bankroll * f * kelly_fraction_multiplier, 2)

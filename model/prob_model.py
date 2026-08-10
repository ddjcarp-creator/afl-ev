"""
Estimates the probability of a player going over/under a given prop line,
using a Poisson distribution fitted to their recent game stats.

Poisson works reasonably well for count stats (disposals, marks, tackles,
goals) since they're non-negative integers. It's a simplification - it
assumes each disposal/goal is roughly independent and ignores things like
blowout-game garbage time, role changes, or weather - but it's a solid,
explainable starting point.
"""
import numpy as np
import pandas as pd
from scipy.stats import poisson
from config import RECENT_GAMES_WINDOW, DECAY_RATE


def weighted_recent_average(recent_games: pd.DataFrame, stat_col: str) -> float:
    """
    Compute an exponentially-decayed average of a player's recent games,
    weighting the most recent games most heavily.
    """
    values = recent_games[stat_col].dropna().values
    if len(values) == 0:
        return np.nan

    values = values[:RECENT_GAMES_WINDOW]  # most recent N games
    weights = np.array([DECAY_RATE ** i for i in range(len(values))])
    return np.average(values, weights=weights)


def estimate_lambda(recent_games: pd.DataFrame, stat_col: str,
                     opponent_adjustment: float = 1.0) -> float:
    """
    Estimate the Poisson rate parameter (lambda) for a player's stat,
    optionally adjusted for opponent strength.

    opponent_adjustment: multiplier >1 means opponent concedes more of this
    stat than average (favorable matchup), <1 means tougher matchup.
    Defaults to 1.0 (no adjustment) until you wire up opponent-level data.
    """
    base_rate = weighted_recent_average(recent_games, stat_col)
    if np.isnan(base_rate):
        return np.nan
    return base_rate * opponent_adjustment


def prob_over_under(lam: float, line: float) -> dict:
    """
    Given a Poisson rate (lambda) and a betting line (e.g. 22.5 disposals),
    return the model's probability of Over and Under.

    Lines are typically set at X.5 to avoid pushes, so we split cleanly at
    the line: P(Over) = P(X > line), P(Under) = P(X <= line).
    """
    if np.isnan(lam):
        return {"prob_over": np.nan, "prob_under": np.nan}

    threshold = int(np.floor(line))  # e.g. line=22.5 -> threshold=22
    prob_under_or_equal = poisson.cdf(threshold, mu=lam)
    prob_over = 1 - prob_under_or_equal

    return {"prob_over": prob_over, "prob_under": prob_under_or_equal}


def model_prop_probability(recent_games: pd.DataFrame, stat_col: str,
                            line: float, opponent_adjustment: float = 1.0) -> dict:
    """Convenience wrapper: recent games -> lambda -> over/under probabilities."""
    lam = estimate_lambda(recent_games, stat_col, opponent_adjustment)
    result = prob_over_under(lam, line)
    result["lambda"] = lam
    return result

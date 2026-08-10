"""
Removes the bookmaker's margin ("vig"/"overround") from a pair of over/under
odds so you get a fair implied probability to compare your model against.

Bookmaker odds always sum to slightly more than 100% implied probability -
that extra is their margin. If you compare your model's probability directly
against raw implied odds, you're comparing against an inflated number and
will systematically underestimate your edge (or think you have edge you don't).
"""
import numpy as np


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds (e.g. 1.91) to implied probability (e.g. 0.524)."""
    if decimal_odds <= 0:
        return float("nan")
    return 1 / decimal_odds


def devig_multiplicative(over_odds: float, under_odds: float) -> dict:
    """
    Multiplicative devigging: scale both implied probabilities down
    proportionally so they sum to exactly 1.0. Simple and works well when
    the margin is roughly evenly distributed between the two sides.
    """
    p_over_raw = decimal_to_implied_prob(over_odds)
    p_under_raw = decimal_to_implied_prob(under_odds)
    total = p_over_raw + p_under_raw

    if total == 0 or np.isnan(total):
        return {"fair_prob_over": float("nan"), "fair_prob_under": float("nan"), "overround": float("nan")}

    return {
        "fair_prob_over": p_over_raw / total,
        "fair_prob_under": p_under_raw / total,
        "overround": total - 1.0,  # the bookmaker's margin, e.g. 0.05 = 5%
    }


def devig_shin(over_odds: float, under_odds: float, max_iter: int = 100, tol: float = 1e-10) -> dict:
    """
    Shin's method devigging - accounts for the fact that bookmakers often
    shade margin more heavily onto the less-likely outcome (to protect
    against informed bettors). Slightly more accurate than multiplicative
    for lines with a large favorite/underdog gap; for close-to-even props
    the two methods will give very similar results.
    """
    p_over_raw = decimal_to_implied_prob(over_odds)
    p_under_raw = decimal_to_implied_prob(under_odds)
    total = p_over_raw + p_under_raw

    if total <= 1.0 or np.isnan(total):
        # No margin to remove, or bad odds input - fall back to multiplicative
        return devig_multiplicative(over_odds, under_odds)

    z = 0.0
    for _ in range(max_iter):
        sqrt_term_over = np.sqrt(z ** 2 + 4 * (1 - z) * (p_over_raw ** 2) / total)
        sqrt_term_under = np.sqrt(z ** 2 + 4 * (1 - z) * (p_under_raw ** 2) / total)
        fair_over = (sqrt_term_over - z) / (2 * (1 - z)) if z != 1 else p_over_raw
        fair_under = (sqrt_term_under - z) / (2 * (1 - z)) if z != 1 else p_under_raw
        new_z = fair_over + fair_under - 1.0

        if abs(new_z - z) < tol:
            z = new_z
            break
        z = new_z

    fair_over = np.clip(fair_over, 0, 1)
    fair_under = np.clip(fair_under, 0, 1)
    norm = fair_over + fair_under
    return {
        "fair_prob_over": fair_over / norm,
        "fair_prob_under": fair_under / norm,
        "overround": total - 1.0,
    }

"""
Orchestrates the full pipeline: fetch odds -> fetch stats -> model probabilities
-> devig market odds -> calculate EV -> return a ranked DataFrame of opportunities.
"""
import pandas as pd
import numpy as np

from data_sources import odds_api, stats_data
from model.prob_model import model_prop_probability
from model.devig import devig_shin
from model.ev import ev_percentage, edge, suggested_stake
from config import EV_THRESHOLD, BANKROLL, KELLY_FRACTION

# Maps The Odds API market keys to the stat column names used in player_stats.csv
MARKET_TO_STAT_COL = {
    "player_disposals": "disposals",
    "player_goals": "goals",
    "player_marks": "marks",
    "player_tackles": "tackles",
}


def run_pipeline(year: int = None, force_refresh_stats: bool = False) -> pd.DataFrame:
    """
    Runs the full pipeline and returns a DataFrame of all player props with
    model probability, fair market probability, and EV attached - ready to
    filter/sort in the dashboard.
    """
    props_df = odds_api.get_all_player_props()
    if props_df.empty:
        return pd.DataFrame()

    stats_df = stats_data.load_player_stats(year=year, force_refresh=force_refresh_stats)
    if stats_df.empty:
        return pd.DataFrame()

    # Pivot props so each (event, bookmaker, market, player, line) has both
    # an Over and Under price in the same row - needed for devigging.
    pivoted = props_df.pivot_table(
        index=["event_id", "home_team", "away_team", "commence_time",
               "bookmaker", "market", "player", "line"],
        columns="side", values="price", aggfunc="first"
    ).reset_index()

    if "Over" not in pivoted.columns or "Under" not in pivoted.columns:
        return pd.DataFrame()

    results = []
    for _, row in pivoted.iterrows():
        stat_col = MARKET_TO_STAT_COL.get(row["market"])
        if stat_col is None or pd.isna(row["Over"]) or pd.isna(row["Under"]):
            continue

        recent_games = stats_data.get_player_recent_games(stats_df, row["player"])
        if recent_games.empty:
            continue

        model_result = model_prop_probability(recent_games, stat_col, row["line"])
        fair = devig_shin(row["Over"], row["Under"])

        for side, price_col, model_prob_key, fair_prob_key in [
            ("Over", "Over", "prob_over", "fair_prob_over"),
            ("Under", "Under", "prob_under", "fair_prob_under"),
        ]:
            model_prob = model_result.get(model_prob_key)
            fair_prob = fair.get(fair_prob_key)
            decimal_odds = row[price_col]

            if model_prob is None or np.isnan(model_prob):
                continue

            results.append({
                "player": row["player"],
                "market": row["market"],
                "line": row["line"],
                "side": side,
                "bookmaker": row["bookmaker"],
                "odds": decimal_odds,
                "model_prob": round(model_prob, 4),
                "fair_market_prob": round(fair_prob, 4) if fair_prob is not None else np.nan,
                "edge": round(edge(model_prob, fair_prob), 4) if fair_prob is not None else np.nan,
                "ev_pct": round(ev_percentage(model_prob, decimal_odds), 2),
                "suggested_stake": suggested_stake(model_prob, decimal_odds, BANKROLL, KELLY_FRACTION),
                "match": f"{row['home_team']} vs {row['away_team']}",
                "commence_time": row["commence_time"],
            })

    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    return results_df.sort_values("ev_pct", ascending=False)


def get_plus_ev_bets(results_df: pd.DataFrame, threshold: float = None) -> pd.DataFrame:
    """Filter to only bets above the EV threshold (default from config)."""
    threshold = threshold if threshold is not None else EV_THRESHOLD * 100
    if results_df.empty:
        return results_df
    return results_df[results_df["ev_pct"] >= threshold]

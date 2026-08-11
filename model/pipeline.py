"""
Orchestrates the full pipeline: fetch odds -> fetch stats -> model probabilities
-> devig market odds -> calculate EV -> return a ranked DataFrame of opportunities.
"""
import pandas as pd
import numpy as np

from data_sources import odds_api, stats_data
from model.prob_model import model_prop_probability, model_anytime_probability
from model.devig import devig_shin
from model.ev import ev_percentage, edge, suggested_stake
from config import EV_THRESHOLD, BANKROLL, KELLY_FRACTION

# Maps line-based market keys to the stat column in player_stats.csv.
# player_disposals is a true Over/Under pair. player_goals_scored_over may or
# may not include Under outcomes depending on your bookmakers (see note in
# data_sources/odds_api.py) - the loop below handles both cases automatically.
LINE_MARKET_TO_STAT_COL = {
    "player_disposals": "disposals",
    "player_goals_scored_over": "goals",
}

# Maps the anytime binary market to its stat column
ANYTIME_MARKET_TO_STAT_COL = {
    "player_goal_scorer_anytime": "goals",
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

    results = []

    # --- Line-based markets (disposals, goals) ---
    line_props = props_df[props_df["market"].isin(LINE_MARKET_TO_STAT_COL.keys())]
    pivoted = line_props.pivot_table(
        index=["event_id", "home_team", "away_team", "commence_time",
               "bookmaker", "market", "player", "line"],
        columns="side", values="price", aggfunc="first"
    ).reset_index()

    has_over = "Over" in pivoted.columns
    has_under = "Under" in pivoted.columns

    if has_over:
        for _, row in pivoted.iterrows():
            stat_col = LINE_MARKET_TO_STAT_COL.get(row["market"])
            over_price = row.get("Over")
            under_price = row.get("Under") if has_under else None
            if stat_col is None or pd.isna(over_price):
                continue

            recent_games = stats_data.get_player_recent_games(stats_df, row["player"])
            if recent_games.empty:
                continue

            model_result = model_prop_probability(recent_games, stat_col, row["line"])

            if under_price is not None and not pd.isna(under_price):
                # Both sides available - devig properly, same as disposals.
                fair = devig_shin(over_price, under_price)
                sides = [
                    ("Over", over_price, "prob_over", fair.get("fair_prob_over")),
                    ("Under", under_price, "prob_under", fair.get("fair_prob_under")),
                ]
            else:
                # Over-only (e.g. player_goals_scored_over on books that don't
                # offer a matching Under) - no pair to devig against, so we
                # fall back to raw implied probability, same conservative
                # treatment as the anytime-scorer market below.
                sides = [
                    ("Over", over_price, "prob_over", 1 / over_price if over_price > 0 else np.nan),
                ]

            for side, decimal_odds, model_prob_key, fair_prob in sides:
                model_prob = model_result.get(model_prob_key)
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
                    "fair_market_prob": round(fair_prob, 4) if fair_prob is not None and not np.isnan(fair_prob) else np.nan,
                    "edge": round(edge(model_prob, fair_prob), 4) if fair_prob is not None and not np.isnan(fair_prob) else np.nan,
                    "ev_pct": round(ev_percentage(model_prob, decimal_odds), 2),
                    "suggested_stake": suggested_stake(model_prob, decimal_odds, BANKROLL, KELLY_FRACTION),
                    "match": f"{row['home_team']} vs {row['away_team']}",
                    "commence_time": row["commence_time"],
                })

    # --- Anytime goalscorer (binary "Yes" price, no Under to devig against) ---
    anytime_props = props_df[props_df["market"].isin(ANYTIME_MARKET_TO_STAT_COL.keys())]
    for _, row in anytime_props.iterrows():
        if pd.isna(row["price"]):
            continue
        stat_col = ANYTIME_MARKET_TO_STAT_COL.get(row["market"])
        recent_games = stats_data.get_player_recent_games(stats_df, row["player"])
        if recent_games.empty:
            continue

        model_result = model_anytime_probability(recent_games, stat_col)
        model_prob = model_result["prob_yes"]
        if np.isnan(model_prob):
            continue

        # No paired "No" price to devig against here - using raw implied
        # probability as the market comparison, same approach as the
        # football bot's anytime-goalscorer market. Treat EV on this market
        # a bit more conservatively than the devigged disposals numbers.
        market_implied_prob = 1 / row["price"] if row["price"] > 0 else np.nan

        results.append({
            "player": row["player"],
            "market": row["market"],
            "line": None,
            "side": "Yes",
            "bookmaker": row["bookmaker"],
            "odds": row["price"],
            "model_prob": round(model_prob, 4),
            "fair_market_prob": round(market_implied_prob, 4),
            "edge": round(edge(model_prob, market_implied_prob), 4),
            "ev_pct": round(ev_percentage(model_prob, row["price"]), 2),
            "suggested_stake": suggested_stake(model_prob, row["price"], BANKROLL, KELLY_FRACTION),
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

"""
AFL Prop EV Bot - Streamlit dashboard entry point.

Run locally with: streamlit run app.py
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from model.pipeline import run_pipeline, get_plus_ev_bets
from config import ODDS_API_KEY, EV_THRESHOLD, BANKROLL

st.set_page_config(page_title="AFL Prop EV Bot", page_icon="🏉", layout="wide")

st.title("🏉 AFL Prop EV Bot")
st.caption("Flags +EV player prop bets by comparing a Poisson model against devigged bookmaker odds.")

# --- Sidebar controls ---
with st.sidebar:
    st.header("Settings")

    if not ODDS_API_KEY:
        st.error("No ODDS_API_KEY found. Add it to your .env file or Streamlit secrets.")

    ev_threshold_pct = st.slider(
        "Minimum EV to flag (%)", min_value=0.0, max_value=20.0,
        value=EV_THRESHOLD * 100, step=0.5
    )
    bankroll = st.number_input("Bankroll ($)", min_value=0.0, value=BANKROLL, step=50.0)
    refresh_stats = st.checkbox("Force refresh player stats (re-scrape AFL Tables)", value=False)

    run_button = st.button("🔄 Fetch odds & run model", type="primary", use_container_width=True)

    st.markdown("---")
    st.caption(
        "Data sources: [The Odds API](https://the-odds-api.com/) for odds, "
        "[AFL Tables](https://afltables.com) for player stats."
    )

# --- Session state so results persist between interactions ---
if "results_df" not in st.session_state:
    st.session_state.results_df = pd.DataFrame()
if "last_run" not in st.session_state:
    st.session_state.last_run = None

if run_button:
    with st.spinner("Fetching odds and player stats, then running the model..."):
        try:
            results = run_pipeline(force_refresh_stats=refresh_stats)
            st.session_state.results_df = results
            st.session_state.last_run = datetime.now()
        except Exception as e:
            st.error(f"Something went wrong running the pipeline: {e}")

results_df = st.session_state.results_df

if st.session_state.last_run:
    st.caption(f"Last updated: {st.session_state.last_run.strftime('%Y-%m-%d %H:%M:%S')}")

if results_df.empty:
    st.info(
        "No results yet. Click **Fetch odds & run model** in the sidebar to pull "
        "current AFL player props and check for +EV opportunities.\n\n"
        "If this is your first run, make sure you've added your Odds API key "
        "(see sidebar) - player stats will auto-scrape from AFL Tables on first use, "
        "which can take a minute or two."
    )
else:
    plus_ev = get_plus_ev_bets(results_df, threshold=ev_threshold_pct)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total props scanned", len(results_df))
    col2.metric("+EV opportunities", len(plus_ev))
    col3.metric("Best EV found", f"{results_df['ev_pct'].max():.1f}%" if not results_df.empty else "—")

    st.subheader(f"✅ +EV Bets (≥ {ev_threshold_pct:.1f}%)")
    if plus_ev.empty:
        st.write("No bets currently meet your EV threshold. Try lowering it or check back closer to game time.")
    else:
        display_df = plus_ev.copy()
        display_df["commence_time"] = pd.to_datetime(display_df["commence_time"]).dt.strftime("%a %d %b, %I:%M %p")
        st.dataframe(
            display_df[[
                "player", "market", "line", "side", "bookmaker", "odds",
                "model_prob", "fair_market_prob", "edge", "ev_pct",
                "suggested_stake", "match", "commence_time"
            ]].rename(columns={
                "model_prob": "Model Prob", "fair_market_prob": "Fair Market Prob",
                "edge": "Edge", "ev_pct": "EV %", "suggested_stake": "Suggested Stake ($)",
                "player": "Player", "market": "Market", "line": "Line", "side": "Side",
                "bookmaker": "Bookmaker", "odds": "Odds", "match": "Match",
                "commence_time": "Kickoff",
            }),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("View all scanned props (including negative EV)"):
        st.dataframe(results_df, use_container_width=True, hide_index=True)

st.markdown("---")
with st.expander("🔧 Diagnostics (use this if results are empty)"):
    st.caption("Runs each pipeline stage separately so you can see exactly where data is being lost.")
    if st.button("Run diagnostics"):
        from data_sources import odds_api as _odds_api, stats_data as _stats_data

        st.write("**1. Odds API**")
        try:
            props, odds_errors = _odds_api.get_all_player_props_verbose()
            st.write(f"Player props fetched: **{len(props)} rows**")
            if not props.empty:
                st.write("Sample markets found:", list(props['market'].unique()[:10]))
                st.write("Sample players found:", list(props['player'].unique()[:10]))
            if odds_errors:
                st.write(f"**{len(odds_errors)} issue(s) encountered while fetching odds:**")
                for err in odds_errors[:15]:  # cap so the page doesn't get huge
                    st.code(err)
                if len(odds_errors) > 15:
                    st.caption(f"...and {len(odds_errors) - 15} more.")
            if props.empty and not odds_errors:
                st.warning(
                    "Odds are empty with no specific errors logged. Likely causes: no "
                    "upcoming AFL events right now, or your bookmakers/plan don't offer "
                    "player prop markets for AFL."
                )
        except Exception as e:
            st.error(f"Error fetching odds: {e}")
            props = None

        st.write("**2. Player stats**")
        try:
            stats, stats_errors = _stats_data.scrape_all_teams_verbose()
            st.write(f"Player stats loaded: **{len(stats)} rows**")
            if not stats.empty:
                st.write("Sample players in stats:", list(stats['player'].unique()[:10]))
            if stats_errors:
                st.write(f"**{len(stats_errors)} issue(s) encountered while scraping stats:**")
                for err in stats_errors[:15]:
                    st.code(err)
                if len(stats_errors) > 15:
                    st.caption(f"...and {len(stats_errors) - 15} more.")
            if stats.empty and not stats_errors:
                st.warning(
                    "Stats are empty with no specific errors logged - unexpected, "
                    "worth re-running or checking data_sources/stats_data.py directly."
                )
        except Exception as e:
            st.error(f"Error loading stats: {e}")
            stats = None

        st.write("**3. Name overlap between odds and stats**")
        if props is not None and stats is not None and not props.empty and not stats.empty:
            odds_players = set(p.lower() for p in props['player'].dropna().unique())
            stats_players = set(p.lower() for p in stats['player'].dropna().unique())
            overlap = odds_players & stats_players
            st.write(f"Players in odds: **{len(odds_players)}**, players in stats: **{len(stats_players)}**")
            st.write(f"Matching players: **{len(overlap)}**")
            if len(overlap) == 0:
                st.warning(
                    "No name overlap. Player name formatting likely differs between the "
                    "odds API (e.g. 'M. Bontempelli') and AFL Tables (e.g. 'Marcus Bontempelli')."
                )
        else:
            st.caption("Skipped - need both odds and stats to be non-empty first.")

st.markdown("---")
st.caption(
    "⚠️ This tool surfaces model output for informational purposes only - it does not "
    "place bets and isn't financial advice. The probability model is a simplified "
    "Poisson estimate; validate it against historical results before staking real money. "
    "Gambling involves financial risk."
)

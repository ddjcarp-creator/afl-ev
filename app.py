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
st.caption(
    "⚠️ This tool surfaces model output for informational purposes only - it does not "
    "place bets and isn't financial advice. The probability model is a simplified "
    "Poisson estimate; validate it against historical results before staking real money. "
    "Gambling involves financial risk."
)

"""
AFL Prop EV Bot - Streamlit dashboard entry point.
Run locally with: streamlit run app.py
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from model.pipeline import run_pipeline, get_plus_ev_bets
from config import ODDS_API_KEY, EV_THRESHOLD, BANKROLL, BOOKMAKER_FILTER

st.set_page_config(page_title="AFL Prop EV Bot", page_icon="🏉", layout="wide")

# --- Light custom styling on top of the theme ---
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetric"] {
        background-color: #1A1F2B;
        border: 1px solid #2A3040;
        border-radius: 10px;
        padding: 14px 18px;
    }
    div[data-testid="stMetricLabel"] { font-size: 0.85rem; opacity: 0.75; }
    .ev-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .ev-strong { background-color: rgba(46, 204, 113, 0.18); color: #2ECC71; }
    .ev-moderate { background-color: rgba(232, 88, 12, 0.18); color: #E8580C; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1A1F2B;
        border-radius: 8px 8px 0 0;
        padding: 8px 18px;
    }
    hr { margin: 1.5rem 0; opacity: 0.15; }
</style>
""", unsafe_allow_html=True)

MARKET_LABELS = {
    "player_disposals": "Disposals",
    "player_goals_scored_over": "Goals (Over)",
    "player_goal_scorer_anytime": "Anytime Goalscorer",
}
BOOKMAKER_DISPLAY_NAMES = {"ladbrokes_au": "Ladbrokes", "neds": "Neds", "pointsbetau": "PointsBet"}

st.title("🏉 AFL Prop EV Bot")
st.caption(
    f"Comparing a Poisson model against devigged odds from "
    f"**{', '.join(BOOKMAKER_DISPLAY_NAMES.get(b, b) for b in BOOKMAKER_FILTER)}**."
)

# --- Sidebar controls ---
with st.sidebar:
    st.header("⚙️ Settings")

    if not ODDS_API_KEY:
        st.error("No ODDS_API_KEY found. Add it to your .env file or Streamlit secrets.")

    ev_threshold_pct = st.slider(
        "Minimum EV to flag (%)", min_value=0.0, max_value=20.0,
        value=EV_THRESHOLD * 100, step=0.5
    )
    bankroll = st.number_input("Bankroll ($)", min_value=0.0, value=BANKROLL, step=50.0)
    refresh_stats = st.checkbox("Force refresh player stats", value=False)

    run_button = st.button("🔄  Fetch odds & run model", type="primary", use_container_width=True)

    st.markdown("---")
    st.caption("**Data sources**")
    st.caption("Odds: [The Odds API](https://the-odds-api.com/)")
    st.caption("Stats: [AFL Tables](https://afltables.com)")

# --- Session state ---
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
    st.caption(f"🕒 Last updated {st.session_state.last_run.strftime('%a %d %b, %I:%M %p')}")

if results_df.empty:
    st.info(
        "No results yet. Click **Fetch odds & run model** in the sidebar to pull "
        "current AFL player props and check for +EV opportunities.\n\n"
        "First run will scrape AFL Tables for player stats, which can take a minute or two."
    )
else:
    plus_ev = get_plus_ev_bets(results_df, threshold=ev_threshold_pct)

    col1, col2, col3 = st.columns(3)
    col1.metric("Props scanned", len(results_df))
    col2.metric("+EV opportunities", len(plus_ev))
    col3.metric("Best EV found", f"{results_df['ev_pct'].max():.1f}%" if not results_df.empty else "—")

    st.markdown("")

    def render_bet_table(df: pd.DataFrame, empty_message: str):
        if df.empty:
            st.caption(empty_message)
            return
        display_df = df.copy()
        display_df["commence_time"] = pd.to_datetime(display_df["commence_time"]).dt.strftime("%a %d %b, %I:%M %p")
        display_df["bookmaker"] = display_df["bookmaker"]

        st.dataframe(
            display_df[[
                "player", "side", "line", "odds", "bookmaker",
                "model_prob", "fair_market_prob", "ev_pct",
                "suggested_stake", "match", "commence_time"
            ]].rename(columns={
                "player": "Player", "side": "Side", "line": "Line", "odds": "Odds",
                "bookmaker": "Bookmaker", "model_prob": "Model %", "fair_market_prob": "Market %",
                "ev_pct": "EV %", "suggested_stake": "Stake ($)",
                "match": "Match", "commence_time": "Kickoff",
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Model %": st.column_config.ProgressColumn("Model %", format="%.1f%%", min_value=0, max_value=1),
                "Market %": st.column_config.ProgressColumn("Market %", format="%.1f%%", min_value=0, max_value=1),
                "EV %": st.column_config.NumberColumn("EV %", format="%.1f%%"),
                "Stake ($)": st.column_config.NumberColumn("Stake ($)", format="$%.0f"),
                "Odds": st.column_config.NumberColumn("Odds", format="%.2f"),
            },
        )

    st.subheader(f"✅ +EV Bets  ·  threshold ≥ {ev_threshold_pct:.1f}%")

    tab_all, tab_disposals, tab_goals_over, tab_anytime = st.tabs([
        "All markets", "Disposals", "Goals (Over)", "Anytime Goalscorer"
    ])

    with tab_all:
        render_bet_table(plus_ev, "No bets currently meet your EV threshold across any market.")

    with tab_disposals:
        subset = plus_ev[plus_ev["market"] == "player_disposals"]
        render_bet_table(subset, "No +EV disposals bets right now.")

    with tab_goals_over:
        subset = plus_ev[plus_ev["market"] == "player_goals_scored_over"]
        render_bet_table(subset, "No +EV goals-over bets right now.")

    with tab_anytime:
        subset = plus_ev[plus_ev["market"] == "player_goal_scorer_anytime"]
        render_bet_table(subset, "No +EV anytime goalscorer bets right now.")

    with st.expander("View all scanned props (including negative EV)"):
        all_display = results_df.copy()
        all_display["market"] = all_display["market"].map(MARKET_LABELS).fillna(all_display["market"])
        st.dataframe(all_display, use_container_width=True, hide_index=True)

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
                for err in odds_errors[:15]:
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
                    "odds API and the stats source."
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

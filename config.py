"""
Central config loader. Reads from .env locally, or from Streamlit secrets
when deployed on Streamlit Community Cloud.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default=None):
    """Try Streamlit secrets first (for cloud deploys), fall back to env vars."""
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


ODDS_API_KEY = _get("ODDS_API_KEY", "")
EV_THRESHOLD = float(_get("EV_THRESHOLD", 0.04))
BANKROLL = float(_get("BANKROLL", 1000))
KELLY_FRACTION = float(_get("KELLY_FRACTION", 0.25))

# The Odds API sport key for AFL
ODDS_API_SPORT_KEY = "aussierules_afl"
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"

# Only fetch odds from these bookmakers (their real API bookmaker keys, not
# display names - confirmed from live API responses). Using the "bookmakers"
# param instead of "regions" also cuts API credit usage since you're not
# paying for data from books you don't want anyway.
BOOKMAKER_FILTER = ["ladbrokes_au", "neds", "pointsbetau"]

# Recency weighting: how many recent games to weight most heavily
RECENT_GAMES_WINDOW = 6
DECAY_RATE = 0.85  # each game further back is weighted by this factor

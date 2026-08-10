"""
Fetches AFL player prop odds from The Odds API (https://the-odds-api.com/).

Note: player-props markets (player_disposals, player_goals, etc.) may only be
available on paid plans / for certain bookmakers depending on your account tier.
Check the markets available to your key at:
https://the-odds-api.com/liveapi/guides/v4/#historical-odds
"""
import requests
import pandas as pd
from config import ODDS_API_KEY, ODDS_API_BASE_URL, ODDS_API_SPORT_KEY

# Common AFL player prop markets - adjust based on what your plan/bookmakers support
PLAYER_PROP_MARKETS = [
    "player_disposals",
    "player_goals",
    "player_marks",
    "player_tackles",
]

REGION = "au"  # Australian bookmakers


def get_upcoming_events():
    """Get list of upcoming AFL matches with event IDs (needed to fetch props)."""
    url = f"{ODDS_API_BASE_URL}/sports/{ODDS_API_SPORT_KEY}/events"
    resp = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_player_props_for_event(event_id: str) -> pd.DataFrame:
    """
    Fetch player prop odds for a single event.
    Returns a tidy DataFrame: player, market, line, side (over/under), price, bookmaker.
    """
    url = f"{ODDS_API_BASE_URL}/sports/{ODDS_API_SPORT_KEY}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGION,
        "markets": ",".join(PLAYER_PROP_MARKETS),
        "oddsFormat": "decimal",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for bookmaker in data.get("bookmakers", []):
        book_name = bookmaker["title"]
        for market in bookmaker.get("markets", []):
            market_key = market["key"]
            for outcome in market.get("outcomes", []):
                rows.append({
                    "event_id": event_id,
                    "home_team": data.get("home_team"),
                    "away_team": data.get("away_team"),
                    "commence_time": data.get("commence_time"),
                    "bookmaker": book_name,
                    "market": market_key,
                    "player": outcome.get("description"),  # player name
                    "side": outcome.get("name"),            # "Over" / "Under"
                    "line": outcome.get("point"),
                    "price": outcome.get("price"),           # decimal odds
                })
    return pd.DataFrame(rows)


def get_all_player_props() -> pd.DataFrame:
    """Fetch player props across all upcoming AFL events. This can burn API
    credits quickly (one request per event) - be mindful of your plan's quota."""
    events = get_upcoming_events()
    all_props = []
    for event in events:
        try:
            df = get_player_props_for_event(event["id"])
            if not df.empty:
                all_props.append(df)
        except requests.HTTPError as e:
            print(f"Skipping event {event.get('id')}: {e}")
    if not all_props:
        return pd.DataFrame()
    return pd.concat(all_props, ignore_index=True)

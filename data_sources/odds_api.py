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

# AFL player prop markets from The Odds API (api.the-odds-api.com - note the
# hyphenated domain; there's a separate, differently-priced product at the
# non-hyphenated theoddsapi.com that this code does NOT use).
#
# All three below are confirmed directly from the official docs example at
# https://the-odds-api.com/sports/afl-odds.html#query-any-afl-market:
#   - player_disposals: standard Over/Under line market (has both sides)
#   - player_goal_scorer_anytime: binary "Yes" market, no Under to pair against
#   - player_goals_scored_over: the docs' own example shows ONLY "Over"
#     outcomes for this key (e.g. "Over 3.5 goals" at various lines per
#     player) - the "_over" suffix in the key name itself suggests there's
#     no matching Under, i.e. these are alternate goal lines rather than a
#     single Over/Under pair. Handled as Over-only (no devig pairing
#     possible) in pipeline.py, same conservative treatment as the anytime
#     market. If your account's actual response DOES include Under outcomes
#     for this key, the pipeline will automatically pick them up and devig
#     properly - it doesn't assume either way, it just handles whatever
#     comes back.
LINE_PROP_MARKETS = ["player_disposals", "player_goals_scored_over"]
ANYTIME_PROP_MARKETS = ["player_goal_scorer_anytime"]

REGION = "au"  # Australian bookmakers


def get_upcoming_events():
    """Get list of upcoming AFL matches with event IDs (needed to fetch props)."""
    url = f"{ODDS_API_BASE_URL}/sports/{ODDS_API_SPORT_KEY}/events"
    resp = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_player_props_for_event(event_id: str) -> pd.DataFrame:
    """
    Fetch player prop odds for a single event - both the line-based market
    (player_disposals, has Over/Under) and the anytime binary market
    (player_goal_scorer_anytime, single "Yes" price per player).
    Returns a tidy DataFrame: player, market, line, side, price, bookmaker.
    """
    all_markets = LINE_PROP_MARKETS + ANYTIME_PROP_MARKETS
    url = f"{ODDS_API_BASE_URL}/sports/{ODDS_API_SPORT_KEY}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGION,
        "markets": ",".join(all_markets),
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
                    "side": outcome.get("name"),            # "Over"/"Under" or "Yes"
                    "line": outcome.get("point"),           # None for anytime market
                    "price": outcome.get("price"),
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


def get_all_player_props_verbose():
    """
    Same as get_all_player_props(), but returns (DataFrame, list_of_errors)
    instead of silently printing failures - used by the Diagnostics panel so
    errors show up in the browser instead of only in server logs.
    """
    errors = []
    try:
        events = get_upcoming_events()
    except requests.HTTPError as e:
        errors.append(f"get_upcoming_events failed: {e} - response body: {getattr(e.response, 'text', '')[:300]}")
        return pd.DataFrame(), errors
    except Exception as e:
        errors.append(f"get_upcoming_events failed (non-HTTP error): {e}")
        return pd.DataFrame(), errors

    if not events:
        errors.append("get_upcoming_events returned an empty list - no events, even though this should exist per your manual test. Possible cause: sport key or API key mismatch between what the app is using and what you tested manually.")
        return pd.DataFrame(), errors

    all_props = []
    for event in events:
        try:
            df = get_player_props_for_event(event["id"])
            if not df.empty:
                all_props.append(df)
            else:
                errors.append(f"Event {event.get('id')} ({event.get('home_team')} v {event.get('away_team')}): returned 0 rows (no bookmakers/markets in response for this event yet)")
        except requests.HTTPError as e:
            body = getattr(e.response, 'text', '')[:300]
            errors.append(f"Event {event.get('id')}: HTTP error - {e} - response body: {body}")
        except Exception as e:
            errors.append(f"Event {event.get('id')}: unexpected error - {e}")

    if not all_props:
        return pd.DataFrame(), errors
    return pd.concat(all_props, ignore_index=True), errors

"""
Fetches historical AFL player game stats from AFL Tables (https://afltables.com).

Rewritten against the ACTUAL live page structure (fetched and inspected
directly), fixing several bugs the original version had from guessing:

1. URL: the correct path is /afl/stats/teams/<slug>/<year>_gbg.html
   (the original version was missing "/stats/" and 404'd every request).
2. Player names on this page are "Lastname, Firstname" (e.g. "Dawson, Jordan").
   The Odds API gives player names as "Firstname Lastname" (e.g. "Jordan
   Dawson"). This module converts to the odds API's format so names actually
   match up in the pipeline.
3. Table order on the page follows the site's own "Display" selector order:
   Disposals, Kicks, Marks, Handballs, Goals, Behinds, Hit Outs, Tackles,
   Rebound 50s, Inside 50s, Clearances, Clangers, Frees For, Frees Against,
   Contested Poss, Uncontested Poss, Contested Marks, Marks Inside 50,
   One Percenters, Bounces, Goal Assist, %Played. This module hardcodes the
   indices for the stats we actually use rather than assuming an offset.
4. Each stat table's last column is "Tot" (season total) - this is NOT
   another round and is explicitly excluded before reshaping to long format,
   otherwise the recency-weighted average would treat a player's season
   total as if it were a single game's stats.

Still worth verifying if something changes: AFL Tables' page structure has
been stable for years but isn't guaranteed. If scraping breaks again, the
verbose function at the bottom (scrape_all_teams_verbose) surfaces exactly
which team/table failed instead of failing silently.
"""
import time
import re
import pandas as pd
import requests
from pathlib import Path
from io import StringIO

CACHE_PATH = Path(__file__).parent.parent / "data" / "player_stats.csv"
CACHE_PATH.parent.mkdir(exist_ok=True)

# AFL Tables' team slugs (used in URLs like /afl/stats/teams/<slug>/2026_gbg.html)
TEAM_SLUGS = {
    "Adelaide": "adelaide", "Brisbane Lions": "brisbanel", "Carlton": "carlton",
    "Collingwood": "collingwood", "Essendon": "essendon", "Fremantle": "fremantle",
    "Geelong": "geelong", "Gold Coast": "goldcoast", "GWS": "gws",
    "Hawthorn": "hawthorn", "Melbourne": "melbourne", "North Melbourne": "kangaroos",
    "Port Adelaide": "padelaide", "Richmond": "richmond", "St Kilda": "stkilda",
    "Sydney": "swans", "West Coast": "westcoast", "Western Bulldogs": "bullldogs",
}

# Confirmed table order on the live gbg page (0-indexed), matching the site's
# own "Display: DI KI MK HB GL BH HO TK ..." selector list.
STAT_TABLE_INDEX = {
    "disposals": 0,
    "kicks": 1,
    "marks": 2,
    "handballs": 3,
    "goals": 4,
    "behinds": 5,
    "hitouts": 6,
    "tackles": 7,
}
# The stats this bot actually models - trim/extend as needed
STATS_TO_EXTRACT = ["disposals", "goals", "marks", "tackles"]

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _normalize_player_name(raw_name: str) -> str:
    """Convert AFL Tables' 'Lastname, Firstname' to 'Firstname Lastname' so
    names match the format the Odds API uses."""
    raw_name = raw_name.strip()
    if "," in raw_name:
        last, first = raw_name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return raw_name  # already in expected format, or unparseable - leave as-is


def _fetch_team_gbg_tables(team_slug: str, year: int):
    url = f"https://afltables.com/afl/stats/teams/{team_slug}/{year}_gbg.html"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def _reshape_stat_table(table: pd.DataFrame, stat_name: str, team: str) -> pd.DataFrame:
    """
    Reshape one wide stat table (player rows x round columns) into long
    format: player, round, <stat_name>. Excludes the 'Tot' column and
    non-player summary rows (Totals, Opponent).
    """
    df = table.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[-1] for c in df.columns]

    df = df.rename(columns={df.columns[0]: "player"})
    df = df[df["player"].notna()]
    df = df[df["player"].astype(str).str.strip() != ""]
    # Drop the season-total and team-summary rows, not individual players
    df = df[~df["player"].astype(str).str.contains("Totals|Opponent", case=False, na=False)]

    df["player"] = df["player"].astype(str).apply(_normalize_player_name)

    # Round columns are everything except player and the season-total "Tot" column
    value_cols = [c for c in df.columns if c not in ("player", "Tot")]
    long_df = df.melt(id_vars="player", value_vars=value_cols,
                       var_name="round", value_name=stat_name)
    long_df["team"] = team

    # AFL Tables uses "-" for a recorded-zero stat in a game the player played -
    # treat as 0, not missing, so it doesn't get silently dropped.
    long_df[stat_name] = long_df[stat_name].replace("-", 0)
    long_df[stat_name] = pd.to_numeric(long_df[stat_name], errors="coerce")

    # A genuinely blank cell means the player didn't play that round - drop those
    return long_df.dropna(subset=[stat_name])


def fetch_season_player_stats(year: int) -> pd.DataFrame:
    """Scrape and combine per-game player stats for every team for a season."""
    all_frames = []
    for team_name, slug in TEAM_SLUGS.items():
        try:
            tables = _fetch_team_gbg_tables(slug, year)
        except Exception as e:
            print(f"Could not fetch {team_name} ({year}): {e}")
            continue

        team_stats = {}
        for stat_name in STATS_TO_EXTRACT:
            idx = STAT_TABLE_INDEX[stat_name]
            if idx >= len(tables):
                print(f"{team_name}: expected table index {idx} for {stat_name}, "
                      f"but only {len(tables)} tables found on page - skipping")
                continue
            try:
                team_stats[stat_name] = _reshape_stat_table(tables[idx], stat_name, team_name)
            except Exception as e:
                print(f"Could not parse {stat_name} table for {team_name}: {e}")

        if team_stats:
            merged = None
            for stat_name, frame in team_stats.items():
                if merged is None:
                    merged = frame
                else:
                    merged = merged.merge(
                        frame[["player", "round", stat_name]],
                        on=["player", "round"], how="outer"
                    )
            if merged is not None:
                all_frames.append(merged)

        time.sleep(1)  # be polite to afltables.com's servers

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)
    for col in STATS_TO_EXTRACT:
        if col not in combined.columns:
            combined[col] = None
    combined["minutes"] = None
    combined["opponent"] = None
    combined["venue"] = None
    combined["date"] = None
    return combined


def load_player_stats(year: int = None, force_refresh: bool = False) -> pd.DataFrame:
    import datetime
    year = year or datetime.date.today().year

    if CACHE_PATH.exists() and not force_refresh:
        return pd.read_csv(CACHE_PATH)

    df = fetch_season_player_stats(year)
    if not df.empty:
        df.to_csv(CACHE_PATH, index=False)
    return df


def get_player_recent_games(df: pd.DataFrame, player: str, n: int = 10) -> pd.DataFrame:
    """Return a player's most recent n games (by round number, descending)."""
    player_df = df[df["player"].str.lower() == player.lower()]
    if "round" in player_df.columns:
        # Round labels are like "R2", "R14" - sort numerically, not alphabetically
        player_df = player_df.copy()
        player_df["_round_num"] = player_df["round"].astype(str).str.extract(r"(\d+)").astype(float)
        player_df = player_df.sort_values("_round_num", ascending=False)
    return player_df.head(n)


def scrape_all_teams_verbose(year: int = None):
    """
    Same as fetch_season_player_stats(), but returns (DataFrame, list_of_errors)
    for the Diagnostics panel, instead of only printing failures to server logs.
    """
    import datetime
    year = year or datetime.date.today().year
    errors = []
    all_frames = []

    for team_name, slug in TEAM_SLUGS.items():
        try:
            tables = _fetch_team_gbg_tables(slug, year)
        except Exception as e:
            errors.append(f"{team_name}: failed to fetch page - {e}")
            continue

        if len(tables) < max(STAT_TABLE_INDEX.values()) + 1:
            errors.append(f"{team_name}: page returned only {len(tables)} tables, "
                           f"expected at least {max(STAT_TABLE_INDEX.values()) + 1}")

        team_stats = {}
        for stat_name in STATS_TO_EXTRACT:
            idx = STAT_TABLE_INDEX[stat_name]
            if idx >= len(tables):
                continue
            try:
                reshaped = _reshape_stat_table(tables[idx], stat_name, team_name)
                team_stats[stat_name] = reshaped
                if reshaped.empty:
                    errors.append(f"{team_name}/{stat_name}: table found but reshaped to 0 rows")
            except Exception as e:
                errors.append(f"{team_name}/{stat_name}: reshape failed - {e}")

        if team_stats:
            merged = None
            for stat_name, frame in team_stats.items():
                if merged is None:
                    merged = frame
                else:
                    merged = merged.merge(frame[["player", "round", stat_name]],
                                           on=["player", "round"], how="outer")
            if merged is not None:
                all_frames.append(merged)
        time.sleep(1)

    if not all_frames:
        return pd.DataFrame(), errors

    combined = pd.concat(all_frames, ignore_index=True)
    for col in STATS_TO_EXTRACT:
        if col not in combined.columns:
            combined[col] = None
    return combined, errors

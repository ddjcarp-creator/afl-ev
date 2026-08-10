"""
Automatically fetches historical AFL player game stats from AFL Tables
(https://afltables.com), no manual CSV export required.

AFL Tables publishes a "game-by-game" (gbg) stats page per team per season,
e.g. https://afltables.com/afl/teams/adelaide/2026_gbg.html - these contain
one HTML table per statistical category (Kicks, Marks, Disposals, Goals,
Tackles, etc.), with players as rows and rounds as columns.

This module scrapes those pages with pandas.read_html(), reshapes them into
a tidy long-format DataFrame, and caches the result to data/player_stats.csv
so you're not re-scraping on every run.

NOTE: AFL Tables' page structure has been stable for years, but it can change.
If this stops working, the first thing to check is whether the table order/
headers still match what's assumed in STAT_TABLES below - open the relevant
_gbg.html page in a browser and compare against fetch_season_player_stats().
This module was written without the ability to test live network calls, so
treat it as a strong starting template rather than guaranteed-working code.
"""
import time
import pandas as pd
import requests
from pathlib import Path
from io import StringIO

CACHE_PATH = Path(__file__).parent.parent / "data" / "player_stats.csv"
CACHE_PATH.parent.mkdir(exist_ok=True)

# AFL Tables' team slugs (used in URLs like /afl/teams/<slug>/2026_gbg.html)
TEAM_SLUGS = {
    "Adelaide": "adelaide", "Brisbane Lions": "brisbanel", "Carlton": "carlton",
    "Collingwood": "collingwood", "Essendon": "essendon", "Fremantle": "fremantle",
    "Geelong": "geelong", "Gold Coast": "goldcoast", "GWS": "gws",
    "Hawthorn": "hawthorn", "Melbourne": "melbourne", "North Melbourne": "kangaroos",
    "Port Adelaide": "padelaide", "Richmond": "richmond", "St Kilda": "stkilda",
    "Sydney": "swans", "West Coast": "westcoast", "Western Bulldogs": "bullldogs",
}

# Stat categories we care about, in the order they typically appear on the
# gbg page (after an initial "Games" summary table)
STAT_TABLES = {
    "disposals": "Disposals",
    "goals": "Goals",
    "marks": "Marks",
    "tackles": "Tackles",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_team_gbg_tables(team_slug: str, year: int):
    """Fetch all HTML tables from a team's game-by-game stats page for a season."""
    url = f"https://afltables.com/afl/teams/{team_slug}/{year}_gbg.html"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    return tables


def _reshape_stat_table(table: pd.DataFrame, stat_name: str, team: str) -> pd.DataFrame:
    """
    AFL Tables gbg tables are wide: one row per player, one column per round.
    Reshape to long format: player, round, <stat_name>.
    """
    df = table.copy()
    df = df.rename(columns={df.columns[0]: "player"})
    df = df[df["player"].notna()]
    df = df[~df["player"].astype(str).str.contains("Opponent|Total|Average", na=False)]

    value_cols = [c for c in df.columns if c != "player"]
    long_df = df.melt(id_vars="player", value_vars=value_cols,
                       var_name="round", value_name=stat_name)
    long_df["team"] = team
    long_df[stat_name] = pd.to_numeric(long_df[stat_name], errors="coerce")
    return long_df.dropna(subset=[stat_name])


def fetch_season_player_stats(year: int) -> pd.DataFrame:
    """
    Scrape and combine per-game player stats for every team for a given season.
    Returns a tidy DataFrame: player, team, round, disposals, goals, marks, tackles.

    Opponent/venue/date aren't reliably exposed on gbg pages, so those columns
    are left blank here - fine for the recency-weighted model, which mainly
    needs the stat values themselves plus round order.
    """
    all_frames = []
    for team_name, slug in TEAM_SLUGS.items():
        try:
            tables = _fetch_team_gbg_tables(slug, year)
        except Exception as e:
            print(f"Could not fetch {team_name} ({year}): {e}")
            continue

        team_stats = {}
        stat_keys = list(STAT_TABLES.keys())
        for i, stat_name in enumerate(stat_keys):
            table_index = i + 1  # table 0 is usually a games/results summary
            if table_index < len(tables):
                try:
                    reshaped = _reshape_stat_table(tables[table_index], stat_name, team_name)
                    team_stats[stat_name] = reshaped
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
    for col in ["disposals", "goals", "marks", "tackles"]:
        if col not in combined.columns:
            combined[col] = None
    combined["minutes"] = None  # gbg pages don't include time-on-ground
    combined["opponent"] = None
    combined["venue"] = None
    combined["date"] = None
    return combined


def load_player_stats(year: int = None, force_refresh: bool = False) -> pd.DataFrame:
    """
    Main entry point. Loads cached stats if available, otherwise scrapes fresh
    data from AFL Tables and caches it to data/player_stats.csv.
    """
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
        player_df = player_df.sort_values("round", ascending=False)
    return player_df.head(n)

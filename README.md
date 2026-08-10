# AFL Prop EV Bot

A Streamlit dashboard that flags positive expected-value (+EV) AFL player prop bets
by comparing a statistical model's estimated probabilities against devigged
bookmaker odds.

## How it works

1. **Odds** are pulled from [The Odds API](https://the-odds-api.com/) for AFL player props.
2. **Player stats** (recent disposal/goal/mark counts etc.) are loaded from a CSV you provide
   (there's no free official AFL stats API — see `data_sources/stats_data.py` for a scraper stub).
3. A **Poisson-based model** estimates the probability of a player going over/under a given line.
4. Bookmaker odds are **devigged** (margin removed) to get a fair implied probability.
5. **EV** is calculated for each prop; anything above your threshold gets flagged in the dashboard.

## Setup

```bash
git clone <your-repo-url>
cd afl-ev-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your ODDS_API_KEY
streamlit run app.py
```

## Getting an odds API key

1. Sign up at https://the-odds-api.com/ (free tier gives 500 requests/month, enough to test).
2. Copy your key into `.env` as `ODDS_API_KEY=...`.
3. Confirm AFL ("Australian Football") is listed under available sports for your plan —
   player props specifically may require a paid tier depending on the bookmaker.

## Getting player stats data

The model needs recent per-player stats (disposals, goals, marks, minutes) to build
its probability estimates. Options, roughly in order of effort:

- **Manual CSV export**: pull season stats from footywire.com or afltables.com and
  save as `data/player_stats.csv` (see `data_sources/stats_data.py` for the expected columns).
- **Scraper stub**: `data_sources/stats_data.py` includes a `scrape_footywire()` function
  as a starting point. Site HTML structures change often, so treat it as a template,
  not a guarantee — inspect the page and adjust selectors before relying on it.
- **Paid data**: Champion Data or Api Sports offer more robust AFL feeds if you want
  to scale this up.

## Project structure

```
afl-ev-bot/
├── app.py                      # Streamlit dashboard (entry point)
├── config.py                   # env var / settings loader
├── data_sources/
│   ├── odds_api.py             # fetches player prop odds
│   └── stats_data.py           # loads/scrapes historical player stats
├── model/
│   ├── prob_model.py           # Poisson probability model
│   ├── devig.py                # removes bookmaker margin from odds
│   └── ev.py                   # expected value + Kelly stake sizing
├── data/
│   └── player_stats.csv        # you provide this (see above)
└── requirements.txt
```

## Important notes

- **This is a starting framework, not a finished profitable system.** The probability
  model is intentionally simple (Poisson on recent form + opponent adjustment). Its
  output is only as good as the model and data you feed it — validate with backtesting
  before staking real money.
- **Check bookmaker terms of service** before scraping odds directly instead of using
  an API — many prohibit automated access.
- **Gambling carries financial risk.** Nothing here is financial advice, and past model
  performance (backtested or otherwise) doesn't guarantee future results.
- No part of this automatically places bets — it only surfaces information. Staking
  decisions are yours.

## Step-by-step: get this onto GitHub

1. **Create a GitHub account** if you don't have one: https://github.com/join
2. **Create a new repository**: on github.com, click the `+` in the top right → "New repository". Name it something like `afl-ev-bot`, keep it Private if you don't want the world seeing it, don't initialize with a README (you already have one). Click "Create repository".
3. **Install Git** if you don't have it: https://git-scm.com/downloads
4. **Push this folder to GitHub** — open a terminal in the `afl-ev-bot` folder and run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - AFL prop EV bot"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/afl-ev-bot.git
   git push -u origin main
   ```
   (Replace `YOUR_USERNAME` with your actual GitHub username — GitHub shows you this exact URL on the empty repo page after step 2.)
5. **Double check `.env` did NOT get pushed** — it's listed in `.gitignore` so it shouldn't, but confirm by checking your repo on github.com. Your API key should never appear there.

## Step-by-step: deploy to Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with your GitHub account.
2. Click **"Create app"** → **"From existing repo"**.
3. Select your `afl-ev-bot` repository, branch `main`, and set the main file path to `app.py`.
4. Before clicking Deploy, click **"Advanced settings"** → **Secrets**, and paste:
   ```toml
   ODDS_API_KEY = "your_actual_key_here"
   EV_THRESHOLD = 0.04
   BANKROLL = 1000
   KELLY_FRACTION = 0.25
   ```
5. Click **Deploy**. First deploy takes a couple of minutes while it installs `requirements.txt`.
6. Once live, click **"Fetch odds & run model"** in the app sidebar. The very first run will scrape AFL Tables for player stats (can take 1-2 minutes across all teams) and cache the result — subsequent runs reuse the cache unless you tick "Force refresh."
7. Your app gets a public URL like `https://your-app-name.streamlit.app` — bookmark it.

### If something breaks on first run
- **"No ODDS_API_KEY found"** → you missed step 4 above, or typo'd the secret name. Go to your app on share.streamlit.io → Settings → Secrets and check.
- **Stats scraping fails / empty results** → AFL Tables' page structure may not match what `stats_data.py` expects (see the note at the top of that file). Open `https://afltables.com/afl/teams/adelaide/2026_gbg.html` in a browser, compare its table structure to the assumptions in `_reshape_stat_table()`, and adjust.
- **No player props returned from odds API** → player props may not be available on your Odds API plan/region, or there are simply no AFL matches in the next few days. Check what markets your key supports in your Odds API dashboard.

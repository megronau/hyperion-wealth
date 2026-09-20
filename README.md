# Hyperion Wealth System

Paper-trading engine that scans for +EV, arbitrage, and free-bet conversions, sizes bets with fractional Kelly, and records P&L after a **2% fee on winning profit**.

It does **not** send real money to sportsbooks. Paper mode simulates unique games. Live mode can read real odds if `ODDS_API_KEY` is set, but Kalshi execution is still simulated.

## Live URLs

| What | URL |
|------|-----|
| Dashboard | https://hyperion-wealth.vercel.app |
| API | https://hyperion-api-klr5.onrender.com |
| Health | https://hyperion-api-klr5.onrender.com/api/health |
| GitHub | https://github.com/megronau/hyperion-wealth |

The first request after Render sleeps can take ~30 seconds.

## How to run locally

Use three terminals from the repo root. Python 3.11+ and Node.js 20+ are required.

**1. API**

```powershell
py -3 -m pip install -r requirements.txt
py -3 src/api.py
```

API: http://127.0.0.1:5000  
Health: http://127.0.0.1:5000/api/health

**2. Dashboard**

```powershell
cd dashboard
npm install
npm run dev
```

UI: http://localhost:5173/

**3. Daemon (paper loop)**

```powershell
py -3 src/daemon.py
```

Without `ODDS_API_KEY` this stays in **paper** mode: unique +EV games, 2% win fee, bankroll in `trading_brain.db`.

**Reset the local book to $100**

```powershell
$env:STARTING_BANKROLL = "100"
$env:PAPER_GAMES_PER_CYCLE = "20"
py -3 scripts/reset_paper_book.py
```

That wipes trades, sets bankroll to $100, then runs a seed walk-forward.

**Tests**

```powershell
py -3 -m unittest discover -s src -v
```

## Paper vs live

| | Paper (default) | Live |
|---|---|---|
| Data | Simulated unique markets | The Odds API |
| Settlement | Win with modeled probability | Real scores when available |
| Win P&L | `(odds − 1) × stake × 0.98` | Same formula |
| Loss P&L | `−stake` | `−stake` |
| Money | Simulated | **Not sent.** Kalshi signing and tickers are not production-ready. |

`TRADING_MODE=live` without `ODDS_API_KEY` is forced back to paper.

## Fees

`FEE_PERCENTAGE` defaults to **0.02**.

- Wins: 2% of **profit** (not of stake)
- Losses: no fee
- Kelly and the +EV filter use after-fee odds so the model does not pretend the gross price is keepable

Not in P&L: Odds API subscription, Render/Vercel hosting, deposits, withdrawals.

## Environment variables

Copy [`.env.example`](.env.example). Important keys:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `FEE_PERCENTAGE` | `0.02` | Win commission |
| `DATABASE_URL` | unset (SQLite `trading_brain.db`) | Postgres on Render |
| `ODDS_API_KEY` | unset (mock odds) | Real odds |
| `API_URL` | `http://127.0.0.1:5000` | Daemon → API broadcasts |
| `PAPER_GAMES_PER_CYCLE` | `120` locally / `20` on the $100 cloud trial | Paper batch size |
| `SCAN_INTERVAL_SECONDS` | `300` | Seconds between cycles |
| `EMBED_DAEMON` | `false` locally / `true` on Render web | Run daemon inside the API process |
| `STARTING_BANKROLL` | `1000` | Used by `scripts/reset_paper_book.py` |
| `VITE_BACKEND_URL` | (dashboard) | Public API URL for Vercel builds |

## Project layout

```
src/api.py            Flask API + optional embedded daemon
src/daemon.py         Scan / paper walk-forward / settle / learn
src/paper_engine.py   Unique +EV paper games
src/fees.py           2% win fee
src/ev_scanner.py     +EV vs sharp books
src/scanner.py        Arbitrage
src/matched_betting.py
src/settlement.py     Paper Bernoulli + live scores
src/database.py       SQLite or Postgres
dashboard/            React UI
render.yaml           Render API + optional worker + Postgres
scripts/reset_paper_book.py
```

## Cloud

**Dashboard** is on Vercel (`dashboard/`). **API + paper loop** are on Render (`render.yaml`). Vercel cannot run the Python daemon.

### Render (already created)

- Web: `hyperion-api` (free). `EMBED_DAEMON=true` so the loop runs on the web service.
- Postgres: `hyperion-db` (free; expires ~30 days unless upgraded).
- A separate **worker** needs a credit card. Without it, keep `EMBED_DAEMON=true`.

Free web services sleep when idle. Ping `/api/health` or upgrade if you need the loop always on.

### Point Vercel at the API

```powershell
cd dashboard
echo "https://hyperion-api-klr5.onrender.com" | vercel env add VITE_BACKEND_URL production
vercel deploy --prod
```

### New Render deploy from this repo

1. Connect GitHub repo `megronau/hyperion-wealth` to Render.
2. Apply `render.yaml` (or recreate web + Postgres).
3. Set `DATABASE_URL` from the database, `TRADING_MODE=paper`, `FEE_PERCENTAGE=0.02`, `EMBED_DAEMON=true`.
4. After the API URL exists, set `VITE_BACKEND_URL` on Vercel and redeploy.

### Reset the cloud $100 paper trial

The live trial was reset to **$100** bankroll, paper mode, 20 games per cycle. To reset again, run `scripts/reset_cloud_book.py` with `RENDER_API_KEY` (do not commit that key), or SQL against Postgres:

```sql
DELETE FROM trades;
UPDATE system_params
SET bankroll = 100, kelly_fraction = 0.25, min_ev_threshold = 0.02
WHERE id = 1;
```

## What is not finished

- Kalshi live orders (paper fills, mock signatures, fake tickers)
- Direct FanDuel / DraftKings betting
- Odds API, hosting, and cash-out fees in P&L
- Always-on worker without Render billing

## API cheatsheet

| Method | Path | Use |
|--------|------|-----|
| GET | `/api/health` | Liveness |
| GET | `/api/system_status` | Mode, bankroll, P&L, fee, Kelly |
| GET | `/api/history` | Closed trades |
| GET | `/api/opportunities/ev` | +EV list (`?refresh=1` to rescan) |
| GET | `/api/opportunities/arbitrage` | Arb list |
| GET | `/api/opportunities/matched_betting` | Free-bet conversions |

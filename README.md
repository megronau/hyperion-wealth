# Hyperion Wealth System

Scans US sports moneylines for +EV, arbitrage, and free-bet conversions. Sizes bets with fractional Kelly. Records P&L after a **2% fee on winning profit**.

**Production default is `live_paper`:** real odds from [The Odds API](https://the-odds-api.com), **paper fills** (no cash sent to a book), settlement from **real scores**.

It does **not** place sportsbook or Kalshi orders. The invented-game simulator (`TRADING_MODE=sim`) is opt-in only and is **off** in production.

## Live URLs

| What | URL |
|------|-----|
| Dashboard | https://hyperion-wealth.vercel.app |
| API | https://hyperion-web-dbbz.onrender.com |
| Health | https://hyperion-web-dbbz.onrender.com/api/health |
| GitHub | https://github.com/megronau/hyperion-wealth |

## How a live-paper cycle works

Every **15 minutes** the Render worker:

1. Settles any open **live_paper** tickets whose games have real scores (win profit × 0.98).
2. Pulls **upcoming** US h2h odds (DraftKings/Pinnacle as sharp, FanDuel and others as soft).
3. Logs at most **10** unique +EV paper bets that pass the min-edge filter. **One ticket per event.** Draw is only allowed when **both** books list three outcomes. Soft odds above 12.0 or EV above 30% are treated as feed junk and skipped.
4. Broadcasts EV / arb / matched-betting lists to the dashboard.
5. Adjusts Kelly only from **realized** ROI, not from fake closing lines.

Expect a handful of paper tickets per day on a real slate, not hundreds. Hundreds of fills meant the old simulator.

## How to run locally

Python 3.11+ and Node.js 20+. Three terminals from the repo root.

**1. API**

```powershell
py -3 -m pip install -r requirements.txt
copy .env.example .env   # then set ODDS_API_KEY
py -3 src/api.py
```

- API: http://127.0.0.1:5000
- Health: http://127.0.0.1:5000/api/health

**2. Dashboard**

```powershell
cd dashboard
npm install
npm run dev
```

UI: http://localhost:5173/  
Vite proxies `/api` and `/socket.io` to port 5000. If the page is blank, hard-refresh (Ctrl+Shift+R). Do not use port 5000 as the UI.

**3. Daemon**

```powershell
$env:ODDS_API_KEY = "your-odds-api-key"
$env:TRADING_MODE = "live_paper"
py -3 src/daemon.py
```

Without `ODDS_API_KEY`, live_paper **skips** the cycle. It will not invent games.

**Simulator only (math test, not production)**

```powershell
$env:TRADING_MODE = "sim"
py -3 src/daemon.py
```

**Reset local SQLite bankroll** (does **not** invent games by itself; `reset_paper_book.py` then runs a sim batch — use only for simulator tests):

```powershell
$env:STARTING_BANKROLL = "100"
py -3 scripts/reset_paper_book.py
```

**Tests**

```powershell
py -3 -m unittest discover -s src -v
```

## Modes

| `TRADING_MODE` | Odds | Fills | Settlement |
|----------------|------|-------|------------|
| `live_paper` (production) | The Odds API | Paper log only | Real scores |
| `live` | Same as live_paper until Kalshi signing exists | Still no cash | Real scores |
| `sim` or `paper` | Invented markets | Simulated | Bernoulli at modeled p |

Missing `ODDS_API_KEY` + `live_paper` = **no trades**, not a silent fallback to `sim`.

## Fees

`FEE_PERCENTAGE` = **0.02**

- Win: `(odds − 1) × stake × 0.98`
- Loss: `−stake`
- Kelly and the +EV filter use after-fee odds

Not in P&L: Odds API bill, Render, Vercel, deposits, withdrawals.

## Environment variables

See [`.env.example`](.env.example). Do not commit secrets.

| Variable | Production | Purpose |
|----------|------------|---------|
| `TRADING_MODE` | `live_paper` | See modes above |
| `ODDS_API_KEY` | set on Render | Required for live_paper |
| `FEE_PERCENTAGE` | `0.02` | Win commission |
| `DATABASE_URL` | Render Postgres | Unset locally → `trading_brain.db` |
| `API_URL` | `https://hyperion-web-dbbz.onrender.com` | Worker → API broadcasts |
| `SCAN_INTERVAL_SECONDS` | `900` | 15 minutes between live-paper cycles |
| `MAX_BETS_PER_CYCLE` | `10` | Cap on new live-paper tickets per scan |
| `LIVE_SPORTS` | `upcoming` | Odds API sport key(s), comma-separated |
| `EMBED_DAEMON` | `false` | Do not run the loop inside the web service |
| `PAPER_GAMES_PER_CYCLE` | unused in live_paper | Sim batch size only |
| `STARTING_BANKROLL` | `100` | `scripts/reset_paper_book.py` only |
| `VITE_BACKEND_URL` | Render API URL | Vercel production build |
| `DISCORD_WEBHOOK_URL` | optional | Alerts |

Odds API quota: `upcoming` every 15 minutes is ~96 odds calls/day plus score fetches. Free 500/month is not enough; use a paid Odds API plan.

## Project layout

```
src/api.py              Flask API (status, history, scanners, sockets)
src/daemon.py           Worker: settle → scan → paper-log +EV
src/trading_mode.py     live_paper / live / sim
src/ev_scanner.py       +EV vs sharp books
src/scanner.py          Arbitrage
src/matched_betting.py  Free-bet conversion
src/settlement.py       Real scores (live_paper) or Bernoulli (sim)
src/fees.py             2% win fee + Kelly net odds
src/paper_engine.py     Invented games (sim only)
src/database.py         SQLite or Postgres
src/kalshi_client.py    Paper fills only
dashboard/              React UI (Vercel)
render.yaml             Starter web + Starter worker + Basic Postgres
scripts/reset_paper_book.py   Local sim reset (not for production)
```

## Cloud (~$20/month on Render)

| Service | Plan | Role |
|---------|------|------|
| `hyperion-web` | Starter (~$7) | Always-on API |
| `hyperion-daemon` | Starter (~$7) | live_paper loop |
| `hyperion-db` | Basic 256 MB (~$6) | Postgres |
| Vercel `hyperion-wealth` | Hobby | Dashboard |

The old free web service `hyperion-api` is **suspended**. `EMBED_DAEMON` is **false** so the worker owns the loop.

**Odds API key** must be set on **both** `hyperion-web` and `hyperion-daemon` (Render Dashboard → Environment). Never commit it.

**Point Vercel at the API** (already done for production):

```powershell
cd dashboard
echo "https://hyperion-web-dbbz.onrender.com" | vercel env add VITE_BACKEND_URL production
vercel deploy --prod
```

**Reset the cloud $100 live-paper book** (SQL on Postgres). This does not start the simulator:

```sql
DELETE FROM trades;
UPDATE system_params
SET bankroll = 100, kelly_fraction = 0.25, min_ev_threshold = 0.02
WHERE id = 1;
```

Do **not** run `scripts/reset_paper_book.py` against production; that seeds invented sim trades.

## What is not finished

- Real Kalshi or sportsbook order routing
- Spreads/totals (moneyline h2h only)
- Odds API, hosting, and cash-out fees in P&L
- Auto-rotating secrets that were pasted in chat

## API cheatsheet

| Method | Path | Use |
|--------|------|-----|
| GET | `/api/health` | Liveness |
| GET | `/api/system_status` | Mode, `odds_live`, bankroll, P&L, fee |
| GET | `/api/history` | Closed trades |
| GET | `/api/opportunities/ev?refresh=1` | Rescan +EV |
| GET | `/api/opportunities/arbitrage` | Arb |
| GET | `/api/opportunities/matched_betting` | Free-bet conversions |

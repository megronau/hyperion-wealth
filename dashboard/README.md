# Hyperion dashboard

React + Vite UI. It shows bankroll, live-paper P&L, and scanners from the Flask API.

Full system docs: [root README](../README.md).

## Local

Start the API first (`py -3 src/api.py` from the repo root), then:

```powershell
npm install
npm run dev
```

Open **http://localhost:5173/** (not port 5000).

Vite proxies `/api` and `/socket.io` to `http://127.0.0.1:5000`. Leave `VITE_BACKEND_URL` unset in development.

If the page is blank, hard-refresh (Ctrl+Shift+R). An older build crashed when status had not loaded yet; current `App.jsx` guards that.

## Production (Vercel)

- Site: https://hyperion-wealth.vercel.app
- API: https://hyperion-web-dbbz.onrender.com
- Mode shown: **LIVE PAPER** when `TRADING_MODE=live_paper` and `odds_live` is true

Build env:

```
VITE_BACKEND_URL=https://hyperion-web-dbbz.onrender.com
```

```powershell
cd dashboard
vercel env add VITE_BACKEND_URL production
vercel deploy --prod
```

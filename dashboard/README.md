# Hyperion dashboard

React + Vite UI for the Hyperion wealth system. It reads bankroll, P&L, and live scanners from the Flask API.

Full run instructions (API, daemon, cloud) are in the [root README](../README.md).

## Local

From this folder, with the API already running on port 5000:

```powershell
npm install
npm run dev
```

Open http://localhost:5173/

Vite proxies `/api` and `/socket.io` to `http://127.0.0.1:5000`. You do not need `VITE_BACKEND_URL` in development.

## Production (Vercel)

The production site is https://hyperion-wealth.vercel.app

Build-time env:

```
VITE_BACKEND_URL=https://hyperion-api-klr5.onrender.com
```

Redeploy after changing that variable:

```powershell
cd dashboard
vercel env add VITE_BACKEND_URL production
vercel deploy --prod
```

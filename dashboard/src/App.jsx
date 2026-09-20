import { useState, useEffect } from 'react'
import { io } from 'socket.io-client'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || (import.meta.env.DEV ? '' : '')
const socket = BACKEND_URL ? io(BACKEND_URL) : io()

async function fetchJson(path) {
  const res = await fetch(`${BACKEND_URL}${path}`)
  if (!res.ok) throw new Error(`${path} failed (${res.status})`)
  return res.json()
}

function money(n) {
  const v = Number(n || 0)
  return `${v < 0 ? '-' : ''}$${Math.abs(v).toFixed(2)}`
}

function outcomeLabel(trade) {
  if (trade.status === 'OPEN' || trade.outcome === 'PENDING') return 'Waiting on score'
  return trade.outcome
}

function App() {
  const [status, setStatus] = useState(null)
  const [openBets, setOpenBets] = useState([])
  const [opportunities, setOpportunities] = useState([])
  const [arbitrageOpps, setArbitrageOpps] = useState([])
  const [matchedBets, setMatchedBets] = useState([])
  const [history, setHistory] = useState([])
  const [realizedPnl, setRealizedPnl] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = async (refresh = false) => {
    setLoading(true)
    setError(null)
    const q = refresh ? '?refresh=1' : ''

    try {
      const [statusRes, historyRes, openRes, evRes, arbRes, mbRes] = await Promise.allSettled([
        fetchJson('/api/system_status'),
        fetchJson('/api/history'),
        fetchJson('/api/open_bets'),
        fetchJson(`/api/opportunities/ev${q}`),
        fetchJson(`/api/opportunities/arbitrage${q}`),
        fetchJson(`/api/opportunities/matched_betting${q}`),
      ])

      if (statusRes.status === 'fulfilled') {
        setStatus(statusRes.value)
        if (typeof statusRes.value.realized_pnl === 'number') {
          setRealizedPnl(statusRes.value.realized_pnl)
        }
      }

      if (openRes.status === 'fulfilled' && Array.isArray(openRes.value)) {
        setOpenBets(openRes.value)
      }

      if (historyRes.status === 'fulfilled' && Array.isArray(historyRes.value)) {
        const pending = historyRes.value.filter((t) => (t.outcome || 'PENDING') === 'PENDING')
        if (openRes.status !== 'fulfilled') setOpenBets(pending)

        const settled = historyRes.value.filter((t) =>
          ['WON', 'LOST', 'PUSH'].includes(t.outcome)
        )
        const chronological = [...settled].sort((a, b) =>
          String(a.timestamp || '').localeCompare(String(b.timestamp || ''))
        )
        let cumulativePnl = 0
        const chartData = chronological.map((trade, idx) => {
          cumulativePnl += trade.profit_loss || 0
          return { name: `${idx + 1}`, pnl: Number(cumulativePnl.toFixed(2)) }
        })
        setHistory(chartData)
        if (typeof statusRes.value?.realized_pnl !== 'number') {
          setRealizedPnl(cumulativePnl)
        }
      }

      if (evRes.status === 'fulfilled' && Array.isArray(evRes.value)) setOpportunities(evRes.value)
      if (arbRes.status === 'fulfilled' && Array.isArray(arbRes.value)) setArbitrageOpps(arbRes.value)
      if (mbRes.status === 'fulfilled' && Array.isArray(mbRes.value)) setMatchedBets(mbRes.value)

      const failed = [statusRes, historyRes, openRes].filter((r) => r.status === 'rejected')
      if (failed.length === 3) setError('Cannot reach the Hyperion API.')
    } catch (err) {
      console.error(err)
      setError('Cannot reach the Hyperion API.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData(false)
    const tick = setInterval(() => fetchData(false), 30000)
    socket.on('new_opportunities', (rows) => Array.isArray(rows) && setOpportunities(rows))
    socket.on('new_arbitrage', (rows) => Array.isArray(rows) && setArbitrageOpps(rows))
    socket.on('new_matched_bet', (rows) => Array.isArray(rows) && setMatchedBets(rows))
    return () => {
      clearInterval(tick)
      socket.off('new_opportunities')
      socket.off('new_arbitrage')
      socket.off('new_matched_bet')
    }
  }, [])

  const online = Boolean(status)
  const pnl = Number(status?.realized_pnl ?? realizedPnl)
  const mode = (status?.trading_mode || 'live_paper').replace('_', ' ')

  return (
    <div className="app-container">
      <header className="header">
        <div>
          <div className="kicker">Paper desk · real markets</div>
          <h1 className="header-title">Hyperion</h1>
        </div>
        <div className="header-actions">
          {status && <div className="status-badge">{mode}</div>}
          <div className={`status-badge ${online ? '' : 'offline'}`}>
            <div className="status-dot"></div>
            {error && !status ? 'Offline' : (status ? 'Online' : 'Connecting')}
          </div>
          <button className="refresh-btn" onClick={() => fetchData(true)} disabled={loading}>
            {loading ? 'Scanning' : 'Refresh'}
          </button>
        </div>
      </header>

      <p className="lede">
        {status?.trading_mode === 'sim'
          ? 'Simulator is inventing games. This is not a real slate.'
          : 'Live paper trading: real upcoming odds, paper fills, settlement from real scores. A 2% fee comes off winning profit. No sportsbook cash is sent.'}
        {status && !status.odds_live ? ' Odds API key is missing, so scans are blocked.' : ''}
      </p>

      {error && <div className="error-banner">{error}</div>}

      {status && (
        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-label">Bankroll</span>
            <span className="stat-value">{money(status.bankroll)}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Paper P&L</span>
            <span className={`stat-value ${pnl >= 0 ? 'up' : 'down'}`}>
              {pnl >= 0 ? '+' : ''}{money(pnl)}
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Working now</span>
            <span className="stat-value">{openBets.length}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Settled</span>
            <span className="stat-value">
              {status.total_trades}
              <span className="stat-sub">{((status.win_rate || 0) * 100).toFixed(0)}% wins</span>
            </span>
          </div>
        </div>
      )}

      <section className="panel hero-panel">
        <div className="panel-head">
          <div>
            <h2>Currently betting</h2>
            <p>Paper tickets waiting on a real final score. P&L does not move until then.</p>
          </div>
        </div>
        {openBets.length === 0 ? (
          <div className="empty">
            Nothing working right now. The worker scans every 15 minutes and only logs unique +EV sides.
          </div>
        ) : (
          <div className="ticket-list">
            {openBets.map((bet) => (
              <article key={bet.id} className="ticket">
                <div>
                  <div className="ticket-match">{bet.match_name}</div>
                  <div className="ticket-meta">
                    <span>Paper on <strong>{bet.bet_on}</strong> @ {Number(bet.placed_odds).toFixed(2)}</span>
                    {bet.sport_key && <span>{bet.sport_key}</span>}
                    <span>{bet.timestamp ? new Date(bet.timestamp).toLocaleString() : ''}</span>
                  </div>
                </div>
                <div className="ticket-side">
                  <span className="pill live">{outcomeLabel(bet)}</span>
                  <div style={{marginTop: 8}}>{money(bet.stake)}</div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {history.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Settled paper P&L</h2>
              <p>Only completed games. Open tickets are not in this line.</p>
            </div>
          </div>
          <div className="chart-wrap">
            <ResponsiveContainer>
              <LineChart data={history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2c3629" vertical={false} />
                <XAxis dataKey="name" stroke="#9aa392" />
                <YAxis stroke="#9aa392" />
                <Tooltip contentStyle={{ background: '#181e17', borderColor: '#3d4638', borderRadius: 8 }} />
                <Line type="monotone" dataKey="pnl" name="P&L" stroke="#d4b483" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>+EV watchlist</h2>
            <p>Edges the model likes. Not the same as tickets already placed.</p>
          </div>
        </div>
        {loading && opportunities.length === 0 ? (
          <div className="empty">Scanning live moneylines…</div>
        ) : opportunities.length === 0 ? (
          <div className="empty">No +EV sides above the min-edge filter right now.</div>
        ) : (
          <div className="opp-list">
            {opportunities.map((opp, idx) => (
              <div key={opp.event_id ? `${opp.event_id}-${opp.bet_on}` : idx} className="opp-card">
                <div>
                  <div className="opp-match">{opp.event}</div>
                  <div className="opp-details">
                    {opp.bet_on} @ {opp.soft_odds} · {opp.soft_book} · model {opp.true_probability}%
                  </div>
                </div>
                <div>
                  <div className="opp-ev">+{opp.ev_percentage}% EV</div>
                  <div className="opp-stake">Kelly {money(opp.kelly_stake)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Arbitrage watchlist</h2>
            <p>Alert only. Profit is locked only if every leg is filled at these odds. Hyperion does not place these.</p>
          </div>
        </div>
        {arbitrageOpps.length === 0 ? (
          <div className="empty">No cross-book arbs on the current slate.</div>
        ) : (
          <div className="opp-list">
            {arbitrageOpps.map((arb, idx) => (
              <div key={arb.event_id || idx} className="opp-card">
                <div>
                  <div className="opp-match">{arb.match}</div>
                  <div className="opp-details">
                    {(arb.legs || []).map((leg, i) => (
                      <div key={i}>{leg.outcome} @ {leg.odds} · {leg.bookmaker} · {money(leg.stake)}</div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="opp-ev">+{arb.roi_percentage}% ROI</div>
                  <div className="opp-stake">If filled {money(arb.guaranteed_profit)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Free-bet conversion</h2>
            <p>Alert only. Assumes a FanDuel free bet hedged on DraftKings. Not placed automatically.</p>
          </div>
        </div>
        {matchedBets.length === 0 ? (
          <div className="empty">No conversion setups above the 65% threshold.</div>
        ) : (
          <div className="opp-list">
            {matchedBets.map((mb, idx) => (
              <div key={idx} className="opp-card">
                <div>
                  <div className="opp-match">{mb.event}</div>
                  <div className="opp-details">
                    <div>{mb.free_bet}</div>
                    <div>{mb.hedge_bet}</div>
                  </div>
                </div>
                <div>
                  <div className="opp-ev">{Number(mb.conversion_rate || 0).toFixed(0)}% cash</div>
                  <div className="opp-stake">Hedge {money(mb.lay_stake_needed)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default App

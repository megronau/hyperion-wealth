import { useState, useEffect } from 'react'
import { io } from 'socket.io-client'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || (import.meta.env.DEV ? '' : '')
const socket = BACKEND_URL ? io(BACKEND_URL) : io()

async function fetchJson(path) {
  const res = await fetch(`${BACKEND_URL}${path}`)
  if (!res.ok) {
    throw new Error(`${path} failed (${res.status})`)
  }
  return res.json()
}

function App() {
  const [status, setStatus] = useState(null)
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
      const [statusRes, historyRes, evRes, arbRes, mbRes] = await Promise.allSettled([
        fetchJson('/api/system_status'),
        fetchJson('/api/history'),
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

      if (historyRes.status === 'fulfilled' && Array.isArray(historyRes.value)) {
        const chronological = [...historyRes.value].sort((a, b) =>
          String(a.timestamp || '').localeCompare(String(b.timestamp || ''))
        )
        let cumulativeClv = 0
        let cumulativePnl = 0
        const chartData = chronological.map((trade, idx) => {
          cumulativeClv += (trade.clv_percentage || 0) * 100
          if (trade.outcome === 'WON' || trade.outcome === 'LOST' || trade.outcome === 'PUSH') {
            cumulativePnl += trade.profit_loss || 0
          }
          return {
            name: `Trade ${idx + 1}`,
            clv: Number(cumulativeClv.toFixed(2)),
            pnl: Number(cumulativePnl.toFixed(2)),
            edge: Number(((trade.clv_percentage || 0) * 100).toFixed(2)),
          }
        })
        setHistory(chartData)
        setRealizedPnl(
          typeof statusRes.value?.realized_pnl === 'number'
            ? statusRes.value.realized_pnl
            : cumulativePnl
        )
      }

      if (evRes.status === 'fulfilled' && Array.isArray(evRes.value)) {
        setOpportunities(evRes.value)
      }
      if (arbRes.status === 'fulfilled' && Array.isArray(arbRes.value)) {
        setArbitrageOpps(arbRes.value)
      }
      if (mbRes.status === 'fulfilled' && Array.isArray(mbRes.value)) {
        setMatchedBets(mbRes.value)
      }

      const failed = [statusRes, historyRes, evRes, arbRes, mbRes].filter((r) => r.status === 'rejected')
      if (failed.length === 5) {
        setError('Cannot reach the wealth backend. Start the API on port 5000.')
      } else if (failed.length > 0) {
        setError('Some scanners failed. Showing whatever data loaded.')
      }
    } catch (err) {
      console.error('Failed to fetch data', err)
      setError('Cannot reach the wealth backend. Start the API on port 5000.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData(false)

    socket.on('new_opportunities', (newOpps) => {
      if (Array.isArray(newOpps)) {
        setOpportunities(newOpps)
      }
    })

    socket.on('new_arbitrage', (newArbs) => {
      if (Array.isArray(newArbs)) {
        setArbitrageOpps(newArbs)
      }
    })

    socket.on('new_matched_bet', (newMb) => {
      if (Array.isArray(newMb)) {
        setMatchedBets(newMb)
      }
    })

    return () => {
      socket.off('new_opportunities')
      socket.off('new_arbitrage')
      socket.off('new_matched_bet')
    }
  }, [])

  const online = Boolean(status)

  return (
    <div className="app-container">
      <header className="header">
        <h1 className="header-title text-gradient-green">HYPERION Wealth System</h1>
        <div style={{display: 'flex', gap: '10px', alignItems: 'center'}}>
          {status && (
            <div className={`status-badge ${status.trading_mode === 'live' ? '' : 'paper'}`}>
              {(status.trading_mode || 'paper').toUpperCase()} MODE
            </div>
          )}
          <div className={`status-badge ${online ? '' : 'offline'}`}>
            <div className="status-dot"></div>
            {error && !status ? 'OFFLINE' : (status ? status.status : 'CONNECTING...')}
          </div>
        </div>
      </header>

      {error && (
        <div className="error-banner">{error}</div>
      )}

      {status && (
        <div className="stats-grid">
          <div className="glass-panel stat-card">
            <span className="stat-label">Bankroll</span>
            <span className="stat-value">${Number(status.bankroll || 0).toFixed(2)}</span>
          </div>
          <div className="glass-panel stat-card">
            <span className="stat-label">{status.trading_mode === 'live' ? 'Realized P&L' : 'Paper P&L'}</span>
            <span className="stat-value" style={{color: realizedPnl >= 0 ? '#00ffcc' : '#ff4d4d'}}>
              {realizedPnl >= 0 ? '+' : ''}${Number(status.realized_pnl ?? realizedPnl).toFixed(2)}
            </span>
          </div>
          <div className="glass-panel stat-card">
            <span className="stat-label">Win Rate / ROI</span>
            <span className="stat-value">
              {((status.win_rate || 0) * 100).toFixed(1)}%
              <span style={{fontSize: '1rem', marginLeft: '8px', color: '#8b8b9e'}}>
                {((status.roi || 0) * 100).toFixed(2)}% ROI
              </span>
            </span>
          </div>
          <div className="glass-panel stat-card">
            <span className="stat-label">System Kelly Fraction</span>
            <span className="stat-value">{status.kelly_fraction}x</span>
          </div>
          <div className="glass-panel stat-card">
            <span className="stat-label">Min EV Threshold</span>
            <span className="stat-value">{(status.min_ev_threshold * 100).toFixed(2)}%</span>
          </div>
          <div className="glass-panel stat-card">
            <span className="stat-label">Settled Trades</span>
            <span className="stat-value">{status.total_trades}</span>
          </div>
        </div>
      )}
      {status?.trading_mode !== 'live' && (
        <p className="mode-note">
          Paper mode walks unique +EV games forward and settles each bet with its modeled probability.
          Winning profit is reduced by a {(Number(status.win_fee_percentage ?? 0.02) * 100).toFixed(0)}% exchange fee.
          This is not sportsbook cash. Live mode needs ODDS_API_KEY and real scores.
        </p>
      )}

      {history.length > 0 && (
          <div className="glass-panel chart-container" style={{marginTop: '20px', padding: '20px', borderRadius: '16px'}}>
              <h2 style={{marginTop: 0, color: '#fff', fontSize: '1.2rem'}}>Cumulative System Edge (CLV)</h2>
              <div style={{width: '100%', height: '300px', marginTop: '20px'}}>
                  <ResponsiveContainer>
                      <LineChart data={history}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                          <XAxis dataKey="name" stroke="#888" tick={{fill: '#888'}} />
                          <YAxis yAxisId="left" stroke="#888" tick={{fill: '#888'}} label={{ value: 'CLV (%)', angle: -90, position: 'insideLeft', fill: '#888' }} />
                          <YAxis yAxisId="right" orientation="right" stroke="#888" tick={{fill: '#888'}} label={{ value: 'P&L ($)', angle: 90, position: 'insideRight', fill: '#888' }} />
                          <Tooltip
                              contentStyle={{backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#333', borderRadius: '8px'}}
                              itemStyle={{color: '#00ffcc'}}
                          />
                          <Line type="monotone" yAxisId="left" dataKey="clv" name="Cumulative CLV (%)" stroke="#00ffcc" strokeWidth={3} dot={{r: 4, fill: '#00ffcc'}} activeDot={{r: 6}} />
                          <Line type="monotone" yAxisId="right" dataKey="pnl" name="Realized P&L ($)" stroke="#ec4899" strokeWidth={3} dot={{r: 4, fill: '#ec4899'}} activeDot={{r: 6}} />
                      </LineChart>
                  </ResponsiveContainer>
              </div>
          </div>
      )}

      <main className="glass-panel" style={{marginTop: '20px'}}>
        <div className="opportunities-header">
          <h2>Active +EV Opportunities (Live WebSockets)</h2>
          <button className="refresh-btn" onClick={() => fetchData(true)} disabled={loading}>
            {loading ? 'Scanning...' : 'Manual Scan'}
          </button>
        </div>

        {loading ? (
          <div className="loading">Executing mathematical scan across markets...</div>
        ) : opportunities.length === 0 ? (
          <div className="loading">No +EV opportunities found meeting system criteria.</div>
        ) : (
          <div className="opportunity-list">
            {opportunities.map((opp, idx) => (
              <div key={opp.event_id ? `${opp.event_id}-${opp.bet_on}` : idx} className="opp-card">
                <div className="opp-main">
                  <div className="opp-match">{opp.event}</div>
                  <div className="opp-details">
                    <span className="opp-bet">Bet: <strong>{opp.bet_on}</strong> @ {opp.soft_odds}</span>
                    <span className="opp-book">[{opp.soft_book}]</span>
                    <span>True Prob: {opp.true_probability}%</span>
                  </div>
                </div>
                <div className="opp-metrics">
                  <div className="opp-ev">+{opp.ev_percentage}% EV</div>
                  <div className="opp-stake">Rec. Stake: ${Number(opp.kelly_stake || 0).toFixed(2)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <main className="glass-panel" style={{marginTop: '20px', borderColor: 'rgba(255, 204, 0, 0.3)'}}>
        <div className="opportunities-header">
          <h2 style={{color: '#ffcc00'}}>Live Arbitrage Scanner (Guaranteed Profit)</h2>
        </div>

        {loading ? (
          <div className="loading">Executing cross-exchange scan...</div>
        ) : arbitrageOpps.length === 0 ? (
          <div className="loading">No risk-free Arbitrage opportunities found currently.</div>
        ) : (
          <div className="opportunity-list">
            {arbitrageOpps.map((arb, idx) => (
              <div key={arb.event_id || idx} className="opp-card" style={{borderLeft: '4px solid #ffcc00'}}>
                <div className="opp-main">
                  <div className="opp-match" style={{color: '#ffcc00'}}>{arb.match}</div>
                  <div className="opp-details" style={{display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px'}}>
                    {(arb.legs || []).map((leg, lIdx) => (
                      <span key={lIdx} style={{fontSize: '0.9rem'}}>
                        Bet <strong>${Number(leg.stake || 0).toFixed(2)}</strong> on <strong>{leg.outcome}</strong> @ {leg.odds} [{leg.bookmaker}]
                      </span>
                    ))}
                  </div>
                </div>
                <div className="opp-metrics">
                  <div className="opp-ev" style={{color: '#ffcc00'}}>+{arb.roi_percentage}% ROI</div>
                  <div className="opp-stake">Profit: ${Number(arb.guaranteed_profit || 0).toFixed(2)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <main className="glass-panel" style={{marginTop: '20px', borderColor: 'rgba(236, 72, 153, 0.3)'}}>
        <div className="opportunities-header">
          <h2 style={{color: '#ec4899'}}>Free Bet Conversion Scanner (Guaranteed Cash)</h2>
        </div>

        {loading ? (
          <div className="loading">Executing matched betting scan...</div>
        ) : matchedBets.length === 0 ? (
          <div className="loading">No Free Bet conversion opportunities found currently.</div>
        ) : (
          <div className="opportunity-list">
            {matchedBets.map((mb, idx) => (
              <div key={idx} className="opp-card" style={{borderLeft: '4px solid #ec4899'}}>
                <div className="opp-main">
                  <div className="opp-match" style={{color: '#ec4899'}}>{mb.event}</div>
                  <div className="opp-details" style={{display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px'}}>
                    <span style={{fontSize: '0.9rem'}}>Target: <strong>{mb.free_bet}</strong></span>
                    <span style={{fontSize: '0.9rem'}}>Hedge: <strong>{mb.hedge_bet}</strong></span>
                    <span style={{fontSize: '0.9rem'}}>Required Hedge Stake: <strong>${Number(mb.lay_stake_needed || 0).toFixed(2)}</strong></span>
                  </div>
                </div>
                <div className="opp-metrics">
                  <div className="opp-ev" style={{color: '#ec4899'}}>{Number(mb.conversion_rate || 0).toFixed(2)}% Conversion</div>
                  <div className="opp-stake">Guaranteed Profit: ${Number(mb.guaranteed_profit || 0).toFixed(2)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

export default App

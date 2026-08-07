import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceDot,
} from 'recharts'
import './App.css'
import { formatAr, formatArShort } from './time.js'

const API = import.meta.env.VITE_API_URL || ''

function money(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  return Number(v).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  })
}

function num(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <label>{label}</label>
      <strong className="mono">{value}</strong>
    </div>
  )
}

export default function App() {
  const [state, setState] = useState(null)
  const [equity, setEquity] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const [sRes, eRes] = await Promise.all([
          fetch(`${API}/api/state`),
          fetch(`${API}/api/equity`),
        ])
        if (!sRes.ok) throw new Error(`API ${sRes.status}`)
        const s = await sRes.json()
        const e = eRes.ok ? await eRes.json() : []
        if (!alive) return
        setState(s)
        setEquity(e)
        setError('')
      } catch (err) {
        if (!alive) return
        setError(
          'No se puede conectar al backend. Si estás en local, corré ./start.sh. ' +
            String(err.message || err),
        )
      }
    }
    load()
    const id = setInterval(load, 5000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const markers = useMemo(
    () =>
      equity.filter(
        (p) => p.reason === 'ENTRY' || p.reason === 'SMA_EXIT' || p.reason === 'SESSION_CLOSE',
      ),
    [equity],
  )

  const a = state?.account
  const st = state?.strategy
  const perf = state?.performance
  const pos = state?.current_position
  const trades = state?.trades || []

  return (
    <div>
      <header className="topbar">
        <div>
          <div className="muted" style={{ marginBottom: 6 }}>
            Forward test · PAPER ONLY · 1 MNQ · horas en Argentina
          </div>
          <h1 className="brand">MNQ Paper Desk</h1>
        </div>
        <div className="badge">
          <span className="dot" />
          {state?.health?.status || '…'} · {state?.meta?.trading_mode || 'PAPER'} ·{' '}
          {state?.meta?.data_provider || '…'}
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <div className="grid">
        <section className="panel">
          <h2>Account</h2>
          <div className="metrics">
            <Metric label="Initial" value={money(a?.initial_balance)} />
            <Metric label="Balance" value={money(a?.current_balance)} />
            <Metric label="Equity" value={money(a?.current_equity)} />
            <Metric label="Total PnL" value={money(a?.total_pnl)} />
            <Metric label="Realized" value={money(a?.realized_pnl)} />
            <Metric label="Unrealized" value={money(a?.unrealized_pnl)} />
            <Metric label="Max DD" value={money(a?.max_drawdown)} />
            <Metric label="Current DD" value={money(a?.current_drawdown)} />
          </div>
        </section>

        <section className={`panel ${st?.position === 'LONG' ? 'pos-long' : 'pos-flat'}`}>
          <h2>Strategy</h2>
          <div className="metrics">
            <Metric label="SMA" value={st?.sma_period ?? 4750} />
            <Metric label="Band" value={st?.band_points ?? 50} />
            <Metric label="Position" value={st?.position || '—'} />
            <Metric label="Current SMA" value={num(st?.current_sma)} />
            <Metric label="MNQ Price" value={num(st?.current_price)} />
            <Metric label="Entry thr" value={num(st?.entry_threshold)} />
            <Metric label="Exit thr" value={num(st?.exit_threshold)} />
            <Metric
              label="Bars"
              value={`${st?.bars_loaded ?? 0} / ${st?.bars_required ?? 4750}`}
            />
          </div>
        </section>

        <section className="panel">
          <h2>Performance</h2>
          <div className="metrics">
            <Metric label="Trades" value={perf?.total_trades ?? 0} />
            <Metric label="Wins" value={perf?.winning_trades ?? 0} />
            <Metric label="Losses" value={perf?.losing_trades ?? 0} />
            <Metric label="Win rate" value={`${num(perf?.win_rate, 1)}%`} />
            <Metric
              label="Profit factor"
              value={perf?.profit_factor_display ?? '—'}
            />
            <Metric label="Avg trade" value={money(perf?.average_trade)} />
            <Metric label="Largest win" value={money(perf?.largest_winner)} />
            <Metric label="Largest loss" value={money(perf?.largest_loser)} />
            <Metric
              label="Longest losing streak"
              value={perf?.longest_losing_streak ?? 0}
            />
          </div>
        </section>

        <section className="panel">
          <h2>Current Position</h2>
          <div className="pos-block metrics">
            <Metric label="State" value={pos?.state || 'FLAT'} />
            <Metric label="Entry time (AR)" value={formatAr(pos?.entry_time)} />
            <Metric label="Entry price" value={num(pos?.entry_price)} />
            <Metric label="Current price" value={num(pos?.current_price)} />
            <Metric label="PnL" value={money(pos?.pnl)} />
            <Metric label="Duration" value={pos?.duration || '—'} />
          </div>
        </section>

        <section className="panel wide">
          <h2>Equity Curve</h2>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equity}>
                <CartesianGrid stroke="rgba(19,33,43,0.08)" />
                <XAxis
                  dataKey="ts"
                  tick={{ fontSize: 11 }}
                  minTickGap={40}
                  tickFormatter={(v) => formatArShort(v)}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tick={{ fontSize: 11 }}
                  width={70}
                  tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
                />
                <Tooltip
                  formatter={(v) => money(v)}
                  labelFormatter={(l) => formatAr(l)}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#0f7a6b"
                  dot={false}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                {markers.map((m) => (
                  <ReferenceDot
                    key={`${m.ts}-${m.reason}`}
                    x={m.ts}
                    y={m.equity}
                    r={4}
                    fill={m.reason === 'ENTRY' ? '#0f7a6b' : '#b42318'}
                    stroke="#fff"
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="panel full">
          <h2>Trades</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Entry</th>
                  <th>Entry fill</th>
                  <th>Exit</th>
                  <th>Exit fill</th>
                  <th>Gross</th>
                  <th>Fees</th>
                  <th>Net</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {[...trades].reverse().map((t) => (
                  <tr key={t.trade_id}>
                    <td className="mono">{t.trade_id}</td>
                    <td>{t.status}</td>
                    <td className="mono">{formatAr(t.entry_time)}</td>
                    <td className="mono">{num(t.entry_fill_price)}</td>
                    <td className="mono">{formatAr(t.exit_time)}</td>
                    <td className="mono">{num(t.exit_fill_price)}</td>
                    <td className="mono">{money(t.gross_pnl)}</td>
                    <td className="mono">{money(t.commission)}</td>
                    <td className="mono">{money(t.net_pnl)}</td>
                    <td>{t.exit_reason || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <p className="footer-note muted">
        Experiment started (AR):{' '}
        <span className="mono">
          {formatAr(state?.meta?.experiment_started_at) || 'not yet'}
        </span>
        {' · '}
        Strategy frozen: SMA 4750 / Band 50 / LONG only / On bar close
      </p>
    </div>
  )
}

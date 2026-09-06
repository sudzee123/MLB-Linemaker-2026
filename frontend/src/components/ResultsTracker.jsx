import { useState, useRef } from 'react'

// ── Linear regression trend line ─────────────────────────────────────────────
function addTrend(data) {
  if (data.length < 2) return data.map(d => ({ ...d, trend: d.cumulative_units }))
  const n = data.length
  const xs = data.map((_, i) => i)
  const ys = data.map(d => d.cumulative_units)
  const mx = xs.reduce((s, x) => s + x, 0) / n
  const my = ys.reduce((s, y) => s + y, 0) / n
  const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0)
  const den = xs.reduce((s, x) => s + (x - mx) ** 2, 0)
  const slope = den ? num / den : 0
  const intercept = my - slope * mx
  return data.map((d, i) => ({
    ...d,
    trend: Math.round((slope * i + intercept) * 1000) / 1000,
  }))
}

function fmt(ml) {
  if (ml == null) return '—'
  return ml > 0 ? `+${ml}` : `${ml}`
}

function fmtDateShort(dateStr) {
  const [, m, d] = dateStr.split('-')
  return `${parseInt(m)}/${parseInt(d)}`
}

function collapseByDay(data) {
  const byDate = {}
  for (const d of data) {
    if (!byDate[d.date]) byDate[d.date] = { date: d.date, units: 0, game_count: 0 }
    byDate[d.date].units = Math.round((byDate[d.date].units + d.units) * 1000) / 1000
    byDate[d.date].game_count += 1
  }
  let cumulative = 0
  return Object.keys(byDate).sort().map((date, i) => {
    const day = byDate[date]
    cumulative = Math.round((cumulative + day.units) * 1000) / 1000
    return {
      date,
      play_num: i + 1,
      units: day.units,
      cumulative_units: cumulative,
      result: day.units >= 0 ? 'W' : 'L',
      game_count: day.game_count,
    }
  })
}

// ── Pure SVG chart ────────────────────────────────────────────────────────────
function UnitChart({ rawData, mode = 'game' }) {
  const [hovered, setHovered] = useState(null)
  const svgRef = useRef(null)

  const data = addTrend(rawData)
  const n = data.length
  if (n === 0) return null

  const VW = 600, VH = 200
  const pad = { top: 16, right: 16, bottom: 28, left: 46 }
  const plotW = VW - pad.left - pad.right
  const plotH = VH - pad.top - pad.bottom

  const ys = data.map(d => d.cumulative_units)
  const trends = data.map(d => d.trend)
  const yMin = Math.min(0, ...ys, ...trends)
  const yMax = Math.max(0, ...ys, ...trends)
  const yRange = yMax - yMin || 1

  const sx = i => pad.left + (i / Math.max(n - 1, 1)) * plotW
  const sy = v => pad.top + plotH - ((v - yMin) / yRange) * plotH

  const unitPath = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(i).toFixed(1)},${sy(d.cumulative_units).toFixed(1)}`).join(' ')
  const trendPath = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(i).toFixed(1)},${sy(d.trend).toFixed(1)}`).join(' ')

  // Y axis ticks: 5 evenly spaced
  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + (i / 4) * yRange)

  // X labels: show at most 8, always include first and last
  const step = Math.ceil(n / 8)
  const showX = i => n <= 8 || i % step === 0 || i === n - 1

  const handleEnter = (d, i) => {
    if (!svgRef.current) return
    setHovered({ d, svgX: sx(i), svgY: sy(d.cumulative_units) })
  }

  return (
    <div className="chart-container">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VW} ${VH}`}
        className="unit-chart-svg"
        onMouseLeave={() => setHovered(null)}
      >
        {/* Horizontal grid lines + Y labels */}
        {yTicks.map((v, ti) => {
          const y = sy(v)
          const isZero = Math.abs(v) < yRange * 0.01
          return (
            <g key={ti}>
              <line
                x1={pad.left} y1={y} x2={VW - pad.right} y2={y}
                stroke={isZero ? '#2a3f55' : '#141f2e'}
                strokeWidth={isZero ? 1 : 0.5}
              />
              <text x={pad.left - 6} y={y + 4} textAnchor="end" fill="#475569" fontSize="11" fontFamily="monospace">
                {v >= 0 ? `+${v.toFixed(1)}` : v.toFixed(1)}
              </text>
            </g>
          )
        })}

        {/* X axis labels */}
        {data.map((d, i) => showX(i) && (
          <text key={i} x={sx(i)} y={VH - 6} textAnchor="middle" fill="#475569" fontSize="11" fontFamily="monospace">
            {mode === 'day' ? fmtDateShort(d.date) : d.play_num}
          </text>
        ))}

        {/* Trend line */}
        {n > 1 && (
          <path d={trendPath} fill="none" stroke="#38bdf8" strokeWidth="1.5" strokeDasharray="6 4" opacity="0.65" />
        )}

        {/* Cumulative units line */}
        <path d={unitPath} fill="none" stroke="#34d399" strokeWidth="2" strokeLinejoin="round" />

        {/* Dots with hit areas */}
        {data.map((d, i) => (
          <g key={i} onMouseEnter={() => handleEnter(d, i)}>
            <circle cx={sx(i)} cy={sy(d.cumulative_units)} r="10" fill="transparent" style={{ cursor: 'crosshair' }} />
            <circle
              cx={sx(i)} cy={sy(d.cumulative_units)} r="4"
              fill={d.result === 'W' ? '#34d399' : '#f87171'}
              stroke="#0a0e17" strokeWidth="1.5"
            />
          </g>
        ))}
      </svg>

      {/* Floating tooltip — positioned relative to chart-container */}
      {hovered && (() => {
        const { d, svgX, svgY } = hovered
        // Convert SVG coords → percentage → CSS position
        const leftPct = (svgX / VW * 100).toFixed(1)
        const topPct = (svgY / VH * 100).toFixed(1)
        const unitsStr = d.units >= 0 ? `+${d.units}` : `${d.units}`
        const runStr = d.cumulative_units >= 0 ? `+${d.cumulative_units}` : `${d.cumulative_units}`
        return (
          <div className="chart-tooltip" style={{ left: `${leftPct}%`, top: `${topPct}%` }}>
            {mode === 'day' ? (
              <>
                <div><span className="ct-team">{d.date}</span></div>
                <div className="ct-date">{d.game_count} game{d.game_count !== 1 ? 's' : ''}</div>
                <div className="ct-units">{unitsStr}u → {runStr}u running</div>
              </>
            ) : (
              <>
                <div>
                  <span className="ct-team">{d.team} vs {d.opponent}</span>
                  <span className={d.result === 'W' ? 'ct-win' : 'ct-loss'}> {d.result}</span>
                </div>
                <div className="ct-date">{d.date} · {d.edge_pct} edge</div>
                <div className="ct-units">{unitsStr}u → {runStr}u running</div>
              </>
            )}
          </div>
        )
      })()}

      <div className="chart-legend">
        <span className="legend-item">
          <span className="legend-dot green-dot" /> Units
        </span>
        <span className="legend-item">
          <span className="legend-dash" /> Trend
        </span>
        <span className="legend-item">
          <span className="legend-dot win-dot" /> Win
        </span>
        <span className="legend-item">
          <span className="legend-dot loss-dot" /> Loss
        </span>
      </div>
    </div>
  )
}

// ── History table ─────────────────────────────────────────────────────────────
function HistoryTable({ chartData, onUpdate, onDelete }) {
  const [deleting, setDeleting] = useState(null)
  const [editing, setEditing] = useState(null)   // id of row being edited
  const [draft, setDraft] = useState({})          // { result, book_ml, edge_pct }
  const [saving, setSaving] = useState(false)

  const startEdit = (r) => {
    setEditing(r.id)
    setDraft({ result: r.result, book_ml: r.book_ml, edge_pct: r.edge_pct })
  }

  const cancelEdit = () => { setEditing(null); setDraft({}) }

  const saveEdit = async () => {
    setSaving(true)
    try {
      await onUpdate(editing, {
        result: draft.result,
        book_ml: parseInt(draft.book_ml, 10),
        edge_pct: draft.edge_pct,
      })
      setEditing(null)
      setDraft({})
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    setDeleting(id)
    await onDelete(id)
    setDeleting(null)
  }

  const rows = [...chartData].reverse()

  return (
    <div className="results-history">
      <div className="rh-header">
        <span>Date</span>
        <span>Play</span>
        <span>ML</span>
        <span>Edge</span>
        <span>W/L</span>
        <span>Units</span>
        <span>Running</span>
        <span />
      </div>
      {rows.map(r => {
        if (editing === r.id) {
          return (
            <div key={r.id} className="rh-row rh-editing">
              <span className="rh-date">{r.date}</span>
              <span className="rh-team">{r.team} vs {r.opponent}</span>
              <input
                className="rh-edit-input"
                type="number"
                value={draft.book_ml}
                onChange={e => setDraft(d => ({ ...d, book_ml: e.target.value }))}
                title="Book ML"
              />
              <input
                className="rh-edit-input"
                type="text"
                value={draft.edge_pct}
                onChange={e => setDraft(d => ({ ...d, edge_pct: e.target.value }))}
                title="Edge %"
              />
              <button
                className={`rh-wl-toggle ${draft.result === 'W' ? 'green' : 'red'}`}
                onClick={() => setDraft(d => ({ ...d, result: d.result === 'W' ? 'L' : 'W' }))}
                title="Toggle W/L"
              >
                {draft.result}
              </button>
              <span className="rh-edit-spacer" />
              <span className="rh-edit-spacer" />
              <span className="rh-edit-actions">
                <button className="rh-save" onClick={saveEdit} disabled={saving}>✓</button>
                <button className="rh-cancel" onClick={cancelEdit} disabled={saving}>×</button>
              </span>
            </div>
          )
        }

        const unitPos = r.units >= 0
        const runPos = r.cumulative_units >= 0
        return (
          <div key={r.id} className={`rh-row ${r.result === 'W' ? 'rh-win' : 'rh-loss'}`}>
            <span className="rh-date">{r.date}</span>
            <span className="rh-team">{r.team} vs {r.opponent}</span>
            <span className="rh-ml">{fmt(r.book_ml)}</span>
            <span className="rh-edge">{r.edge_pct}</span>
            <span className={`rh-result ${r.result === 'W' ? 'green' : 'red'}`}>{r.result}</span>
            <span className={unitPos ? 'green' : 'red'}>{unitPos ? '+' : ''}{r.units}u</span>
            <span className={runPos ? 'green' : 'red'}>{runPos ? '+' : ''}{r.cumulative_units}u</span>
            <span className="rh-row-actions">
              <button className="rh-edit" onClick={() => startEdit(r)} title="Edit this result">✎</button>
              <button
                className="rh-del"
                onClick={() => handleDelete(r.id)}
                disabled={deleting === r.id}
                title="Remove this result"
              >×</button>
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Conflict breakdown ────────────────────────────────────────────────────────
const PAIR_LABELS = {
  season_vs_l30: { keys: ['season', 'l30'], labels: { season: 'Season', l30: 'L30' } },
  season_vs_l21: { keys: ['season', 'l21'], labels: { season: 'Season', l21: 'L21' } },
  l30_vs_l21:   { keys: ['l30', 'l21'],   labels: { l30: 'L30', l21: 'L21' } },
}

function ConflictStat({ label, data }) {
  if (!data) return null
  const netPos = data.net_units >= 0
  const roiPos = data.roi_pct >= 0
  return (
    <div className="conflict-side">
      <div className="conflict-side-label">{label}</div>
      <div className="conflict-side-stats">
        <span className="cs-record">{data.wins}–{data.losses}</span>
        <span className={`cs-units ${netPos ? 'green' : 'red'}`}>
          {netPos ? '+' : ''}{data.net_units}u
        </span>
        <span className={`cs-roi ${roiPos ? 'green' : 'red'}`}>
          ROI {roiPos ? '+' : ''}{data.roi_pct}%
        </span>
        <span className="cs-plays">{data.total_plays} play{data.total_plays !== 1 ? 's' : ''}</span>
      </div>
    </div>
  )
}

function ConflictBreakdown({ breakdown }) {
  if (!breakdown) return <div className="state-msg">Loading…</div>

  const allEmpty = Object.values(breakdown).every(d => d.game_count === 0)
  if (allEmpty) return (
    <div className="state-msg">No settled plays from conflicting games yet.</div>
  )

  return (
    <div className="conflict-breakdown">
      {Object.entries(PAIR_LABELS).map(([pairKey, { keys, labels }]) => {
        const data = breakdown[pairKey]
        if (!data || data.game_count === 0) return null
        const [w1, w2] = keys
        return (
          <div key={pairKey} className="conflict-pair">
            <div className="conflict-pair-header">
              {labels[w1]} vs {labels[w2]}
              <span className="conflict-game-count">{data.game_count} game{data.game_count !== 1 ? 's' : ''}</span>
            </div>
            <div className="conflict-pair-body">
              <ConflictStat label={labels[w1]} data={data[w1]} />
              <div className="conflict-divider">vs</div>
              <ConflictStat label={labels[w2]} data={data[w2]} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Window selector ───────────────────────────────────────────────────────────
const WINDOW_LABELS = { season: 'Season', l30: 'L30', l21: 'L21', conflicts: 'Conflicts' }

function WindowSelector({ window, onChange }) {
  return (
    <div className="window-selector">
      {Object.entries(WINDOW_LABELS).map(([key, label]) => (
        <button
          key={key}
          className={`ws-btn${window === key ? ' ws-active' : ''}`}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function ExportCSV({ chartData, windowLabel }) {
  const handle = () => {
    const headers = ['date', 'team', 'opponent', 'window', 'book_ml', 'edge_pct', 'result', 'units', 'cumulative_units']
    const rows = chartData.map(r => [
      r.date, r.team, r.opponent, r.window ?? windowLabel,
      r.book_ml, r.edge_pct, r.result, r.units, r.cumulative_units,
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `linemaker_${windowLabel}_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <button className="backfill-btn" onClick={handle}>Export CSV</button>
  )
}

function BackfillButton({ onRefresh }) {
  const [state, setState] = useState('idle') // idle | running | done | error
  const [msg, setMsg] = useState('')

  const run = async () => {
    setState('running')
    setMsg('')
    try {
      const res = await fetch('/api/backfill-windows', { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Request failed')
      setMsg(`${data.entries_created} entries added across ${data.dates_processed} dates`)
      setState('done')
      if (data.entries_created > 0) onRefresh()
    } catch (e) {
      setMsg(e.message)
      setState('error')
    }
  }

  return (
    <div className="backfill-row">
      <button
        className="backfill-btn"
        onClick={run}
        disabled={state === 'running'}
      >
        {state === 'running' ? 'Backfilling…' : 'Backfill L30/L21 History'}
      </button>
      {msg && (
        <span className={`backfill-msg ${state === 'error' ? 'backfill-err' : 'backfill-ok'}`}>
          {msg}
        </span>
      )}
    </div>
  )
}

// ── Results filter ────────────────────────────────────────────────────────────
function ResultsFilter({
  startDate, endDate, onStartDateChange, onEndDateChange,
  minEdge, onMinEdgeChange, maxEdge, onMaxEdgeChange,
  mlMin, onMlMinChange, mlMax, onMlMaxChange,
  team, onTeamChange,
  prevLossFilter, onPrevLossFilterChange,
}) {
  const isFiltered = startDate || endDate || minEdge !== '' || maxEdge !== '' || mlMin !== '' || mlMax !== '' || team !== '' || prevLossFilter

  function clearAll() {
    onStartDateChange(''); onEndDateChange('')
    onMinEdgeChange(''); onMaxEdgeChange(''); onMlMinChange(''); onMlMaxChange('')
    onTeamChange('')
    onPrevLossFilterChange(false)
  }

  return (
    <div className="results-filter">
      {/* Row 1: date range */}
      <div className="rf-row">
        <span className="drf-label">Date Range</span>
        <button
          className={`drf-alltime${!startDate && !endDate ? ' drf-active' : ''}`}
          onClick={() => { onStartDateChange(''); onEndDateChange('') }}
        >
          All Time
        </button>
        <div className="drf-inputs">
          <input type="date" className="drf-input" value={startDate}
            onChange={e => onStartDateChange(e.target.value)} title="Start date" />
          <span className="drf-sep">→</span>
          <input type="date" className="drf-input" value={endDate}
            onChange={e => onEndDateChange(e.target.value)} title="End date" />
        </div>
      </div>

      {/* Row 2: edge % + ML range */}
      <div className="rf-row rf-row-divider">
        <span className="drf-label">Edge %</span>
        <div className="drf-inputs">
          <input
            type="number"
            className="drf-input drf-number"
            value={minEdge}
            onChange={e => onMinEdgeChange(e.target.value)}
            placeholder="Min"
            min="0"
            step="0.1"
            title="Minimum edge percentage"
          />
          <span className="drf-sep">→</span>
          <input
            type="number"
            className="drf-input drf-number"
            value={maxEdge}
            onChange={e => onMaxEdgeChange(e.target.value)}
            placeholder="Max"
            min="0"
            step="0.1"
            title="Maximum edge percentage"
          />
        </div>

        <span className="drf-label rf-ml-label">ML Range</span>
        <div className="drf-inputs">
          <input
            type="number"
            className="drf-input drf-number"
            value={mlMin}
            onChange={e => onMlMinChange(e.target.value)}
            placeholder="Min"
            step="5"
            title="Minimum moneyline (e.g. -200)"
          />
          <span className="drf-sep">→</span>
          <input
            type="number"
            className="drf-input drf-number"
            value={mlMax}
            onChange={e => onMlMaxChange(e.target.value)}
            placeholder="Max"
            step="5"
            title="Maximum moneyline (e.g. +300)"
          />
        </div>

        {isFiltered && (
          <button className="drf-clear" onClick={clearAll}>Clear All</button>
        )}
      </div>

      {/* Row 3: team filter */}
      <div className="rf-row rf-row-divider">
        <span className="drf-label">Team</span>
        <div className="drf-inputs">
          <input
            type="text"
            className="drf-input drf-team"
            value={team}
            onChange={e => onTeamChange(e.target.value)}
            placeholder="e.g. NYY"
            maxLength={5}
            title="Filter by team abbreviation"
          />
        </div>
      </div>

      {/* Row 4: series loss qualifier */}
      <div className="rf-row rf-row-divider">
        <label className="drf-toggle-label">
          <input
            type="checkbox"
            className="drf-toggle"
            checked={prevLossFilter}
            onChange={e => onPrevLossFilterChange(e.target.checked)}
          />
          <span>Game 2+ · prev game L</span>
          <span className="drf-toggle-hint">edge ≤ 10% · ML ≥ −109 in prior game of same series</span>
        </label>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ResultsTracker({
  summary, conflictBreakdown, loading, onUpdate, onDelete, onRefresh,
  window, onWindowChange,
  startDate, endDate, onStartDateChange, onEndDateChange,
  minEdge, onMinEdgeChange, maxEdge, onMaxEdgeChange,
  mlMin, onMlMinChange, mlMax, onMlMaxChange,
  team, onTeamChange,
  prevLossFilter, onPrevLossFilterChange,
}) {
  const isFiltered = startDate || endDate || minEdge !== '' || maxEdge !== '' || mlMin !== '' || mlMax !== '' || team !== '' || prevLossFilter

  const filterProps = {
    startDate, endDate, onStartDateChange, onEndDateChange,
    minEdge, onMinEdgeChange, maxEdge, onMaxEdgeChange,
    mlMin, onMlMinChange, mlMax, onMlMaxChange,
    team, onTeamChange,
    prevLossFilter, onPrevLossFilterChange,
  }

  if (window === 'conflicts') {
    return (
      <div className="results-tracker">
        <WindowSelector window={window} onChange={onWindowChange} />
        {loading
          ? <div className="state-msg">Loading…</div>
          : <ConflictBreakdown breakdown={conflictBreakdown} />
        }
      </div>
    )
  }

  if (loading) return (
    <div className="results-tracker">
      <WindowSelector window={window} onChange={onWindowChange} />
      <BackfillButton onRefresh={onRefresh} />
      <ResultsFilter {...filterProps} />
      <div className="state-msg">Loading results…</div>
    </div>
  )

  if (!summary || summary.total_plays === 0) {
    return (
      <div className="results-tracker">
        <WindowSelector window={window} onChange={onWindowChange} />
        <div className="backfill-row"><BackfillButton onRefresh={onRefresh} /></div>
        <ResultsFilter {...filterProps} />
        <p className="results-empty">
          {isFiltered
            ? 'No plays match the current filters.'
            : 'No plays logged yet. Games with Season edge ≥ 1% are tracked automatically.'
          }
        </p>
      </div>
    )
  }

  const [chartMode, setChartMode] = useState('game')

  const netPos = summary.net_units >= 0
  const roiPos = summary.roi_pct >= 0

  const chartData = chartMode === 'day'
    ? collapseByDay(summary.chart_data)
    : summary.chart_data

  return (
    <div className="results-tracker">
      <WindowSelector window={window} onChange={onWindowChange} />
      <div className="backfill-row">
        <BackfillButton onRefresh={onRefresh} />
        {summary?.chart_data?.length > 0 && (
          <ExportCSV chartData={summary.chart_data} windowLabel={window} />
        )}
      </div>
      <ResultsFilter {...filterProps} />

      {/* Stats pills */}
      <div className="summary-bar">
        <div className="stat-pill">
          <span className="pill-label">Record</span>
          <span className="pill-value">{summary.wins}–{summary.losses}</span>
        </div>
        <div className="stat-pill">
          <span className="pill-label">Net Units</span>
          <span className={`pill-value ${netPos ? 'green' : 'red'}`}>
            {netPos ? '+' : ''}{summary.net_units}u
          </span>
        </div>
        <div className="stat-pill">
          <span className="pill-label">ROI</span>
          <span className={`pill-value ${roiPos ? 'green' : 'red'}`}>
            {roiPos ? '+' : ''}{summary.roi_pct}%
          </span>
        </div>
        <div className="stat-pill">
          <span className="pill-label">Plays</span>
          <span className="pill-value">{summary.total_plays}</span>
        </div>
      </div>

      {/* Chart */}
      <div className="chart-mode-toggle">
        <button className={`cmt-btn${chartMode === 'game' ? ' cmt-active' : ''}`} onClick={() => setChartMode('game')}>By Game</button>
        <button className={`cmt-btn${chartMode === 'day' ? ' cmt-active' : ''}`} onClick={() => setChartMode('day')}>By Day</button>
      </div>
      <UnitChart rawData={chartData} mode={chartMode} />

      {/* History */}
      <HistoryTable chartData={summary.chart_data} onUpdate={onUpdate} onDelete={onDelete} />
    </div>
  )
}

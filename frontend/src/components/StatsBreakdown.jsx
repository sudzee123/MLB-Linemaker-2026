import { useState } from 'react'

export default function StatsBreakdown({ side }) {
  const [open, setOpen] = useState(false)
  const p = side.pitcher

  return (
    <div className="breakdown">
      <button className="breakdown-toggle" onClick={() => setOpen(o => !o)}>
        {open ? '▲' : '▼'} Calculation detail
      </button>
      {open && (
        <div className="breakdown-body">
          <Row label="RS/G (season)" value={side.rs_pg} />
          <Row label="SP ERA" value={p.sp_era} />
          <Row label="SP IP/GS" value={p.sp_ip_per_gs} />
          <Row label="SP GS" value={p.sp_gs} />
          <Row label="BP ERA" value={p.bp_era} />
          <Row label="Starter contrib" value={p.starter_contribution?.toFixed(3)} />
          <Row label="Bullpen contrib" value={p.bullpen_contribution?.toFixed(3)} />
          <Row label="Recalc RA/G" value={p.recalc_ra} />
          <Row label="Exp runs" value={side.exp_r} />
          <Row label="Win prob" value={`${(side.win_prob * 100).toFixed(1)}%`} />
          <Row label="Fair ML" value={fmt(side.fair_ml)} />
          {side.book_implied_prob != null && (
            <Row label="Book impl prob" value={`${(side.book_implied_prob * 100).toFixed(1)}%`} />
          )}
          <Row label="Edge" value={side.edge_pct} highlight={side.has_edge} />
        </div>
      )}
    </div>
  )
}

function Row({ label, value, highlight }) {
  return (
    <div className={`bd-row ${highlight ? 'bd-highlight' : ''}`}>
      <span className="bd-label">{label}</span>
      <span className="bd-value">{value ?? '—'}</span>
    </div>
  )
}

function fmt(ml) {
  if (ml == null) return '—'
  return ml > 0 ? `+${ml}` : `${ml}`
}

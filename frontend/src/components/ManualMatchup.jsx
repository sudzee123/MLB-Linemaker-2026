import { useManual } from '../hooks/useManual'

function fmt(ml) {
  if (ml == null) return '—'
  return ml > 0 ? `+${ml}` : `${ml}`
}

function TeamPicker({ label, teams, team, onTeam, pitchers, pitcher, onPitcher, ml, onMl }) {
  return (
    <div className="mm-picker">
      <div className="mm-picker-label">{label}</div>
      <select className="mm-select" value={team} onChange={e => onTeam(e.target.value)}>
        <option value="">Select team…</option>
        {teams.map(t => (
          <option key={t.team_id} value={t.team_id}>{t.name}</option>
        ))}
      </select>
      <select
        className="mm-select"
        value={pitcher}
        onChange={e => onPitcher(e.target.value)}
        disabled={!team}
      >
        <option value="">{team ? 'Starter (optional)…' : 'Select team first'}</option>
        {team && <option value="TEAM">Team (overall ERA)</option>}
        {pitchers.map(p => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>
      <input
        className="mm-ml-input"
        type="number"
        step="5"
        value={ml}
        onChange={e => onMl(e.target.value)}
        placeholder="Line (optional, e.g. -130)"
      />
    </div>
  )
}

function WindowRow({ label, aw, hw }) {
  return (
    <div className="mm-window-row">
      <div className="mm-window-label">{label}</div>
      <div className="mm-window-sides">
        <div className={`mm-side${aw.has_edge ? ' mm-side-edge' : ''}`}>
          <span className="mm-fair">{fmt(aw.fair_ml)}</span>
          <span className="mm-winp">{(aw.win_prob * 100).toFixed(1)}%</span>
          <span className="mm-expr">{aw.exp_r} R</span>
          {aw.edge_pct !== 'N/A' && (
            <span className={`mm-edge${aw.has_edge ? ' pos' : ' neg'}`}>{aw.edge_pct}</span>
          )}
        </div>
        <div className="mm-vs">vs</div>
        <div className={`mm-side${hw.has_edge ? ' mm-side-edge' : ''}`}>
          <span className="mm-fair">{fmt(hw.fair_ml)}</span>
          <span className="mm-winp">{(hw.win_prob * 100).toFixed(1)}%</span>
          <span className="mm-expr">{hw.exp_r} R</span>
          {hw.edge_pct !== 'N/A' && (
            <span className={`mm-edge${hw.has_edge ? ' pos' : ' neg'}`}>{hw.edge_pct}</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ManualMatchup() {
  const m = useManual()
  const r = m.result

  return (
    <div className="manual-matchup">
      <p className="mm-intro">
        Generate hypothetical Season / L30 / L21 lines for any matchup. Pitchers and book
        lines are optional — enter a line to see edges, or leave blank for a pure projection.
        Nothing here is tracked or saved.
      </p>

      <div className="mm-pickers">
        <TeamPicker
          label="Away"
          teams={m.teams}
          team={m.awayTeam} onTeam={m.setAwayTeam}
          pitchers={m.awayPitchers}
          pitcher={m.awayPitcher} onPitcher={m.setAwayPitcher}
          ml={m.awayMl} onMl={m.setAwayMl}
        />
        <TeamPicker
          label="Home"
          teams={m.teams}
          team={m.homeTeam} onTeam={m.setHomeTeam}
          pitchers={m.homePitchers}
          pitcher={m.homePitcher} onPitcher={m.setHomePitcher}
          ml={m.homeMl} onMl={m.setHomeMl}
        />
      </div>

      <button
        className="mm-generate"
        onClick={m.generate}
        disabled={m.loading || !m.awayTeam || !m.homeTeam}
      >
        {m.loading ? 'Generating…' : 'Generate Lines'}
      </button>

      {m.error && <div className="state-msg error">Error: {m.error}</div>}

      {r && (
        <div className="mm-result">
          <div className="mm-result-header">
            <span className="mm-team-block">
              <strong>{r.away.abbrev}</strong> {r.away.pitcher_name}
              {r.away.book_ml != null && <span className="mm-book"> · {fmt(r.away.book_ml)}</span>}
            </span>
            <span className="at">@</span>
            <span className="mm-team-block">
              <strong>{r.home.abbrev}</strong> {r.home.pitcher_name}
              {r.home.book_ml != null && <span className="mm-book"> · {fmt(r.home.book_ml)}</span>}
            </span>
          </div>

          <div className="mm-legend">
            <span>Fair ML</span><span>Win%</span><span>Exp R</span>
            {(r.away.book_ml != null || r.home.book_ml != null) && <span>Edge</span>}
          </div>

          <WindowRow label="Season" aw={r.windows.season.away} hw={r.windows.season.home} />
          <WindowRow label="L30" aw={r.windows.l30.away} hw={r.windows.l30.home} />
          <WindowRow label="L21" aw={r.windows.l21.away} hw={r.windows.l21.home} />
        </div>
      )}
    </div>
  )
}

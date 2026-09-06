import { useState } from 'react'

function fmt(ml) {
  if (ml == null) return '—'
  return ml > 0 ? `+${ml}` : `${ml}`
}

function PlayRow({ play, onSettle, onRemove }) {
  const [settled, setSettled] = useState(null)

  const handle = (result) => {
    setSettled(result)
    onSettle(play.game_id, play.team_abbrev, result)
  }

  const we = play.windowEdges || {}

  return (
    <div className="play-row">
      <div className="play-info">
        <span className="play-date">{play.game_date}</span>
        <span className="play-matchup">
          <strong>{play.team_abbrev}</strong>
          <span className="play-vs"> vs {play.opponent_abbrev}</span>
          <span className="play-side">{play.side}</span>
        </span>
        <span className="play-line">{fmt(play.book_ml)}</span>
        {play.book_name && <span className="play-book">{play.book_name}</span>}
        <span className="play-window-edges">
          {we.season && <span className="pwe-item"><span className="pwe-lbl">S</span>{we.season}</span>}
          {we.l30    && <span className="pwe-item"><span className="pwe-lbl">30</span>{we.l30}</span>}
          {we.l21    && <span className="pwe-item"><span className="pwe-lbl">21</span>{we.l21}</span>}
        </span>
      </div>

      <div className="play-actions">
        {settled ? (
          <span className="log-confirmed">{settled === 'W' ? '✓ Win logged' : '✓ Loss logged'}</span>
        ) : (
          <>
            <button className="log-btn log-win" onClick={() => handle('W')}>W</button>
            <button className="log-btn log-loss" onClick={() => handle('L')}>L</button>
            <button className="play-remove" onClick={() => onRemove(play.game_id, play.team_abbrev)} title="Remove">✕</button>
          </>
        )}
      </div>
    </div>
  )
}

export default function TrackedPlays({ grouped, loading, onSettle, onRemove }) {
  if (loading) return <div className="state-msg">Loading…</div>

  if (!grouped.length) return (
    <div className="state-msg">
      No pending plays. Games with Season edge ≥ 1% are tracked automatically.
    </div>
  )

  return (
    <div className="tracked-plays">
      {grouped.map(p => (
        <PlayRow key={`${p.game_id}-${p.team_abbrev}`} play={p} onSettle={onSettle} onRemove={onRemove} />
      ))}
    </div>
  )
}

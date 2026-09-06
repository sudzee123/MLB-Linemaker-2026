import { useState } from 'react'
import EdgeBadge from './EdgeBadge'
import StatsBreakdown from './StatsBreakdown'

function fmt(ml) {
  if (ml == null) return '—'
  return ml > 0 ? `+${ml}` : `${ml}`
}

function LogButtons({ onLog }) {
  const [logged, setLogged] = useState(null)

  const handle = (result) => {
    setLogged(result)
    onLog(result)
    setTimeout(() => setLogged(null), 3000)
  }

  if (logged) {
    return (
      <div className="log-result-row">
        <span className="log-confirmed">{logged === 'W' ? '✓ Win logged' : '✓ Loss logged'}</span>
      </div>
    )
  }

  return (
    <div className="log-result-row">
      <span className="log-label">Log result:</span>
      <button className="log-btn log-win" onClick={() => handle('W')}>W</button>
      <button className="log-btn log-loss" onClick={() => handle('L')}>L</button>
    </div>
  )
}

function WindowEdges({ windows }) {
  if (!windows) return null
  const entries = [
    { key: 'season', label: 'S' },
    { key: 'l30',    label: '30' },
    { key: 'l21',    label: '21' },
  ]
  return (
    <div className="window-edges">
      {entries.map(({ key, label }) => {
        const w = windows[key]
        if (!w) return null
        return (
          <span key={key} className={`we-item${w.has_edge ? ' we-edge' : ''}`}>
            <span className="we-lbl">{label}</span>
            <span className="we-val">{w.edge_pct}</span>
          </span>
        )
      })}
    </div>
  )
}

function TeamSide({ side, label, onLogResult, isTracked, isPast }) {
  return (
    <div className={`team-col ${side.has_edge_any ? 'has-edge' : ''}`}>
      <div className="team-header">
        <span className="team-name">{side.team_name}</span>
        <span className="team-tag">{label}</span>
      </div>

      <div className="team-sp">
        <span className="sp-name">{side.pitcher?.name || 'TBD'}</span>
        {side.pitcher?.sp_gs > 0 && (
          <span className="sp-era">ERA {side.pitcher.sp_era}</span>
        )}
      </div>

      <div className="lines-block">
        <div className="line-row book-line">
          <span className="line-label">
            {side.book_name ? `Book (${side.book_name})` : 'Book'}
          </span>
          <span className="line-value">{fmt(side.book_ml)}</span>
          {side.book_implied_prob != null && (
            <span className="line-prob">{(side.book_implied_prob * 100).toFixed(1)}%</span>
          )}
        </div>
      </div>

      <WindowEdges windows={side.windows} />

      <StatsBreakdown side={side} />

      {isTracked && (
        <div className="log-result-row">
          <span className="auto-tracked-badge">Auto-tracked</span>
        </div>
      )}

      {onLogResult && (
        <LogButtons onLog={onLogResult} />
      )}
    </div>
  )
}

export default function GameCard({ game, onLogResult, trackedSet, isPast }) {
  const hasEdgeAny = game.away.has_edge_any || game.home.has_edge_any

  const makeLogger = (side, opponentAbbrev) => onLogResult
    ? (result) => onLogResult({ game, side, opponentAbbrev, result })
    : null

  const awayTracked = trackedSet?.has(`${game.game_id}-${game.away.abbrev}`)
  const homeTracked = trackedSet?.has(`${game.game_id}-${game.home.abbrev}`)

  return (
    <div className={`game-card ${hasEdgeAny ? 'card-edge' : ''}`}>
      <div className="game-header">
        <div className="matchup">
          <span>{game.away.abbrev}</span>
          <span className="at">@</span>
          <span>{game.home.abbrev}</span>
          {hasEdgeAny && (
            <EdgeBadge
              edge={true}
              edgePct={game.away.has_edge_any ? game.away.windows?.season?.edge_pct : game.home.windows?.season?.edge_pct}
            />
          )}
        </div>
        <div className="game-meta">
          <span className="game-time">{game.game_time_ct}</span>
          {game.num_books > 0 && (
            <span className="books-count">{game.num_books} books</span>
          )}
        </div>
      </div>

      <div className="game-body">
        <TeamSide
          side={game.away}
          label="Away"
          onLogResult={isPast ? makeLogger(game.away, game.home.abbrev) : null}
          isTracked={awayTracked}
          isPast={isPast}
        />
        <div className="divider" />
        <TeamSide
          side={game.home}
          label="Home"
          onLogResult={isPast ? makeLogger(game.home, game.away.abbrev) : null}
          isTracked={homeTracked}
          isPast={isPast}
        />
      </div>
    </div>
  )
}

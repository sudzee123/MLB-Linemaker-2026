import { useState, useEffect, useMemo, useRef } from 'react'
import { usePlayoffs } from '../hooks/usePlayoffs'

const ALL_SERIES_KEYS = [
  'AL-WC-A', 'AL-WC-B', 'AL-DS-1', 'AL-DS-2', 'AL-CS',
  'NL-WC-A', 'NL-WC-B', 'NL-DS-1', 'NL-DS-2', 'NL-CS',
  'WS',
]

// ── Bracket derivation ────────────────────────────────────────────────────────
// Matchups follow the 12-team format. Teams for later rounds are derived from
// seeds + validated winner picks, so changing an upstream pick reflows downstream.

function validPick(key, seeds, series) {
  const teams = teamsForSeries(key, seeds, series)
  const p = series[key]?.pick || ''
  return p && teams.includes(p) ? p : ''
}

function teamsForSeries(key, seeds, series) {
  if (key === 'WS') {
    return [validPick('AL-CS', seeds, series), validPick('NL-CS', seeds, series)]
  }
  const lg = key.slice(0, 2)
  const s = seeds[lg] || {}
  const sub = key.slice(3)
  switch (sub) {
    case 'WC-A': return [s['3'] || '', s['6'] || '']
    case 'WC-B': return [s['4'] || '', s['5'] || '']
    case 'DS-1': return [s['1'] || '', validPick(`${lg}-WC-B`, seeds, series)]
    case 'DS-2': return [s['2'] || '', validPick(`${lg}-WC-A`, seeds, series)]
    case 'CS':   return [validPick(`${lg}-DS-1`, seeds, series), validPick(`${lg}-DS-2`, seeds, series)]
    default:     return ['', '']
  }
}

const SEED_LABELS = {
  'WC-A': '3 v 6', 'WC-B': '4 v 5',
  'DS-1': '1 v W(4/5)', 'DS-2': '2 v W(3/6)',
  'CS': 'Championship',
}

// ── Series card ───────────────────────────────────────────────────────────────

function SeriesCard({ seriesKey, title, sub, bestOf, seeds, series, setSeriesField, setLine, autoLines }) {
  const [a, b] = teamsForSeries(seriesKey, seeds, series)
  const pick = validPick(seriesKey, seeds, series)
  const lines = series[seriesKey]?.lines || {}
  const auto = autoLines[seriesKey]  // { away_fair_ml, home_fair_ml } — slot 0 = home

  const choose = (team) => {
    if (!team) return
    setSeriesField(seriesKey, 'pick', pick === team ? '' : team)
  }

  // Rendered inline (not as a nested component) so the inputs keep focus
  // across the re-renders that autosave triggers on every keystroke.
  const teamBlock = (team, idx) => {
    const l = lines[team] || {}
    const override = l.my || ''
    const autoMl = auto ? (idx === 0 ? auto.home_fair_ml : auto.away_fair_ml) : null
    const autoStr = autoMl != null ? String(autoMl) : ''
    const myValue = override !== '' ? override : autoStr
    const isOverride = override !== ''
    return (
      <div className="pb-teamblock" key={team || `empty-${idx}`}>
        <button
          className={`pb-team${pick === team && team ? ' pb-team-win' : ''}${!team ? ' pb-team-empty' : ''}`}
          onClick={() => choose(team)}
          disabled={!team}
        >
          <span className="pb-team-abbr">{team || '—'}</span>
          {pick === team && team && <span className="pb-check">✓</span>}
        </button>
        <div className="pb-lines">
          <div className="pb-my-wrap">
            <input
              className={`pb-line-input${!isOverride && autoStr ? ' pb-auto' : ''}`}
              type="text"
              value={myValue}
              onChange={e => setLine(seriesKey, team, 'my', e.target.value)}
              placeholder="My"
              title={isOverride ? 'Your line (overrides auto)' : 'Auto line — model season/team-ERA'}
              disabled={!team}
            />
            {isOverride && (
              <button
                className="pb-reset"
                title="Reset to auto line"
                onClick={() => setLine(seriesKey, team, 'my', '')}
              >↻</button>
            )}
          </div>
          <input
            className="pb-line-input"
            type="text"
            value={l.book || ''}
            onChange={e => setLine(seriesKey, team, 'book', e.target.value)}
            placeholder="Book"
            title="Book line for this team"
            disabled={!team}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="pb-series">
      <div className="pb-series-head">
        <span className="pb-series-title">{title}</span>
        <span className="pb-series-sub">{sub} · Bo{bestOf}</span>
      </div>
      {teamBlock(a, 0)}
      {teamBlock(b, 1)}
    </div>
  )
}

// ── Seed assignment ───────────────────────────────────────────────────────────

function SeedRow({ league, teams, seeds, setSeed }) {
  const used = (slot) =>
    Object.entries(seeds[league] || {})
      .filter(([k, v]) => k !== slot && v)
      .map(([, v]) => v)

  return (
    <div className="pb-seed-row">
      {['1', '2', '3', '4', '5', '6'].map(slot => {
        const usedElsewhere = used(slot)
        const opts = teams.filter(t => !usedElsewhere.includes(t.abbrev))
        return (
          <div key={slot} className="pb-seed">
            <span className="pb-seed-num">
              {slot}{(slot === '1' || slot === '2') ? ' (bye)' : ''}
            </span>
            <select
              className="pb-seed-select"
              value={seeds[league]?.[slot] || ''}
              onChange={e => setSeed(league, slot, e.target.value)}
            >
              <option value="">—</option>
              {opts.map(t => (
                <option key={t.abbrev} value={t.abbrev}>{t.name}</option>
              ))}
            </select>
          </div>
        )
      })}
    </div>
  )
}

// ── League block ──────────────────────────────────────────────────────────────

function LeagueBlock({ league, teams, seeds, setSeed, series, setSeriesField, setLine, autoLines }) {
  const common = { seeds, series, setSeriesField, setLine, autoLines }
  return (
    <div className="pb-league">
      <div className="pb-league-label">{league === 'AL' ? 'American League' : 'National League'}</div>
      <SeedRow league={league} teams={teams} seeds={seeds} setSeed={setSeed} />
      <div className="pb-rounds">
        <div className="pb-round">
          <div className="pb-round-label">Wild Card</div>
          <SeriesCard seriesKey={`${league}-WC-A`} title="WC" sub={SEED_LABELS['WC-A']} bestOf={3} {...common} />
          <SeriesCard seriesKey={`${league}-WC-B`} title="WC" sub={SEED_LABELS['WC-B']} bestOf={3} {...common} />
        </div>
        <div className="pb-round">
          <div className="pb-round-label">Division</div>
          <SeriesCard seriesKey={`${league}-DS-1`} title="DS" sub={SEED_LABELS['DS-1']} bestOf={5} {...common} />
          <SeriesCard seriesKey={`${league}-DS-2`} title="DS" sub={SEED_LABELS['DS-2']} bestOf={5} {...common} />
        </div>
        <div className="pb-round">
          <div className="pb-round-label">Championship</div>
          <SeriesCard seriesKey={`${league}-CS`} title="CS" sub={SEED_LABELS['CS']} bestOf={7} {...common} />
        </div>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function PlayoffBracket() {
  const { teams, seeds, setSeed, series, setSeriesField, setLine, saveStatus } = usePlayoffs()
  const [autoLines, setAutoLines] = useState({})
  const cacheRef = useRef({})  // `${away_id}-${home_id}` → { away_fair_ml, home_fair_ml }

  const idByAbbr = useMemo(
    () => Object.fromEntries(teams.map(t => [t.abbrev, t.team_id])),
    [teams],
  )

  // Every fully-populated matchup (slot 0 = home). Recomputed from seeds+picks.
  const matchups = useMemo(() => {
    const out = []
    for (const key of ALL_SERIES_KEYS) {
      const [home, away] = teamsForSeries(key, seeds, series)
      if (home && away && idByAbbr[home] != null && idByAbbr[away] != null) {
        out.push({ key, home, away, home_id: idByAbbr[home], away_id: idByAbbr[away] })
      }
    }
    return out
  }, [seeds, series, idByAbbr])

  // Signature changes only when the matchup composition changes (not on line typing).
  const sig = useMemo(
    () => matchups.map(m => `${m.key}:${m.away_id}>${m.home_id}`).join('|'),
    [matchups],
  )
  const matchupsRef = useRef(matchups)
  matchupsRef.current = matchups

  useEffect(() => {
    const mm = matchupsRef.current
    // Apply anything already cached immediately.
    const applied = {}
    for (const m of mm) {
      const c = cacheRef.current[`${m.away_id}-${m.home_id}`]
      if (c) applied[m.key] = c
    }
    if (Object.keys(applied).length) setAutoLines(prev => ({ ...prev, ...applied }))

    const need = mm.filter(m => !cacheRef.current[`${m.away_id}-${m.home_id}`])
    if (!need.length) return

    const t = setTimeout(async () => {
      try {
        const res = await fetch('/api/playoffs/lines', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            matchups: need.map(m => ({ key: m.key, away_id: m.away_id, home_id: m.home_id })),
          }),
        })
        if (!res.ok) return
        const data = await res.json()
        const add = {}
        for (const m of need) {
          if (data[m.key]) {
            cacheRef.current[`${m.away_id}-${m.home_id}`] = data[m.key]
            add[m.key] = data[m.key]
          }
        }
        if (Object.keys(add).length) setAutoLines(prev => ({ ...prev, ...add }))
      } catch { /* ignore */ }
    }, 500)
    return () => clearTimeout(t)
  }, [sig])

  return (
    <div className="playoff-bracket">
      <div className="pb-header">
        <p className="pb-intro">
          Assign teams to seed slots — each matchup auto-calculates a season fair line
          (team overall ERA for both sides). Edit any line to override; ↻ resets to auto.
          Pick winners to advance the bracket. Everything saves automatically.
        </p>
        <span className={`pb-save pb-save-${saveStatus}`}>
          {saveStatus === 'saving' ? 'Saving…' : saveStatus === 'saved' ? 'Saved' : ''}
        </span>
      </div>

      <LeagueBlock league="AL" teams={teams} seeds={seeds} setSeed={setSeed} series={series} setSeriesField={setSeriesField} setLine={setLine} autoLines={autoLines} />
      <LeagueBlock league="NL" teams={teams} seeds={seeds} setSeed={setSeed} series={series} setSeriesField={setSeriesField} setLine={setLine} autoLines={autoLines} />

      <div className="pb-ws">
        <div className="pb-round-label">World Series</div>
        <SeriesCard seriesKey="WS" title="WS" sub="AL v NL" bestOf={7} seeds={seeds} series={series} setSeriesField={setSeriesField} setLine={setLine} autoLines={autoLines} />
      </div>
    </div>
  )
}

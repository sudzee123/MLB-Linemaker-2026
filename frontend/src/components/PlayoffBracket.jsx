import { usePlayoffs } from '../hooks/usePlayoffs'

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

function SeriesCard({ seriesKey, title, sub, bestOf, seeds, series, setSeriesField }) {
  const [a, b] = teamsForSeries(seriesKey, seeds, series)
  const pick = validPick(seriesKey, seeds, series)
  const data = series[seriesKey] || {}

  const choose = (team) => {
    if (!team) return
    setSeriesField(seriesKey, 'pick', pick === team ? '' : team)
  }

  const TeamRow = ({ team }) => (
    <button
      className={`pb-team${pick === team && team ? ' pb-team-win' : ''}${!team ? ' pb-team-empty' : ''}`}
      onClick={() => choose(team)}
      disabled={!team}
    >
      <span className="pb-team-abbr">{team || '—'}</span>
      {pick === team && team && <span className="pb-check">✓</span>}
    </button>
  )

  return (
    <div className="pb-series">
      <div className="pb-series-head">
        <span className="pb-series-title">{title}</span>
        <span className="pb-series-sub">{sub} · Bo{bestOf}</span>
      </div>
      <TeamRow team={a} />
      <TeamRow team={b} />
      <div className="pb-lines">
        <input
          className="pb-line-input"
          type="text"
          value={data.my_line || ''}
          onChange={e => setSeriesField(seriesKey, 'my_line', e.target.value)}
          placeholder="My line"
        />
        <input
          className="pb-line-input"
          type="text"
          value={data.book_line || ''}
          onChange={e => setSeriesField(seriesKey, 'book_line', e.target.value)}
          placeholder="Book line"
        />
      </div>
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

function LeagueBlock({ league, teams, seeds, setSeed, series, setSeriesField }) {
  const common = { seeds, series, setSeriesField }
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
  const { teams, seeds, setSeed, series, setSeriesField, saveStatus } = usePlayoffs()

  return (
    <div className="playoff-bracket">
      <div className="pb-header">
        <p className="pb-intro">
          Assign teams to seed slots, enter your line and the book's line per series,
          and pick winners — picks auto-advance to the next round. Everything saves automatically.
        </p>
        <span className={`pb-save pb-save-${saveStatus}`}>
          {saveStatus === 'saving' ? 'Saving…' : saveStatus === 'saved' ? 'Saved' : ''}
        </span>
      </div>

      <LeagueBlock league="AL" teams={teams} seeds={seeds} setSeed={setSeed} series={series} setSeriesField={setSeriesField} />
      <LeagueBlock league="NL" teams={teams} seeds={seeds} setSeed={setSeed} series={series} setSeriesField={setSeriesField} />

      <div className="pb-ws">
        <div className="pb-round-label">World Series</div>
        <SeriesCard seriesKey="WS" title="WS" sub="AL v NL" bestOf={7} seeds={seeds} series={series} setSeriesField={setSeriesField} />
      </div>
    </div>
  )
}

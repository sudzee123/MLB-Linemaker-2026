import { useState, useMemo } from 'react'
import { useGames } from './hooks/useGames'
import { useResults } from './hooks/useResults'
import { usePlays } from './hooks/usePlays'
import DatePicker from './components/DatePicker'
import GameCard from './components/GameCard'
import ResultsTracker from './components/ResultsTracker'
import TrackedPlays from './components/TrackedPlays'
import './index.css'

export default function App() {
  const [activeTab, setActiveTab] = useState('games')

  const {
    date, games, loading, error, lastUpdated,
    edgeCount, minGamesPlayed,
    prevDay, nextDay, refresh,
  } = useGames()

  const {
    summary, conflictBreakdown, loading: resultsLoading, logResult, updateResult, deleteResult, refresh: refreshResults,
    window: resultWindow, setWindow: setResultWindow,
    startDate, setStartDate, endDate, setEndDate,
    minEdge, setMinEdge, maxEdge, setMaxEdge, mlMin, setMlMin, mlMax, setMlMax,
    team, setTeam,
    prevLossFilter, setPrevLossFilter,
  } = useResults()

  const { grouped, loading: playsLoading, settleGroup, removeGroup } = usePlays()

  // Set of "game_id-team_abbrev" strings for auto-tracked badge
  const trackedSet = useMemo(() => {
    const s = new Set()
    grouped.forEach(p => s.add(`${p.game_id}-${p.team_abbrev}`))
    return s
  }, [grouped])

  const isPast = date < new Date().toISOString().slice(0, 10)

  // edgeCount using has_edge_any for the 3-window model
  const edgeCountAny = games.filter(g => g.away?.has_edge_any || g.home?.has_edge_any).length

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>MLB <span>LINEMAKER</span></h1>
          <p className="subtitle">Run-Based Pythagorean · SP+BP Blend · Season / L30 / L21 Windows</p>
        </div>
        <div className="header-right">
          {lastUpdated && <span className="updated">Updated {lastUpdated}</span>}
        </div>
      </header>

      {/* Tab bar */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === 'games' ? 'active' : ''}`}
          onClick={() => setActiveTab('games')}
        >
          Games
          {edgeCountAny > 0 && <span className="tab-badge">{edgeCountAny} edge{edgeCountAny !== 1 ? 's' : ''}</span>}
        </button>
        <button
          className={`tab-btn ${activeTab === 'plays' ? 'active' : ''}`}
          onClick={() => setActiveTab('plays')}
        >
          Plays
          {grouped.length > 0 && (
            <span className="tab-badge">{grouped.length} pending</span>
          )}
        </button>
        <button
          className={`tab-btn ${activeTab === 'results' ? 'active' : ''}`}
          onClick={() => setActiveTab('results')}
        >
          Results
          {summary?.total_plays > 0 && (
            <span className={`tab-badge ${summary.net_units >= 0 ? 'badge-green' : 'badge-red'}`}>
              {summary.net_units >= 0 ? '+' : ''}{summary.net_units}u
            </span>
          )}
        </button>
      </div>

      <main className="main">
        {/* ── Games tab ── */}
        {activeTab === 'games' && (
          <>
            <DatePicker
              date={date}
              onPrev={prevDay}
              onNext={nextDay}
              onRefresh={refresh}
              loading={loading}
            />

            {minGamesPlayed < 10 && games.length > 0 && (
              <div className="warning-bar">
                Small sample: ~{minGamesPlayed} games played this season.
                Model accuracy improves significantly after 30+ games.
              </div>
            )}

            {!loading && games.length > 0 && (
              <div className="summary-bar">
                <div className="stat-pill">
                  <span className="pill-label">Games</span>
                  <span className="pill-value">{games.length}</span>
                </div>
                <div className="stat-pill">
                  <span className="pill-label">Edges</span>
                  <span className="pill-value green">{edgeCountAny}</span>
                </div>
                <div className="stat-pill">
                  <span className="pill-label">Books</span>
                  <span className="pill-value">{Math.max(...games.map(g => g.num_books), 0)}</span>
                </div>
              </div>
            )}

            {loading && <div className="state-msg">Loading…</div>}
            {error && <div className="state-msg error">Error: {error}</div>}
            {!loading && !error && games.length === 0 && (
              <div className="state-msg">No games scheduled for this date.</div>
            )}

            <div className="games-list">
              {games.map(g => (
                <GameCard
                  key={g.game_id}
                  game={g}
                  onLogResult={logResult}
                  trackedSet={trackedSet}
                  isPast={isPast}
                />
              ))}
            </div>
          </>
        )}

        {/* ── Plays tab ── */}
        {activeTab === 'plays' && (
          <TrackedPlays
            grouped={grouped}
            loading={playsLoading}
            onSettle={settleGroup}
            onRemove={removeGroup}
          />
        )}

        {/* ── Results tab ── */}
        {activeTab === 'results' && (
          <ResultsTracker
            summary={summary}
            conflictBreakdown={conflictBreakdown}
            loading={resultsLoading}
            onUpdate={updateResult}
            onDelete={deleteResult}
            onRefresh={refreshResults}
            window={resultWindow}
            onWindowChange={setResultWindow}
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            minEdge={minEdge}
            onMinEdgeChange={setMinEdge}
            maxEdge={maxEdge}
            onMaxEdgeChange={setMaxEdge}
            mlMin={mlMin}
            onMlMinChange={setMlMin}
            mlMax={mlMax}
            onMlMaxChange={setMlMax}
            team={team}
            onTeamChange={setTeam}
            prevLossFilter={prevLossFilter}
            onPrevLossFilterChange={setPrevLossFilter}
          />
        )}
      </main>

      <footer className="footer">
        MLB Stats API · The Odds API · Pythagorean Win% · SP+BP Blended RA · Season / L30 / L21
      </footer>
    </div>
  )
}

import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export function useResults() {
  const [summary, setSummary] = useState(null)
  const [conflictBreakdown, setConflictBreakdown] = useState(null)
  const [clvSummary, setClvSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [window, setWindow] = useState('season')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [minEdge, setMinEdge] = useState('')
  const [maxEdge, setMaxEdge] = useState('10')
  const [mlMin, setMlMin] = useState('-109')
  const [mlMax, setMlMax] = useState('')
  const [jspMin, setJspMin] = useState('')
  const [jspMax, setJspMax] = useState('')
  const [team, setTeam] = useState('')
  const [prevLossFilter, setPrevLossFilter] = useState(false)
  const [phase, setPhase] = useState('all')        // all | reg | playoffs
  const [homeAway, setHomeAway] = useState('both')  // both | home | away
  const [gameNumMin, setGameNumMin] = useState('')
  const [gameNumMax, setGameNumMax] = useState('')
  const [restMin, setRestMin] = useState('')
  const [restMax, setRestMax] = useState('')
  const [mode, setMode] = useState('on') // on | against  (Bet Side)

  const fetchSummary = useCallback(async () => {
    setLoading(true)
    try {
      if (window === 'conflicts') {
        const res = await fetch(`${API}/results/conflict-breakdown`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setConflictBreakdown(await res.json())
        setSummary(null)
        setClvSummary(null)
      } else {
        const params = new URLSearchParams()
        params.set('window', window)
        if (startDate) params.set('start_date', startDate)
        if (endDate) params.set('end_date', endDate)
        if (minEdge !== '') params.set('min_edge', minEdge)
        if (maxEdge !== '') params.set('max_edge', maxEdge)
        if (mlMin !== '') params.set('ml_min', mlMin)
        if (mlMax !== '') params.set('ml_max', mlMax)
        if (jspMin !== '') params.set('jsp_min', jspMin)
        if (jspMax !== '') params.set('jsp_max', jspMax)
        if (team !== '') params.set('team', team)
        if (prevLossFilter) params.set('prev_loss_filter', 'true')
        if (phase !== 'all') params.set('phase', phase)
        if (homeAway !== 'both') params.set('side_filter', homeAway)
        if (gameNumMin !== '') params.set('game_num_min', gameNumMin)
        if (gameNumMax !== '') params.set('game_num_max', gameNumMax)
        if (restMin !== '') params.set('rest_min', restMin)
        if (restMax !== '') params.set('rest_max', restMax)
        if (mode !== 'on') params.set('mode', mode)

        // CLV shares the same filters (minus jsp/prev-loss/mode — CLV is on-side).
        const cp = new URLSearchParams(params)
        cp.delete('jsp_min'); cp.delete('jsp_max')
        cp.delete('prev_loss_filter'); cp.delete('mode')

        const [res, clvRes] = await Promise.all([
          fetch(`${API}/results/summary?${params.toString()}`),
          fetch(`${API}/clv/summary?${cp.toString()}`),
        ])
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setSummary(await res.json())
        setClvSummary(clvRes.ok ? await clvRes.json() : null)
        setConflictBreakdown(null)
      }
    } catch (e) {
      console.error('Failed to fetch results summary:', e)
    } finally {
      setLoading(false)
    }
  }, [window, startDate, endDate, minEdge, maxEdge, mlMin, mlMax, jspMin, jspMax, team, prevLossFilter, phase, homeAway, gameNumMin, gameNumMax, restMin, restMax, mode])

  useEffect(() => { fetchSummary() }, [fetchSummary])

  const logResult = useCallback(async ({ game, side, opponentAbbrev, result }) => {
    const res = await fetch(`${API}/results`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        game_date: game.date,
        game_id: game.game_id,
        team_abbrev: side.abbrev,
        opponent_abbrev: opponentAbbrev,
        book_ml: side.book_ml,
        edge_pct: side.edge_pct,
        result,
        window: 'season',
        game_type: game.game_type || 'R',
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await fetchSummary()
  }, [fetchSummary])

  const updateResult = useCallback(async (id, { result, book_ml, edge_pct }) => {
    const res = await fetch(`${API}/results/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result, book_ml, edge_pct }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await fetchSummary()
  }, [fetchSummary])

  const deleteResult = useCallback(async (id) => {
    await fetch(`${API}/results/${id}`, { method: 'DELETE' })
    await fetchSummary()
  }, [fetchSummary])

  return {
    summary, conflictBreakdown, clvSummary, loading, logResult, updateResult, deleteResult, refresh: fetchSummary,
    window, setWindow,
    startDate, setStartDate, endDate, setEndDate,
    minEdge, setMinEdge, maxEdge, setMaxEdge, mlMin, setMlMin, mlMax, setMlMax,
    jspMin, setJspMin, jspMax, setJspMax,
    team, setTeam,
    prevLossFilter, setPrevLossFilter,
    phase, setPhase,
    homeAway, setHomeAway,
    gameNumMin, setGameNumMin, gameNumMax, setGameNumMax,
    restMin, setRestMin, restMax, setRestMax,
    mode, setMode,
  }
}

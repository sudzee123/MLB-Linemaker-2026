import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export function useResults() {
  const [summary, setSummary] = useState(null)
  const [conflictBreakdown, setConflictBreakdown] = useState(null)
  const [loading, setLoading] = useState(true)
  const [window, setWindow] = useState('season')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [minEdge, setMinEdge] = useState('')
  const [maxEdge, setMaxEdge] = useState('')
  const [mlMin, setMlMin] = useState('')
  const [mlMax, setMlMax] = useState('')
  const [team, setTeam] = useState('')
  const [prevLossFilter, setPrevLossFilter] = useState(false)

  const fetchSummary = useCallback(async () => {
    setLoading(true)
    try {
      if (window === 'conflicts') {
        const res = await fetch(`${API}/results/conflict-breakdown`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setConflictBreakdown(await res.json())
        setSummary(null)
      } else {
        const params = new URLSearchParams()
        params.set('window', window)
        if (startDate) params.set('start_date', startDate)
        if (endDate) params.set('end_date', endDate)
        if (minEdge !== '') params.set('min_edge', minEdge)
        if (maxEdge !== '') params.set('max_edge', maxEdge)
        if (mlMin !== '') params.set('ml_min', mlMin)
        if (mlMax !== '') params.set('ml_max', mlMax)
        if (team !== '') params.set('team', team)
        if (prevLossFilter) params.set('prev_loss_filter', 'true')
        const res = await fetch(`${API}/results/summary?${params.toString()}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setSummary(await res.json())
        setConflictBreakdown(null)
      }
    } catch (e) {
      console.error('Failed to fetch results summary:', e)
    } finally {
      setLoading(false)
    }
  }, [window, startDate, endDate, minEdge, maxEdge, mlMin, mlMax, team, prevLossFilter])

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
    summary, conflictBreakdown, loading, logResult, updateResult, deleteResult, refresh: fetchSummary,
    window, setWindow,
    startDate, setStartDate, endDate, setEndDate,
    minEdge, setMinEdge, maxEdge, setMaxEdge, mlMin, setMlMin, mlMax, setMlMax,
    team, setTeam,
    prevLossFilter, setPrevLossFilter,
  }
}

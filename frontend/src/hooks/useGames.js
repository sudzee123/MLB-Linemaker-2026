import { useState, useEffect, useCallback, useRef } from 'react'

const API = '/api'

function toDateStr(d) {
  return d.toISOString().slice(0, 10)
}

export function useGames() {
  const [date, setDate] = useState(toDateStr(new Date()))
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  // Track the active fetch so a stale response never overwrites a newer one
  const abortRef = useRef(null)

  const fetchGames = useCallback(async (targetDate, forceRefresh = false) => {
    // Cancel any in-flight request for a previous date
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)

    try {
      const url = forceRefresh
        ? `${API}/refresh?date=${targetDate}`
        : `${API}/games?date=${targetDate}`

      const res = await fetch(url, { signal: controller.signal })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()

      // Only update state if this request wasn't superseded
      if (!controller.signal.aborted) {
        setGames(Array.isArray(data) ? data : data.games || [])
        setLastUpdated(new Date().toLocaleTimeString())
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        setError(e.message)
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    fetchGames(date)
    return () => {
      if (abortRef.current) abortRef.current.abort()
    }
  }, [date, fetchGames])

  function prevDay() {
    const d = new Date(date + 'T12:00:00')
    d.setDate(d.getDate() - 1)
    setDate(toDateStr(d))
  }

  function nextDay() {
    const d = new Date(date + 'T12:00:00')
    d.setDate(d.getDate() + 1)
    setDate(toDateStr(d))
  }

  function refresh() {
    fetchGames(date, true)
  }

  const edgeCount = games.filter(g => g.away?.has_edge || g.home?.has_edge).length
  const minGamesPlayed = games.length
    ? Math.min(...games.map(g => Math.min(g.away?.games_played ?? 0, g.home?.games_played ?? 0)))
    : 0

  return {
    date, games, loading, error, lastUpdated,
    edgeCount, minGamesPlayed,
    prevDay, nextDay, refresh,
  }
}

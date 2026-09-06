import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export function usePlays() {
  const [plays, setPlays] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchPlays = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/plays`)
      if (res.ok) setPlays(await res.json())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchPlays() }, [fetchPlays])

  async function settleGroup(game_id, team_abbrev, result) {
    await fetch(`${API}/plays/settle-group`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game_id, team_abbrev, result }),
    })
    await fetchPlays()
  }

  async function removeGroup(game_id, team_abbrev) {
    await fetch(`${API}/plays/group?game_id=${game_id}&team_abbrev=${encodeURIComponent(team_abbrev)}`, {
      method: 'DELETE',
    })
    await fetchPlays()
  }

  // Derive grouped plays: one entry per game_id+team_abbrev (season window preferred for display)
  const grouped = []
  const seen = new Set()
  for (const p of plays) {
    const key = `${p.game_id}-${p.team_abbrev}`
    if (!seen.has(key)) {
      seen.add(key)
      // Find season window entry for display; fall back to first entry
      const seasonEntry = plays.find(x => x.game_id === p.game_id && x.team_abbrev === p.team_abbrev && x.window === 'season') || p
      // Collect all window edge_pcts for this group
      const windowEdges = {}
      plays.filter(x => x.game_id === p.game_id && x.team_abbrev === p.team_abbrev)
           .forEach(x => { windowEdges[x.window] = x.edge_pct })
      grouped.push({ ...seasonEntry, windowEdges })
    }
  }

  return { plays, grouped, loading, settleGroup, removeGroup }
}

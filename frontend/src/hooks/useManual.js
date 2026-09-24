import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export function useManual() {
  const [teams, setTeams] = useState([])
  const [awayTeam, setAwayTeam] = useState('')
  const [homeTeam, setHomeTeam] = useState('')
  const [awayPitchers, setAwayPitchers] = useState([])
  const [homePitchers, setHomePitchers] = useState([])
  const [awayPitcher, setAwayPitcher] = useState('')
  const [homePitcher, setHomePitcher] = useState('')
  const [awayMl, setAwayMl] = useState('')
  const [homeMl, setHomeMl] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Load team list once
  useEffect(() => {
    fetch(`${API}/teams`)
      .then(r => r.json())
      .then(setTeams)
      .catch(e => console.error('Failed to load teams:', e))
  }, [])

  // Fetch pitchers whenever a team is chosen
  const loadPitchers = useCallback(async (teamId, setter) => {
    if (!teamId) { setter([]); return }
    try {
      const res = await fetch(`${API}/teams/${teamId}/pitchers`)
      setter(res.ok ? await res.json() : [])
    } catch {
      setter([])
    }
  }, [])

  useEffect(() => {
    setAwayPitcher('')
    loadPitchers(awayTeam, setAwayPitchers)
  }, [awayTeam, loadPitchers])

  useEffect(() => {
    setHomePitcher('')
    loadPitchers(homeTeam, setHomePitchers)
  }, [homeTeam, loadPitchers])

  const generate = useCallback(async () => {
    if (!awayTeam || !homeTeam) {
      setError('Select both teams first.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const awayOverall = awayPitcher === 'TEAM'
      const homeOverall = homePitcher === 'TEAM'
      const awayP = awayPitchers.find(p => String(p.id) === String(awayPitcher))
      const homeP = homePitchers.find(p => String(p.id) === String(homePitcher))
      const body = {
        away_team_id: Number(awayTeam),
        home_team_id: Number(homeTeam),
        away_pitcher_id: (awayPitcher && !awayOverall) ? Number(awayPitcher) : null,
        home_pitcher_id: (homePitcher && !homeOverall) ? Number(homePitcher) : null,
        away_pitcher_name: awayP?.name || 'TBD',
        home_pitcher_name: homeP?.name || 'TBD',
        away_team_overall: awayOverall,
        home_team_overall: homeOverall,
        away_ml: awayMl !== '' ? Number(awayMl) : null,
        home_ml: homeMl !== '' ? Number(homeMl) : null,
      }
      const res = await fetch(`${API}/manual/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
    } catch (e) {
      setError(e.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }, [awayTeam, homeTeam, awayPitcher, homePitcher, awayPitchers, homePitchers, awayMl, homeMl])

  return {
    teams,
    awayTeam, setAwayTeam, homeTeam, setHomeTeam,
    awayPitchers, homePitchers,
    awayPitcher, setAwayPitcher, homePitcher, setHomePitcher,
    awayMl, setAwayMl, homeMl, setHomeMl,
    result, loading, error, generate,
  }
}

import { useState, useEffect, useRef, useCallback } from 'react'

const API = '/api'

export function usePlayoffs() {
  const [teams, setTeams] = useState([])
  const [seeds, setSeeds] = useState({ AL: {}, NL: {} })
  const [series, setSeries] = useState({})
  const [saveStatus, setSaveStatus] = useState('idle') // idle | saving | saved
  const loadedRef = useRef(false)
  const timerRef = useRef(null)

  // Initial load: teams + saved bracket
  useEffect(() => {
    fetch(`${API}/teams`).then(r => r.json()).then(setTeams).catch(() => {})
    fetch(`${API}/playoffs`)
      .then(r => r.json())
      .then(b => {
        setSeeds(b.seeds || { AL: {}, NL: {} })
        setSeries(b.series || {})
      })
      .catch(() => {})
      .finally(() => { loadedRef.current = true })
  }, [])

  // Debounced autosave on any change (after initial load)
  useEffect(() => {
    if (!loadedRef.current) return
    setSaveStatus('saving')
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      try {
        await fetch(`${API}/playoffs`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ payload: { seeds, series } }),
        })
        setSaveStatus('saved')
      } catch {
        setSaveStatus('idle')
      }
    }, 700)
    return () => clearTimeout(timerRef.current)
  }, [seeds, series])

  const setSeed = useCallback((league, slot, abbrev) => {
    setSeeds(prev => ({ ...prev, [league]: { ...prev[league], [slot]: abbrev } }))
  }, [])

  const setSeriesField = useCallback((key, field, value) => {
    setSeries(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [field]: value } }))
  }, [])

  return { teams, seeds, setSeed, series, setSeriesField, saveStatus }
}

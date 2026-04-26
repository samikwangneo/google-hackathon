import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'

import { startPomodoro, stopPomodoro } from '../lib/api'
import { useTerpPetStore } from '../store'

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
}

function secondsUntil(endIso: string | null, nowMs = Date.now()): number {
  if (!endIso) return 0
  return Math.max(0, Math.ceil((new Date(endIso).getTime() - nowMs) / 1000))
}

export function PomodoroPanel(): React.JSX.Element {
  const pomodoro = useTerpPetStore((state) => state.pomodoro)
  const setPomodoro = useTerpPetStore((state) => state.setPomodoro)
  const [minutes, setMinutes] = useState(pomodoro.minutes)
  const [now, setNow] = useState(() => Date.now())
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(tick)
  }, [])

  const remaining = useMemo(() => secondsUntil(pomodoro.ends_at, now), [now, pomodoro.ends_at])

  const progress = useMemo(() => {
    if (!pomodoro.running) return 0
    const total = Math.max(1, pomodoro.minutes * 60)
    return Math.min(100, Math.max(0, ((total - remaining) / total) * 100))
  }, [pomodoro.minutes, pomodoro.running, remaining])

  const handleStart = async (): Promise<void> => {
    setPending(true)
    setError(null)
    try {
      const response = await startPomodoro(minutes)
      setPomodoro({ running: true, ends_at: response.ends_at, minutes })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start Pomodoro')
    } finally {
      setPending(false)
    }
  }

  const handleStop = async (): Promise<void> => {
    setPending(true)
    setError(null)
    try {
      await stopPomodoro()
      setPomodoro({ running: false, ends_at: null, minutes })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not stop Pomodoro')
    } finally {
      setPending(false)
    }
  }

  return (
    <motion.section
      className="panel pomodoro-panel"
      initial={{ opacity: 0, y: 18, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 18, scale: 0.96 }}
    >
      <div className="panel__eyebrow">Focus Ritual</div>
      <h2>{pomodoro.running ? 'Session running' : 'Start a Pomodoro'}</h2>
      <div className="pomodoro-panel__timer">
        {formatTime(pomodoro.running ? remaining : minutes * 60)}
      </div>
      <div className="pomodoro-panel__track" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
      <label className="field">
        Minutes
        <input
          type="number"
          min="1"
          max="180"
          value={minutes}
          disabled={pomodoro.running || pending}
          onChange={(event) => setMinutes(Number(event.target.value))}
        />
      </label>
      <div className="panel__actions">
        {pomodoro.running ? (
          <button
            type="button"
            className="button button--ghost"
            disabled={pending}
            onClick={handleStop}
          >
            Stop
          </button>
        ) : (
          <button type="button" className="button" disabled={pending} onClick={handleStart}>
            Start focus
          </button>
        )}
      </div>
      {error && <p className="panel__error">{error}</p>}
    </motion.section>
  )
}

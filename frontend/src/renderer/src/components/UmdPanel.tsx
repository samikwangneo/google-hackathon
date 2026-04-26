import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

import { getDining, getStudySpots } from '../lib/api'
import type { DiningRec, StudySpot } from '../types/contracts'

export function UmdPanel(): React.JSX.Element {
  const [studySpots, setStudySpots] = useState<StudySpot[]>([])
  const [dining, setDining] = useState<DiningRec[]>([])
  const [pending, setPending] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadUmdData(): Promise<void> {
      try {
        const [spots, meals] = await Promise.all([getStudySpots(), getDining()])
        if (cancelled) return
        setStudySpots(spots)
        setDining(meals)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load UMD picks')
      } finally {
        if (!cancelled) setPending(false)
      }
    }

    void loadUmdData()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <motion.section className="panel umd-panel">
      <div className="panel__eyebrow">Campus picks</div>
      <h2>UMD nearby</h2>
      {pending && <p>Loading campus recs...</p>}
      {!pending && error && <p className="panel__error">{error}</p>}
      {!pending && !error && (
        <div className="umd-panel__content">
          <section className="umd-panel__section">
            <h3>Study spots</h3>
            <div className="umd-panel__list">
              {studySpots.map((spot) => (
                <article className="umd-card" key={spot.name}>
                  <strong>{spot.name}</strong>
                  <span>{spot.vibe}</span>
                  <small>{spot.busyness} traffic</small>
                </article>
              ))}
            </div>
          </section>
          <section className="umd-panel__section">
            <h3>Dining</h3>
            <div className="umd-panel__list">
              {dining.map((rec) => (
                <article className="umd-card umd-card--dining" key={`${rec.hall}-${rec.recommendation}`}>
                  <strong>{rec.hall}</strong>
                  <span>{rec.recommendation}</span>
                  <small>{rec.vibe}</small>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </motion.section>
  )
}

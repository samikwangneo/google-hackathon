import { motion } from 'framer-motion'

import { useTerpPetStore } from '../store'

const thresholds = [0, 100, 250, 500, 1000, 2000, 4000]

function levelProgress(level: number, xp: number): number {
  const current = thresholds[level - 1] ?? thresholds[thresholds.length - 1]
  const next = thresholds[level] ?? current + 500
  return Math.min(100, Math.max(0, ((xp - current) / (next - current)) * 100))
}

export function StatsPanel(): React.JSX.Element {
  const xp = useTerpPetStore((state) => state.xp)
  const level = useTerpPetStore((state) => state.level)
  const focusSeconds = useTerpPetStore((state) => state.focus_seconds)
  const streak = useTerpPetStore((state) => state.distraction_streak)
  const activeWindow = useTerpPetStore((state) => state.active_window)
  const xpFlash = useTerpPetStore((state) => state.xpFlash)
  const nextThreshold = thresholds[level] ?? xp + 500
  const focusMinutes = Math.floor(focusSeconds / 60)

  return (
    <motion.section
      className="panel stats-panel"
      initial={{ opacity: 0, y: 18, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 18, scale: 0.96 }}
    >
      <div className="panel__eyebrow">Today</div>
      <h2>Level {level} TerpPet</h2>
      <div className="stats-panel__xp">
        <span>{xp} XP</span>
        <small>
          {xpFlash ? `+${xpFlash} XP` : `${Math.max(0, nextThreshold - xp)} XP to next`}
        </small>
      </div>
      <div
        className="stats-panel__bar"
        aria-label={`XP progress ${Math.round(levelProgress(level, xp))}%`}
      >
        <span style={{ width: `${levelProgress(level, xp)}%` }} />
      </div>
      <div className="stats-panel__grid">
        <div>
          <strong>{focusMinutes}</strong>
          <small>focus min</small>
        </div>
        <div>
          <strong>{streak}</strong>
          <small>distractions</small>
        </div>
      </div>
      <p className="stats-panel__window">{activeWindow ?? 'Waiting for active-window signal'}</p>
    </motion.section>
  )
}

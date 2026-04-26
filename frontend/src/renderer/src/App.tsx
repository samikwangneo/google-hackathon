import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import { BrainPanel } from './components/BrainPanel'
import { EvolutionEffect } from './components/EvolutionEffect'
import { OrbMenu } from './components/OrbMenu'
import { Pet } from './components/Pet'
import { PomodoroPanel } from './components/PomodoroPanel'
import { StatsPanel } from './components/StatsPanel'
import { UmdPanel } from './components/UmdPanel'
import { connectBehaviorSocket } from './lib/ws'
import { useTerpPetStore } from './store'

const upcomingAssignments = [
  {
    weekday: 'Thu',
    day: '16',
    course: 'ECON315',
    title: 'Group meeting',
    time: '11:59 PM',
    icon: 'memo'
  },
  {
    weekday: 'Mon',
    day: '27',
    course: 'ECON418A',
    title: 'Problem Set 3',
    time: '5:00 PM',
    icon: 'memo'
  },
  {
    weekday: 'Tue',
    day: '28',
    course: 'ECON315',
    title: 'Quiz 8',
    time: '2:00 PM',
    icon: 'rocket'
  }
]

function App(): React.JSX.Element {
  const activePanel = useTerpPetStore((state) => state.activePanel)
  const closePanel = useTerpPetStore((state) => state.closePanel)
  const applyFrame = useTerpPetStore((state) => state.applyFrame)
  const setConnectionStatus = useTerpPetStore((state) => state.setConnectionStatus)
  const connectionStatus = useTerpPetStore((state) => state.connectionStatus)
  const lastFrameAt = useTerpPetStore((state) => state.lastFrameAt)
  const [checkedAssignments, setCheckedAssignments] = useState<Set<string>>(() => new Set())

  const toggleAssignment = (key: string): void => {
    setCheckedAssignments((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  useEffect(() => {
    const socket = connectBehaviorSocket(applyFrame, setConnectionStatus)
    return socket.close
  }, [applyFrame, setConnectionStatus])

  useEffect(() => {
    // The Electron window spans the full screen width and is transparent, so
    // it would otherwise eat clicks meant for whatever the user has under it
    // (terminal, browser, etc.). Pass-through is on by default; we only flip
    // it off when the cursor is over actual interactive UI.
    const INTERACTIVE_SELECTOR = '.pet, .panel, .panel-wrap, .orb-menu, button, input'
    let passthrough = true

    const send = (nextPassthrough: boolean): void => {
      if (nextPassthrough === passthrough) return
      passthrough = nextPassthrough
      try {
        window.electron?.ipcRenderer.send('pet:set-mouse-passthrough', nextPassthrough)
      } catch {
        // preload not available (e.g. browser preview); ignore
      }
    }

    send(true)

    const handleMouseMove = (event: MouseEvent): void => {
      const target = document.elementFromPoint(event.clientX, event.clientY)
      const hit = target?.closest(INTERACTIVE_SELECTOR) ?? null
      send(hit === null)
    }

    window.addEventListener('mousemove', handleMouseMove)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
    }
  }, [])

  return (
    <main className="app-shell">
      <AnimatePresence mode="wait">
        {activePanel && (
          <motion.div
            key={activePanel}
            className="panel-wrap"
            initial={{ opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 18 }}
          >
            <button
              type="button"
              className="panel-close"
              aria-label="Close panel"
              onClick={closePanel}
            >
              x
            </button>
            {activePanel === 'pomodoro' && <PomodoroPanel />}
            {activePanel === 'stats' && <StatsPanel />}
            {activePanel === 'study-plan' && (
              <section className="panel assignments-panel">
                <div className="panel__eyebrow">Canvas due soon</div>
                <h2>Upcoming assignments</h2>
                <div className="assignments-panel__list" aria-label="Upcoming assignments">
                  {upcomingAssignments.map((assignment) => {
                    const key = `${assignment.course}-${assignment.title}`
                    const checked = checkedAssignments.has(key)
                    return (
                      <article
                        className={`assignment-card${checked ? ' assignment-card--done' : ''}`}
                        key={key}
                      >
                        <div className="assignment-card__date">
                          <span>{assignment.weekday}</span>
                          <strong>{assignment.day}</strong>
                        </div>
                        <div className="assignment-card__body">
                          <div className="assignment-card__course">
                            <span aria-hidden="true">{assignment.icon === 'rocket' ? 'R' : 'N'}</span>
                            {assignment.course}
                          </div>
                          <h3>{assignment.title}</h3>
                          <time>{assignment.time}</time>
                        </div>
                        <button
                          type="button"
                          className="assignment-card__check"
                          aria-label={`Mark ${assignment.title} complete`}
                          aria-pressed={checked}
                          onClick={() => toggleAssignment(key)}
                        >
                          {checked && (
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <polyline points="5 12 10 17 19 7" />
                            </svg>
                          )}
                        </button>
                      </article>
                    )
                  })}
                </div>
              </section>
            )}
            {activePanel === 'umd' && <UmdPanel />}
            {activePanel === 'brain' && <BrainPanel />}
          </motion.div>
        )}
      </AnimatePresence>

      <OrbMenu />
      <Pet />
      <EvolutionEffect />
    </main>
  )
}

export default App

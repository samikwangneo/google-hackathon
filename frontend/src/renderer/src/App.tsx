import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import { EvolutionEffect } from './components/EvolutionEffect'
import { OrbMenu } from './components/OrbMenu'
import { Pet } from './components/Pet'
import { PomodoroPanel } from './components/PomodoroPanel'
import { StatsPanel } from './components/StatsPanel'
import { connectBehaviorSocket } from './lib/ws'
import { useTerpPetStore } from './store'

function App(): React.JSX.Element {
  const activePanel = useTerpPetStore((state) => state.activePanel)
  const closePanel = useTerpPetStore((state) => state.closePanel)
  const connectionStatus = useTerpPetStore((state) => state.connectionStatus)
  const applyFrame = useTerpPetStore((state) => state.applyFrame)
  const setConnectionStatus = useTerpPetStore((state) => state.setConnectionStatus)

  useEffect(() => {
    const socket = connectBehaviorSocket(applyFrame, setConnectionStatus)
    return socket.close
  }, [applyFrame, setConnectionStatus])

  return (
    <main className="app-shell">
      <div className={`connection-pill connection-pill--${connectionStatus}`}>
        <span />
        {connectionStatus === 'open' ? 'Backend live' : 'Demo mode'}
      </div>

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
              <section className="panel">
                <div className="panel__eyebrow">Soon</div>
                <h2>Study plan orb</h2>
                <p>Ready for Person D&apos;s Gemini route; the typed API helper is wired.</p>
              </section>
            )}
            {activePanel === 'brain' && (
              <section className="panel">
                <div className="panel__eyebrow">Memory</div>
                <h2>Brain search</h2>
                <p>
                  The REST client can query today&apos;s notes and memory hits once the backend has
                  data.
                </p>
              </section>
            )}
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

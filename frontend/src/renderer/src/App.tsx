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
  const applyFrame = useTerpPetStore((state) => state.applyFrame)
  const setConnectionStatus = useTerpPetStore((state) => state.setConnectionStatus)

  useEffect(() => {
    const socket = connectBehaviorSocket(applyFrame, setConnectionStatus)
    return socket.close
  }, [applyFrame, setConnectionStatus])

  useEffect(() => {
    // The Electron window spans the full screen width and is transparent, so
    // it would otherwise eat clicks meant for whatever the user has under it
    // (terminal, browser, etc.). Pass-through is on by default; we only flip
    // it off when the cursor is over actual interactive UI.
    const INTERACTIVE_SELECTOR =
      '.pet, .panel, .panel-wrap, .connection-pill, .orb-menu, button, input'
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

import { AnimatePresence, motion } from 'framer-motion'

import type { ActivePanel } from '../store'
import { useTerpPetStore } from '../store'

const items: Array<{
  id: Exclude<ActivePanel, null>
  label: string
  glyph: string
  angle: number
}> = [
  { id: 'pomodoro', label: 'Pomodoro', glyph: '25', angle: -132 },
  { id: 'study-plan', label: 'Study Plan', glyph: 'SP', angle: -92 },
  { id: 'brain', label: 'Brain', glyph: 'BR', angle: -52 },
  { id: 'stats', label: 'Stats', glyph: 'XP', angle: -12 }
]

export function OrbMenu(): React.JSX.Element {
  const isOpen = useTerpPetStore((state) => state.menuOpen)
  const setActivePanel = useTerpPetStore((state) => state.setActivePanel)

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="orb-menu"
          initial={{ opacity: 0, scale: 0.72 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.72 }}
          transition={{ type: 'spring', stiffness: 360, damping: 28 }}
        >
          {items.map((item, index) => {
            const radius = 132
            const radians = (item.angle * Math.PI) / 180
            const x = Math.cos(radians) * radius
            const y = Math.sin(radians) * radius

            return (
              <motion.button
                key={item.id}
                type="button"
                className="orb-menu__item"
                style={{ left: `calc(50% + ${x}px)`, top: `calc(50% + ${y}px)` }}
                initial={{ x: 0, y: 0, opacity: 0 }}
                animate={{ x: '-50%', y: '-50%', opacity: 1 }}
                exit={{ x: 0, y: 0, opacity: 0 }}
                transition={{ delay: index * 0.035, type: 'spring', stiffness: 420, damping: 24 }}
                onClick={() => setActivePanel(item.id)}
              >
                <span>{item.glyph}</span>
                <small>{item.label}</small>
              </motion.button>
            )
          })}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

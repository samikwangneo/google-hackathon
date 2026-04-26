import { AnimatePresence, motion } from 'framer-motion'

import type { ActivePanel } from '../store'
import { useTerpPetStore } from '../store'

const items: Array<{
  id: Exclude<ActivePanel, null>
  label: string
  glyph: string
  angle: number
}> = [
  { id: 'pomodoro', label: 'Pomodoro', glyph: '25', angle: -175 },
  { id: 'study-plan', label: 'Study Plan', glyph: 'SP', angle: -140 },
  { id: 'brain', label: 'Brain', glyph: 'BR', angle: -105 },
  { id: 'stats', label: 'Stats', glyph: 'XP', angle: -75 }
]

export function OrbMenu(): React.JSX.Element {
  const isOpen = useTerpPetStore((state) => state.menuOpen)
  const petSide = useTerpPetStore((state) => state.petSide)
  const setActivePanel = useTerpPetStore((state) => state.setActivePanel)

  const positionStyle =
    petSide === 'left' ? { left: 82, right: 'auto' as const } : { right: 82, left: 'auto' as const }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="orb-menu"
          style={positionStyle}
          initial={{ opacity: 0, scale: 0.72 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.72 }}
          transition={{ type: 'spring', stiffness: 360, damping: 28 }}
        >
          {items.map((item, index) => {
            const radius = 132
            // Mirror across the vertical axis when the pet is on the left so the
            // arc fans into the screen instead of off the left edge.
            const angle = petSide === 'left' ? 180 - item.angle : item.angle
            const radians = (angle * Math.PI) / 180
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

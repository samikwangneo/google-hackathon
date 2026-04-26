import { AnimatePresence, motion } from 'framer-motion'

import type { ActivePanel } from '../store'
import { useTerpPetStore } from '../store'

type OrbId = Exclude<ActivePanel, null>

const Stopwatch = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="14" r="7" />
    <path d="M12 14V10" />
    <path d="M14.5 11.5l1.5-1.5" />
    <path d="M9 3h6" />
    <path d="M12 3v3" />
  </svg>
)

const Clipboard = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <rect x="6" y="4" width="12" height="17" rx="2.5" />
    <rect x="9" y="2.5" width="6" height="3.5" rx="1" />
    <path d="M9 11h6" />
    <path d="M9 15h4" />
  </svg>
)

const Campus = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 9.5 12 4l9 5.5" />
    <path d="M5 10.5h14" />
    <path d="M7 11v7" />
    <path d="M12 11v7" />
    <path d="M17 11v7" />
    <path d="M4 20h16" />
  </svg>
)

const Brain = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 5a3 3 0 0 0-5.83-1A2.5 2.5 0 0 0 4 8a2.5 2.5 0 0 0 .5 4.5A2.5 2.5 0 0 0 6 17a3 3 0 0 0 6 1z" />
    <path d="M12 5a3 3 0 0 1 5.83-1A2.5 2.5 0 0 1 20 8a2.5 2.5 0 0 1-.5 4.5A2.5 2.5 0 0 1 18 17a3 3 0 0 1-6 1z" />
    <path d="M12 5v13" />
  </svg>
)

const BarChart = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 20h16" />
    <path d="M7 20v-6" />
    <path d="M12 20V9" />
    <path d="M17 20v-9" />
    <path d="M7 11l5-5 3 3 4-4" />
  </svg>
)

/** Distance from viewport bottom/right to the pet hit-box center (see `.pet`). */
const PET_CENTER_OFFSET_RIGHT_PX = 28 + 64
const PET_CENTER_OFFSET_BOTTOM_PX = 26 + 64
/** Anchor box is 20×20; center it on the pet with bottom/right = center − 10. */
const ORB_MENU_ANCHOR_RIGHT_PX = PET_CENTER_OFFSET_RIGHT_PX - 10
const ORB_MENU_ANCHOR_BOTTOM_PX = PET_CENTER_OFFSET_BOTTOM_PX - 10

// True circular arc in the left half-plane (cos θ < 0) so every orb stays
// around the turtle. Slightly smaller radius sits a bit closer to the pet; a
// wider arc (~84°) adds visible curvature and opens neighbor spacing a touch
// (less overlap) without drifting onto the turtle.
const ORB_RADIUS_PX = 204
const ARC_START_DEG = -178
const ARC_END_DEG = -94

const items: Array<{
  id: OrbId
  label: string
  Icon: () => React.JSX.Element
}> = [
  { id: 'pomodoro', label: 'Pomodoro', Icon: Stopwatch },
  { id: 'study-plan', label: 'Assignments', Icon: Clipboard },
  { id: 'umd', label: 'UMD', Icon: Campus },
  { id: 'brain', label: 'Brain', Icon: Brain },
  { id: 'stats', label: 'Stats', Icon: BarChart }
]

function placementAngleDeg(index: number, total: number): number {
  if (total <= 1) return (ARC_START_DEG + ARC_END_DEG) / 2
  const t = index / (total - 1)
  return ARC_START_DEG + t * (ARC_END_DEG - ARC_START_DEG)
}

export function OrbMenu(): React.JSX.Element {
  const isOpen = useTerpPetStore((state) => state.menuOpen)
  const petSide = useTerpPetStore((state) => state.petSide)
  const setActivePanel = useTerpPetStore((state) => state.setActivePanel)

  const positionStyle =
    petSide === 'left'
      ? {
          left: ORB_MENU_ANCHOR_RIGHT_PX,
          right: 'auto' as const,
          bottom: ORB_MENU_ANCHOR_BOTTOM_PX
        }
      : {
          right: ORB_MENU_ANCHOR_RIGHT_PX,
          left: 'auto' as const,
          bottom: ORB_MENU_ANCHOR_BOTTOM_PX
        }

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
            const baseDeg = placementAngleDeg(index, items.length)
            const angleDeg = petSide === 'left' ? 180 - baseDeg : baseDeg
            const radians = (angleDeg * Math.PI) / 180
            const x = Math.cos(radians) * ORB_RADIUS_PX
            const y = Math.sin(radians) * ORB_RADIUS_PX
            const Icon = item.Icon

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
                aria-label={item.label}
              >
                <span className="orb-menu__icon" aria-hidden="true">
                  <Icon />
                </span>
                <small>{item.label}</small>
              </motion.button>
            )
          })}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

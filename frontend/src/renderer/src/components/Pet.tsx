import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

import chillSrc from '../assets/pet/chill.svg'
import walkSrc from '../assets/pet/walk.svg'
import { useTerpPetStore } from '../store'

const moodCopy = {
  HAPPY: 'Locked in',
  NEUTRAL: 'Ready',
  ANNOYED: 'Back to work',
  SLEEPY: 'Where did you go?',
  FOCUS_MODE: 'Focus mode',
  EVOLVED: 'Level up!'
} as const

type Phase = 'walking' | 'chilling'

const WALK_DURATION_S = 32
const PHASE_DURATION_MS: Record<Phase, number> = {
  walking: WALK_DURATION_S * 1000,
  chilling: 9000
}

// Flip the sprite instantly at the two direction-change moments (start of the
// walk and the turnaround at the far edge). The tiny 0.001 windows give a
// snap rather than a smooth rotation through 0.
const SCALEX_KEYFRAMES = [1, -1, -1, 1, 1]
const SCALEX_TIMES = [0, 0.001, 0.499, 0.501, 1]

// Pet sprite is 178px wide and anchored at right: 34px. Reserve a bit of left
// padding so the pet doesn't slam into the window edge.
const PET_RIGHT_OFFSET_PX = 34 + 178
const LEFT_MARGIN_PX = 24

const SPRITE_STYLE: React.CSSProperties = {
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
  objectFit: 'contain',
  pointerEvents: 'none',
  userSelect: 'none'
}

export function Pet(): React.JSX.Element {
  const mood = useTerpPetStore((state) => state.pet_mood)
  const behavior = useTerpPetStore((state) => state.state)
  const presence = useTerpPetStore((state) => state.presence)
  const toggleMenu = useTerpPetStore((state) => state.toggleMenu)

  const [phase, setPhase] = useState<Phase>('chilling')
  const [walkDistance, setWalkDistance] = useState(() =>
    typeof window === 'undefined'
      ? 600
      : Math.max(200, window.innerWidth - PET_RIGHT_OFFSET_PX - LEFT_MARGIN_PX)
  )

  useEffect(() => {
    const timer = window.setTimeout(
      () => setPhase((prev) => (prev === 'walking' ? 'chilling' : 'walking')),
      PHASE_DURATION_MS[phase]
    )
    return () => window.clearTimeout(timer)
  }, [phase])

  useEffect(() => {
    const handleResize = (): void => {
      setWalkDistance(Math.max(200, window.innerWidth - PET_RIGHT_OFFSET_PX - LEFT_MARGIN_PX))
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const isAnnoyed = mood === 'ANNOYED'
  const isSleepy = mood === 'SLEEPY'
  const isWalking = phase === 'walking'

  return (
    <motion.button
      type="button"
      className={`pet pet--${mood.toLowerCase()}`}
      aria-label="Open TerpPet actions"
      onClick={toggleMenu}
      animate={{
        x: isWalking
          ? [0, -walkDistance * 0.5, -walkDistance, -walkDistance * 0.5, 0]
          : 0,
        y: isWalking ? [0, -3, 0, -3, 0] : isSleepy ? [0, 7, 0] : [0, -6, 0],
        rotate: isAnnoyed ? [0, -6, 6, -4, 4, 0] : 0,
        scaleX: isWalking ? SCALEX_KEYFRAMES : 1,
        scale: mood === 'EVOLVED' ? [1, 1.12, 1] : 1
      }}
      transition={{
        duration: isWalking ? WALK_DURATION_S : isAnnoyed ? 0.45 : 2.8,
        repeat: isAnnoyed ? Infinity : isWalking ? 0 : Infinity,
        repeatDelay: isAnnoyed ? 1.5 : 0,
        ease: isWalking ? 'linear' : 'easeInOut',
        scaleX: isWalking
          ? { duration: WALK_DURATION_S, ease: 'linear', times: SCALEX_TIMES }
          : { duration: 0 }
      }}
    >
      <img
        src={isWalking ? walkSrc : chillSrc}
        alt={isWalking ? 'Pet walking' : 'Pet chilling'}
        draggable={false}
        style={SPRITE_STYLE}
      />
      <span className="pet__status">
        <strong>{moodCopy[mood]}</strong>
        <small>
          {behavior.toLowerCase().replace('_', ' ')} / {presence.toLowerCase().replace('_', ' ')}
        </small>
      </span>
    </motion.button>
  )
}

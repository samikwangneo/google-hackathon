import { motion } from 'framer-motion'

import { useTerpPetStore } from '../store'

const moodCopy = {
  HAPPY: 'Locked in',
  NEUTRAL: 'Ready',
  ANNOYED: 'Back to work',
  SLEEPY: 'Where did you go?',
  FOCUS_MODE: 'Focus mode',
  EVOLVED: 'Level up!'
} as const

export function Pet(): React.JSX.Element {
  const mood = useTerpPetStore((state) => state.pet_mood)
  const behavior = useTerpPetStore((state) => state.state)
  const presence = useTerpPetStore((state) => state.presence)
  const toggleMenu = useTerpPetStore((state) => state.toggleMenu)

  const isAnnoyed = mood === 'ANNOYED'
  const isSleepy = mood === 'SLEEPY'

  return (
    <motion.button
      type="button"
      className={`pet pet--${mood.toLowerCase()}`}
      aria-label="Open TerpPet actions"
      onClick={toggleMenu}
      animate={{
        y: isSleepy ? [0, 7, 0] : [0, -6, 0],
        rotate: isAnnoyed ? [0, -6, 6, -4, 4, 0] : 0,
        scale: mood === 'EVOLVED' ? [1, 1.12, 1] : 1
      }}
      transition={{
        duration: isAnnoyed ? 0.45 : 2.8,
        repeat: isAnnoyed ? Infinity : Infinity,
        repeatDelay: isAnnoyed ? 1.5 : 0,
        ease: 'easeInOut'
      }}
    >
      <span className="pet__aura" />
      <span className="pet__ears">
        <span />
        <span />
      </span>
      <span className="pet__body">
        <span className="pet__face">
          <span className="pet__eye pet__eye--left" />
          <span className="pet__eye pet__eye--right" />
          <span className="pet__mouth" />
        </span>
        <span className="pet__shell">M</span>
      </span>
      <span className="pet__shadow" />
      <span className="pet__status">
        <strong>{moodCopy[mood]}</strong>
        <small>
          {behavior.toLowerCase().replace('_', ' ')} / {presence.toLowerCase().replace('_', ' ')}
        </small>
      </span>
    </motion.button>
  )
}

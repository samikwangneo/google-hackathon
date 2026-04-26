import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

import levelUpSrc from '../assets/pet/levelup.png'
import { useTerpPetStore } from '../store'
import { TerpPetSprite, type SpriteSheetConfig } from './TerpPetSprite'

const levelUpSheet: SpriteSheetConfig = {
  src: levelUpSrc,
  frameWidth: 704,
  frameHeight: 704,
  frames: 8,
  frameDurationMs: 135
}

const PET_RIGHT_OFFSET_PX = 28 + 128
const LEFT_MARGIN_PX = 24

// Symmetric ping-pong cycle (single looping keyframe animation):
//   1. chill at right anchor (CHILL_DURATION_S)
//   2. visible flip to face right, walk rightward off the right edge
//   3. instant off-screen wrap from off-right to off-left
//   4. continue walking rightward into view, stop at left anchor
//   5. chill at left anchor (CHILL_DURATION_S)
//   6. visible flip to face left, walk leftward off the left edge
//   7. instant off-screen wrap from off-left to off-right
//   8. continue walking leftward into view, stop at right anchor (loop wrap)
// The wraps stay instant but happen entirely off-screen, so the user sees a
// continuous walk that "comes back in" from the opposite edge instead of the
// pet popping in. Linear ease + proportional `times` keep walking speed
// constant across all four walking segments.
const CHILL_DURATION_S = 5
const WALK_SPEED_PX_PER_S = 180
const OFF_SCREEN_BUFFER_PX = 260

export function Pet(): React.JSX.Element {
  const mood = useTerpPetStore((state) => state.pet_mood)
  const toggleMenu = useTerpPetStore((state) => state.toggleMenu)

  const [walkDistance, setWalkDistance] = useState(() =>
    typeof window === 'undefined'
      ? 260
      : Math.max(160, window.innerWidth - PET_RIGHT_OFFSET_PX - LEFT_MARGIN_PX)
  )

  useEffect(() => {
    const handleResize = (): void => {
      setWalkDistance(Math.max(160, window.innerWidth - PET_RIGHT_OFFSET_PX - LEFT_MARGIN_PX))
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const isAnnoyed = mood === 'ANNOYED'
  const isSleepy = mood === 'SLEEPY'

  const walkOffSeconds = OFF_SCREEN_BUFFER_PX / WALK_SPEED_PX_PER_S
  const totalCycleSeconds = 2 * CHILL_DURATION_S + 4 * walkOffSeconds
  // Cycle phase boundaries (normalized 0..1)
  const tRightChillEnd = CHILL_DURATION_S / totalCycleSeconds
  const tWalkOffRightEnd = (CHILL_DURATION_S + walkOffSeconds) / totalCycleSeconds
  const tEnterLeftEnd = (CHILL_DURATION_S + 2 * walkOffSeconds) / totalCycleSeconds
  const tLeftChillEnd = (2 * CHILL_DURATION_S + 2 * walkOffSeconds) / totalCycleSeconds
  const tWalkOffLeftEnd = (2 * CHILL_DURATION_S + 3 * walkOffSeconds) / totalCycleSeconds

  return (
    <motion.button
      type="button"
      className={`pet pet--${mood.toLowerCase()}`}
      aria-label="Open TerpPet actions"
      onClick={toggleMenu}
      initial={{ x: 0, scaleX: -1 }}
      animate={{
        x: [
          0,
          0,
          OFF_SCREEN_BUFFER_PX,
          -(walkDistance + OFF_SCREEN_BUFFER_PX),
          -walkDistance,
          -walkDistance,
          -(walkDistance + OFF_SCREEN_BUFFER_PX),
          OFF_SCREEN_BUFFER_PX,
          0
        ],
        scaleX: [-1, -1, 1, 1, -1, -1],
        y: isSleepy ? [0, 7, 0] : [0, -6, 0],
        rotate: isAnnoyed ? [0, -6, 6, -4, 4, 0] : 0,
        scale: mood === 'EVOLVED' ? [1, 1.12, 1] : 1
      }}
      transition={{
        default: { duration: 2.8, repeat: Infinity, ease: 'easeInOut' },
        x: {
          duration: totalCycleSeconds,
          times: [
            0,
            tRightChillEnd,
            tWalkOffRightEnd,
            tWalkOffRightEnd + 0.0001,
            tEnterLeftEnd,
            tLeftChillEnd,
            tWalkOffLeftEnd,
            tWalkOffLeftEnd + 0.0001,
            1
          ],
          repeat: Infinity,
          ease: 'linear'
        },
        scaleX: {
          duration: totalCycleSeconds,
          times: [
            0,
            tRightChillEnd - 0.0001,
            tRightChillEnd,
            tLeftChillEnd - 0.0001,
            tLeftChillEnd,
            1
          ],
          repeat: Infinity,
          ease: 'linear'
        },
        rotate: isAnnoyed
          ? { duration: 0.45, repeat: Infinity, repeatDelay: 1.5, ease: 'easeInOut' }
          : { duration: 0 }
      }}
    >
      <TerpPetSprite
        sheet={levelUpSheet}
        loop
        autoPlay
        className="pet__sprite"
        title="TerpPet level up animation"
      />
    </motion.button>
  )
}

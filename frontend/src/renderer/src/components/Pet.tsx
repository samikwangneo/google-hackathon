import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

import annoyedSrc from '../assets/pet/Annoyed.png'
import annoyedOnPhoneSrc from '../assets/pet/Annoyed on phone.png'
import badAppleSrc from '../assets/pet/Bad apple.png'
import chillSrc from '../assets/pet/Chill.png'
import focusStudyingSrc from '../assets/pet/Focus-Studying.png'
import gameboySrc from '../assets/pet/Gameboy.png'
import goodAppleSrc from '../assets/pet/Good apple.png'
import jengaSrc from '../assets/pet/Jenga.png'
import levelUpSrc from '../assets/pet/levelup.png'
import sleepySrc from '../assets/pet/Sleepy.png'
import stressFocusSrc from '../assets/pet/Stress focus.png'
import walkingSrc from '../assets/pet/Walking.png'
import { useTerpPetStore } from '../store'
import type { PetMood } from '../types/contracts'
import { TerpPetSprite, type SpriteSheetConfig } from './TerpPetSprite'

type PetSpriteConfig = SpriteSheetConfig & {
  title: string
}

function createPetSheet(src: string, title: string, frameDurationMs = 250): PetSpriteConfig {
  return {
    src,
    frameWidth: 704,
    frameHeight: 704,
    frames: 8,
    frameDurationMs,
    title
  }
}

const PET_SPRITES: Record<PetMood, PetSpriteConfig> = {
  HAPPY: createPetSheet(chillSrc, 'TerpPet happy chill animation'),
  NEUTRAL: createPetSheet(chillSrc, 'TerpPet chill animation'),
  ANNOYED: createPetSheet(annoyedSrc, 'TerpPet annoyed animation'),
  SLEEPY: createPetSheet(sleepySrc, 'TerpPet sleepy animation', 265),
  FOCUS_MODE: createPetSheet(focusStudyingSrc, 'TerpPet focus studying animation'),
  EVOLVED: createPetSheet(levelUpSrc, 'TerpPet level up animation'),
  GOOD_APPLE: createPetSheet(goodAppleSrc, 'TerpPet good apple animation'),
  BAD_APPLE: createPetSheet(badAppleSrc, 'TerpPet bad apple animation'),
  JENGA: createPetSheet(jengaSrc, 'TerpPet Jenga animation'),
  GAMEBOY: createPetSheet(gameboySrc, 'TerpPet Game Boy animation'),
  GENTLE_BREATHING: createPetSheet(chillSrc, 'TerpPet gentle breathing animation', 275),
  ANNOYED_FOOT_TAPPING: createPetSheet(annoyedSrc, 'TerpPet foot tapping animation', 220),
  ANNOYED_DOOM_SCROLLING: createPetSheet(
    annoyedOnPhoneSrc,
    'TerpPet doom scrolling animation'
  ),
  EXAM_PANIC_MODE: createPetSheet(stressFocusSrc, 'TerpPet exam panic animation', 210)
}

const WALKING_SPRITE = createPetSheet(walkingSrc, 'TerpPet walking animation', 230)

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
  const phonePresent = useTerpPetStore((state) => state.phone_present)
  const toggleMenu = useTerpPetStore((state) => state.toggleMenu)
  const setPetSide = useTerpPetStore((state) => state.setPetSide)
  const menuOpen = useTerpPetStore((state) => state.menuOpen)
  const petSide = useTerpPetStore((state) => state.petSide)
  const [isWalking, setIsWalking] = useState(false)

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

  const isAnnoyed =
    mood === 'ANNOYED' ||
    mood === 'ANNOYED_FOOT_TAPPING' ||
    mood === 'ANNOYED_DOOM_SCROLLING' ||
    mood === 'EXAM_PANIC_MODE'
  const isSleepy = mood === 'SLEEPY'

  const walkOffSeconds = OFF_SCREEN_BUFFER_PX / WALK_SPEED_PX_PER_S
  const totalCycleSeconds = 2 * CHILL_DURATION_S + 4 * walkOffSeconds
  // Cycle phase boundaries (normalized 0..1)
  const tRightChillEnd = CHILL_DURATION_S / totalCycleSeconds
  const tWalkOffRightEnd = (CHILL_DURATION_S + walkOffSeconds) / totalCycleSeconds
  const tEnterLeftEnd = (CHILL_DURATION_S + 2 * walkOffSeconds) / totalCycleSeconds
  const tLeftChillEnd = (2 * CHILL_DURATION_S + 2 * walkOffSeconds) / totalCycleSeconds
  const tWalkOffLeftEnd = (2 * CHILL_DURATION_S + 3 * walkOffSeconds) / totalCycleSeconds

  useEffect(() => {
    if (menuOpen) {
      // Freeze the cycle while the orb menu is open so the pet stays put and
      // petSide doesn't flip the menu's anchor mid-interaction.
      setIsWalking(false)
      return
    }

    const cycleStartedAt = window.performance.now()
    const updateCycleState = (): void => {
      const elapsedSeconds = (window.performance.now() - cycleStartedAt) / 1000
      const phase = (elapsedSeconds % totalCycleSeconds) / totalCycleSeconds
      const currentlyWalking =
        (phase >= tRightChillEnd && phase < tEnterLeftEnd) || phase >= tLeftChillEnd
      const currentSide: 'left' | 'right' =
        phase >= tWalkOffRightEnd && phase < tWalkOffLeftEnd ? 'left' : 'right'

      setIsWalking((wasWalking) => (wasWalking === currentlyWalking ? wasWalking : currentlyWalking))
      setPetSide(currentSide)
    }

    updateCycleState()
    const intervalId = window.setInterval(updateCycleState, 100)
    return () => window.clearInterval(intervalId)
  }, [
    menuOpen,
    setPetSide,
    tEnterLeftEnd,
    tLeftChillEnd,
    tRightChillEnd,
    tWalkOffLeftEnd,
    tWalkOffRightEnd,
    totalCycleSeconds
  ])

  const moodSprite =
    phonePresent && isAnnoyed ? PET_SPRITES.ANNOYED_DOOM_SCROLLING : PET_SPRITES[mood]
  const sprite = isWalking ? WALKING_SPRITE : moodSprite

  return (
    <motion.button
      type="button"
      className={`pet pet--${mood.toLowerCase()}`}
      aria-label="Open TerpPet actions"
      onClick={toggleMenu}
      initial={{ x: 0, scaleX: -1 }}
      animate={{
        x: menuOpen
          ? petSide === 'left'
            ? -walkDistance
            : 0
          : [
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
        scaleX: menuOpen ? (petSide === 'left' ? 1 : -1) : [-1, -1, 1, 1, -1, -1],
        y: isSleepy ? [0, 7, 0] : [0, -6, 0],
        rotate: isAnnoyed ? [0, -6, 6, -4, 4, 0] : 0,
        scale: mood === 'EVOLVED' ? [1, 1.12, 1] : 1
      }}
      transition={{
        default: { duration: 2.8, repeat: Infinity, ease: 'easeInOut' },
        x: menuOpen
          ? { duration: 0.4, ease: 'easeOut' }
          : {
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
        scaleX: menuOpen
          ? { duration: 0.4, ease: 'easeOut' }
          : {
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
        sheet={sprite}
        loop
        autoPlay
        className="pet__sprite"
        title={sprite.title}
      />
    </motion.button>
  )
}

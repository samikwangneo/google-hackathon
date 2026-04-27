import { useEffect, useRef, useState } from 'react'
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

type AnimationViewerEntry = {
  mood: PetMood
  label: string
  sheet: PetSpriteConfig
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
  ANNOYED_DOOM_SCROLLING: createPetSheet(annoyedOnPhoneSrc, 'TerpPet doom scrolling animation'),
  EXAM_PANIC_MODE: createPetSheet(stressFocusSrc, 'TerpPet exam panic animation', 210),
  WALKING: createPetSheet(walkingSrc, 'TerpPet walking animation', 230)
}

const WALKING_SPRITE = createPetSheet(walkingSrc, 'TerpPet walking animation', 230)

const ANIMATION_VIEWER_ENTRIES: AnimationViewerEntry[] = [
  { mood: 'NEUTRAL', label: 'Chill', sheet: PET_SPRITES.NEUTRAL },
  { mood: 'HAPPY', label: 'Happy', sheet: PET_SPRITES.HAPPY },
  { mood: 'ANNOYED', label: 'Annoyed', sheet: PET_SPRITES.ANNOYED },
  { mood: 'SLEEPY', label: 'Sleepy', sheet: PET_SPRITES.SLEEPY },
  { mood: 'FOCUS_MODE', label: 'Focus', sheet: PET_SPRITES.FOCUS_MODE },
  { mood: 'EVOLVED', label: 'Level Up', sheet: PET_SPRITES.EVOLVED },
  { mood: 'GOOD_APPLE', label: 'Good Apple', sheet: PET_SPRITES.GOOD_APPLE },
  { mood: 'BAD_APPLE', label: 'Bad Apple', sheet: PET_SPRITES.BAD_APPLE },
  { mood: 'JENGA', label: 'Jenga', sheet: PET_SPRITES.JENGA },
  { mood: 'GAMEBOY', label: 'Game Boy', sheet: PET_SPRITES.GAMEBOY },
  { mood: 'GENTLE_BREATHING', label: 'Breathing', sheet: PET_SPRITES.GENTLE_BREATHING },
  {
    mood: 'ANNOYED_FOOT_TAPPING',
    label: 'Foot Tap',
    sheet: PET_SPRITES.ANNOYED_FOOT_TAPPING
  },
  {
    mood: 'ANNOYED_DOOM_SCROLLING',
    label: 'Doomscroll',
    sheet: PET_SPRITES.ANNOYED_DOOM_SCROLLING
  },
  { mood: 'EXAM_PANIC_MODE', label: 'Exam Panic', sheet: PET_SPRITES.EXAM_PANIC_MODE },
  { mood: 'WALKING', label: 'Walking', sheet: PET_SPRITES.WALKING }
]

const PET_RIGHT_OFFSET_PX = 28 + 128
const LEFT_MARGIN_PX = 24
const TAB_JAILBREAK_COUNT = 5
const TAB_JAILBREAK_WINDOW_MS = 900
const VIEWER_DIGIT_WINDOW_MS = 700

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
  const [viewerEnabled, setViewerEnabled] = useState(false)
  const [viewerIndex, setViewerIndex] = useState(0)
  const [viewerReplayKey, setViewerReplayKey] = useState(0)
  const tabCountRef = useRef(0)
  const lastTabAtRef = useRef(0)
  const digitBufferRef = useRef('')
  const digitTimeoutRef = useRef<number | null>(null)

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

  const viewerEntry = ANIMATION_VIEWER_ENTRIES[viewerIndex]
  const effectiveMood = viewerEnabled ? viewerEntry.mood : mood
  const isAnnoyed =
    effectiveMood === 'ANNOYED' ||
    effectiveMood === 'ANNOYED_FOOT_TAPPING' ||
    effectiveMood === 'ANNOYED_DOOM_SCROLLING' ||
    effectiveMood === 'EXAM_PANIC_MODE'
  const isSleepy = effectiveMood === 'SLEEPY'
  const walkingMood = !viewerEnabled && mood === 'WALKING'

  const walkOffSeconds = OFF_SCREEN_BUFFER_PX / WALK_SPEED_PX_PER_S
  const totalCycleSeconds = 2 * CHILL_DURATION_S + 4 * walkOffSeconds
  // Cycle phase boundaries (normalized 0..1)
  const tRightChillEnd = CHILL_DURATION_S / totalCycleSeconds
  const tWalkOffRightEnd = (CHILL_DURATION_S + walkOffSeconds) / totalCycleSeconds
  const tEnterLeftEnd = (CHILL_DURATION_S + 2 * walkOffSeconds) / totalCycleSeconds
  const tLeftChillEnd = (2 * CHILL_DURATION_S + 2 * walkOffSeconds) / totalCycleSeconds
  const tWalkOffLeftEnd = (2 * CHILL_DURATION_S + 3 * walkOffSeconds) / totalCycleSeconds

  useEffect(() => {
    if (menuOpen || !walkingMood) {
      // Freeze the cycle while the orb menu is open or the pet isn't in
      // WALKING mood, so the pet stays parked at its anchor.
      if (!walkingMood) {
        setPetSide('right')
      }
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

      setIsWalking((wasWalking) =>
        wasWalking === currentlyWalking ? wasWalking : currentlyWalking
      )
      setPetSide(currentSide)
    }

    updateCycleState()
    const intervalId = window.setInterval(updateCycleState, 100)
    return () => window.clearInterval(intervalId)
  }, [
    menuOpen,
    walkingMood,
    setPetSide,
    tEnterLeftEnd,
    tLeftChillEnd,
    tRightChillEnd,
    tWalkOffLeftEnd,
    tWalkOffRightEnd,
    totalCycleSeconds
  ])

  useEffect(() => {
    const clearDigitBuffer = (): void => {
      digitBufferRef.current = ''
      if (digitTimeoutRef.current !== null) {
        window.clearTimeout(digitTimeoutRef.current)
        digitTimeoutRef.current = null
      }
    }

    const playViewerAnimation = (index: number): void => {
      setViewerIndex(index)
      setViewerReplayKey((key) => key + 1)
    }

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Tab') {
        const now = window.performance.now()
        tabCountRef.current =
          now - lastTabAtRef.current <= TAB_JAILBREAK_WINDOW_MS ? tabCountRef.current + 1 : 1
        lastTabAtRef.current = now

        if (tabCountRef.current >= TAB_JAILBREAK_COUNT) {
          event.preventDefault()
          tabCountRef.current = 0
          clearDigitBuffer()
          setViewerEnabled((enabled) => !enabled)
          playViewerAnimation(0)
        }
        return
      }

      if (!viewerEnabled) return

      if (event.key === 'Escape') {
        event.preventDefault()
        clearDigitBuffer()
        setViewerEnabled(false)
        return
      }

      if (!/^\d$/.test(event.key)) return

      event.preventDefault()
      const candidate = digitBufferRef.current ? `${digitBufferRef.current}${event.key}` : event.key
      const parsed = candidate === '0' ? 10 : Number(candidate)
      const fallback = event.key === '0' ? 10 : Number(event.key)
      const animationNumber =
        parsed >= 1 && parsed <= ANIMATION_VIEWER_ENTRIES.length ? parsed : fallback

      if (animationNumber >= 1 && animationNumber <= ANIMATION_VIEWER_ENTRIES.length) {
        playViewerAnimation(animationNumber - 1)
      }

      const hasLongerMatch = ANIMATION_VIEWER_ENTRIES.some((_, index) =>
        String(index + 1).startsWith(candidate)
      )
      digitBufferRef.current =
        candidate.length < 2 && hasLongerMatch && candidate !== '0' ? candidate : ''

      if (digitBufferRef.current) {
        if (digitTimeoutRef.current !== null) {
          window.clearTimeout(digitTimeoutRef.current)
        }
        digitTimeoutRef.current = window.setTimeout(clearDigitBuffer, VIEWER_DIGIT_WINDOW_MS)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      clearDigitBuffer()
    }
  }, [viewerEnabled])

  const moodSprite =
    !viewerEnabled && phonePresent && isAnnoyed
      ? PET_SPRITES.ANNOYED_DOOM_SCROLLING
      : PET_SPRITES[effectiveMood]
  const sprite = viewerEnabled
    ? viewerEntry.sheet
    : walkingMood && !menuOpen && isWalking
      ? WALKING_SPRITE
      : moodSprite

  return (
    <>
      <motion.button
        type="button"
        className={`pet pet--${effectiveMood.toLowerCase()} ${
          viewerEnabled ? 'pet--animation-viewer' : ''
        }`}
        aria-label={viewerEnabled ? 'TerpPet animation viewer active' : 'Open TerpPet actions'}
        onClick={viewerEnabled ? undefined : toggleMenu}
        initial={{ x: 0, scaleX: -1 }}
        animate={{
          x: viewerEnabled
            ? 0
            : menuOpen
              ? petSide === 'left'
                ? -walkDistance
                : 0
              : walkingMood
                ? [
                    0,
                    0,
                    OFF_SCREEN_BUFFER_PX,
                    -(walkDistance + OFF_SCREEN_BUFFER_PX),
                    -walkDistance,
                    -walkDistance,
                    -(walkDistance + OFF_SCREEN_BUFFER_PX),
                    OFF_SCREEN_BUFFER_PX,
                    0
                  ]
                : 0,
          scaleX: viewerEnabled
            ? -1
            : menuOpen
              ? petSide === 'left'
                ? 1
                : -1
              : walkingMood
                ? [-1, -1, 1, 1, -1, -1]
                : -1,
          y: isSleepy ? [0, 7, 0] : [0, -6, 0],
          rotate: isAnnoyed ? [0, -6, 6, -4, 4, 0] : 0,
          scale: effectiveMood === 'EVOLVED' ? [1, 1.12, 1] : 1
        }}
        transition={{
          default: { duration: 2.8, repeat: Infinity, ease: 'easeInOut' },
          x: viewerEnabled
            ? { duration: 0.25, ease: 'easeOut' }
            : menuOpen
              ? { duration: 0.4, ease: 'easeOut' }
              : walkingMood
                ? {
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
                  }
                : { duration: 0.6, ease: 'easeOut' },
          scaleX: viewerEnabled
            ? { duration: 0.25, ease: 'easeOut' }
            : menuOpen
              ? { duration: 0.4, ease: 'easeOut' }
              : walkingMood
                ? {
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
                  }
                : { duration: 0.4, ease: 'easeOut' },
          rotate: isAnnoyed
            ? { duration: 0.45, repeat: Infinity, repeatDelay: 1.5, ease: 'easeInOut' }
            : { duration: 0 }
        }}
      >
        <TerpPetSprite
          key={viewerEnabled ? `viewer-${viewerIndex}-${viewerReplayKey}` : `live-${sprite.src}`}
          sheet={sprite}
          loop
          autoPlay
          className="pet__sprite"
          title={sprite.title}
        />
      </motion.button>

      {viewerEnabled && (
        <motion.aside
          className="animation-viewer"
          initial={{ opacity: 0, y: 10, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.96 }}
        >
          <div className="animation-viewer__header">
            <span>Dev Animation Viewer</span>
            <strong>{viewerIndex + 1}</strong>
          </div>
          <div className="animation-viewer__grid">
            {ANIMATION_VIEWER_ENTRIES.map((entry, index) => (
              <button
                key={`${entry.mood}-${index}`}
                type="button"
                className={
                  index === viewerIndex
                    ? 'animation-viewer__item is-active'
                    : 'animation-viewer__item'
                }
                onClick={() => {
                  setViewerIndex(index)
                  setViewerReplayKey((key) => key + 1)
                }}
              >
                <kbd>{index + 1}</kbd>
                <span>{entry.label}</span>
              </button>
            ))}
          </div>
          <p>Type 1-15 to play. Esc closes. Tab x5 toggles.</p>
        </motion.aside>
      )}
    </>
  )
}

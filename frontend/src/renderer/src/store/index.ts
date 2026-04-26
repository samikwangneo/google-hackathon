import { create } from 'zustand'

import type {
  BehaviorSocketFrame,
  BehaviorState,
  BehaviorUpdate,
  PetMood,
  PomodoroState,
  PresenceState
} from '../types/contracts'
import type { SocketStatus } from '../lib/ws'

export type ActivePanel = 'pomodoro' | 'study-plan' | 'umd' | 'brain' | 'stats' | null

export type PetSide = 'left' | 'right'

interface TerpPetState extends BehaviorUpdate {
  activePanel: ActivePanel
  connectionStatus: SocketStatus
  lastFrameAt: number | null
  menuOpen: boolean
  petSide: PetSide
  showEvolution: boolean
  xpFlash: number | null
  applyFrame: (frame: BehaviorSocketFrame) => void
  clearEvolution: () => void
  closePanel: () => void
  setActivePanel: (panel: ActivePanel) => void
  setConnectionStatus: (status: SocketStatus) => void
  setMenuOpen: (open: boolean) => void
  setPetSide: (side: PetSide) => void
  setPomodoro: (pomodoro: PomodoroState) => void
  toggleMenu: () => void
}

const initialPomodoro: PomodoroState = {
  running: false,
  ends_at: null,
  minutes: 25
}

const initialBehavior: BehaviorUpdate = {
  state: 'IDLE',
  presence: 'PRESENT',
  pet_mood: 'NEUTRAL',
  active_window: null,
  focus_seconds: 0,
  distraction_streak: 0,
  xp: 0,
  level: 1,
  pomodoro: initialPomodoro,
  phone_present: false
}

function isSpecialEvent(
  frame: BehaviorSocketFrame
): frame is Extract<BehaviorSocketFrame, { type: string }> {
  return 'type' in frame
}

export const useTerpPetStore = create<TerpPetState>((set) => ({
  ...initialBehavior,
  activePanel: null,
  connectionStatus: 'closed',
  lastFrameAt: null,
  menuOpen: false,
  petSide: 'right',
  showEvolution: false,
  xpFlash: null,
  applyFrame: (frame) =>
    set((state) => {
      if (!isSpecialEvent(frame)) {
        return {
          ...frame,
          lastFrameAt: Date.now(),
          showEvolution: frame.pet_mood === 'EVOLVED' || state.showEvolution
        }
      }

      if (frame.type === 'level_up') {
        return {
          level: frame.level,
          pet_mood: 'EVOLVED' as PetMood,
          showEvolution: true,
          lastFrameAt: Date.now()
        }
      }

      if (frame.type === 'pomodoro_failed') {
        return {
          pet_mood: 'BAD_APPLE' as PetMood,
          lastFrameAt: Date.now()
        }
      }

      return {
        xp: state.xp + frame.xp_delta,
        xpFlash: frame.xp_delta,
        lastFrameAt: Date.now()
      }
    }),
  clearEvolution: () => set({ showEvolution: false, xpFlash: null }),
  closePanel: () => set({ activePanel: null }),
  setActivePanel: (panel) => set({ activePanel: panel }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setMenuOpen: (open) => set({ menuOpen: open }),
  setPetSide: (petSide) => set({ petSide }),
  setPomodoro: (pomodoro) => set({ pomodoro }),
  toggleMenu: () => set((state) => ({ menuOpen: !state.menuOpen }))
}))

export type { BehaviorState, PetMood, PomodoroState, PresenceState }

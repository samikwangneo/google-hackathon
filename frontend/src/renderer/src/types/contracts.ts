export type BehaviorState = 'FOCUSED' | 'DISTRACTED' | 'IDLE' | 'MULTITASKING' | 'AWAY'

export type PresenceState = 'PRESENT' | 'ABSENT' | 'LOOKING_AWAY'

export type PetMood =
  | 'HAPPY'
  | 'NEUTRAL'
  | 'ANNOYED'
  | 'SLEEPY'
  | 'FOCUS_MODE'
  | 'EVOLVED'
  | 'GOOD_APPLE'
  | 'BAD_APPLE'
  | 'JENGA'
  | 'GAMEBOY'
  | 'GENTLE_BREATHING'
  | 'ANNOYED_FOOT_TAPPING'
  | 'ANNOYED_DOOM_SCROLLING'
  | 'EXAM_PANIC_MODE'
  | 'WALKING'

export interface PomodoroState {
  running: boolean
  ends_at: string | null
  minutes: number
}

export interface BehaviorUpdate {
  state: BehaviorState
  presence: PresenceState
  pet_mood: PetMood
  active_window: string | null
  focus_seconds: number
  distraction_streak: number
  xp: number
  level: number
  pomodoro: PomodoroState
  phone_present: boolean
}

export interface PomodoroCompletedEvent {
  type: 'pomodoro_completed'
  xp_delta: number
}

export interface LevelUpEvent {
  type: 'level_up'
  level: number
}

export interface PomodoroFailedEvent {
  type: 'pomodoro_failed'
}

export type BehaviorSocketFrame =
  | BehaviorUpdate
  | PomodoroCompletedEvent
  | LevelUpEvent
  | PomodoroFailedEvent

export interface PomodoroStartRequest {
  minutes: number
}

export interface PomodoroStartResponse {
  started_at: string
  ends_at: string
}

export interface OkResponse {
  ok: boolean
}

export interface StudyPlanRequest {
  goal: string
  hours_available: number
}

export interface StudyPlanBlock {
  start_minute: number
  duration_minutes: number
  topic: string
  activity: string
}

export interface StudyPlanResponse {
  blocks: StudyPlanBlock[]
  summary: string
}

export interface SummarizeRequest {
  text: string
}

export interface QuizQuestion {
  question: string
  answer: string
}

export interface SummarizeResponse {
  summary: string
  quiz: QuizQuestion[]
}

export interface BrainHit {
  timestamp: string
  kind: string
  text: string
  score: number
}

export interface BrainSearchResponse {
  hits: BrainHit[]
}

export interface BrainTodayResponse {
  summary: string
  topics: string[]
  score: number
}

export interface BrainChatMessage {
  role: 'user' | 'assistant'
  text: string
}

export interface BrainExplainRequest {
  session_id: string | null
}

export interface BrainExplainResponse {
  session_id: string
  reply: string
}

export interface BrainChatRequest {
  session_id: string
  message: string
  history: BrainChatMessage[]
}

export interface BrainChatResponse {
  reply: string
}

export interface StudySpot {
  name: string
  vibe: string
  busyness: string
}

export interface DiningRec {
  hall: string
  recommendation: string
  vibe: string
}

export interface StatsTodayResponse {
  focus_seconds: number
  xp: number
  level: number
  pomodoros: number
}

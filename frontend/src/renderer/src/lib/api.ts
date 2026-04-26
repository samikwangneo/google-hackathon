import type {
  BrainChatMessage,
  BrainChatResponse,
  BrainExplainResponse,
  DiningRec,
  OkResponse,
  PomodoroStartResponse,
  StudySpot
} from '../types/contracts'

const API_BASE_URL =
  (import.meta.env.VITE_BACKEND_API_URL as string | undefined) ?? 'http://127.0.0.1:8765'

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export async function startPomodoro(minutes: number): Promise<PomodoroStartResponse> {
  return postJSON<PomodoroStartResponse>('/api/pomodoro/start', { minutes })
}

export async function stopPomodoro(): Promise<OkResponse> {
  return postJSON<OkResponse>('/api/pomodoro/stop')
}

export async function brainExplain(sessionId: string | null): Promise<BrainExplainResponse> {
  return postJSON<BrainExplainResponse>('/api/brain/explain', { session_id: sessionId })
}

export async function brainChat(
  sessionId: string,
  message: string,
  history: BrainChatMessage[]
): Promise<BrainChatResponse> {
  return postJSON<BrainChatResponse>('/api/brain/chat', {
    session_id: sessionId,
    message,
    history
  })
}

export async function getStudySpots(): Promise<StudySpot[]> {
  return getJSON<StudySpot[]>('/api/umd/study-spots')
}

export async function getDining(): Promise<DiningRec[]> {
  return getJSON<DiningRec[]>('/api/umd/dining')
}

import type { BehaviorSocketFrame } from '../types/contracts'

export type SocketStatus = 'connecting' | 'open' | 'closed'

const WS_URL =
  (import.meta.env.VITE_BACKEND_WS_URL as string | undefined) ?? 'ws://127.0.0.1:8765/ws/state'

const RECONNECT_DELAY_MS = 2000

export interface BehaviorSocketHandle {
  close: () => void
}

// Logs are intentionally verbose so a teammate can `npm run dev` and tell at
// a glance whether the socket is reaching the backend and what frames look
// like. Open DevTools (F12 in the Electron window) to see them.
const log = (...args: unknown[]): void => console.log('[ws]', ...args)
const warn = (...args: unknown[]): void => console.warn('[ws]', ...args)

export function connectBehaviorSocket(
  onFrame: (frame: BehaviorSocketFrame) => void,
  onStatus: (status: SocketStatus) => void
): BehaviorSocketHandle {
  let socket: WebSocket | null = null
  let reconnectTimer: number | null = null
  let closed = false
  let frameCount = 0
  let attempt = 0
  // CSP-blocked sockets in some Chromium builds fire `error` without firing
  // `close`. Without this guard, both handlers would race to reconnect.
  let teardownStarted = false

  const setStatus = (status: SocketStatus): void => {
    log(`status -> ${status}`)
    onStatus(status)
  }

  const teardown = (label: string): void => {
    if (teardownStarted) return
    teardownStarted = true
    setStatus('closed')
    socket = null
    if (closed) return
    log(`scheduling reconnect in ${RECONNECT_DELAY_MS}ms (after: ${label})`)
    reconnectTimer = window.setTimeout(open, RECONNECT_DELAY_MS)
  }

  const open = (): void => {
    if (closed) return
    attempt += 1
    teardownStarted = false
    log(`opening (attempt #${attempt}) ${WS_URL}`)
    setStatus('connecting')
    try {
      socket = new WebSocket(WS_URL)
    } catch (err) {
      warn('constructor threw; retrying', err)
      teardown('constructor threw')
      return
    }

    socket.onopen = (): void => {
      log(`open (readyState=${socket?.readyState})`)
      setStatus('open')
    }

    socket.onmessage = (event): void => {
      let frame: BehaviorSocketFrame
      try {
        frame = JSON.parse(event.data) as BehaviorSocketFrame
      } catch (err) {
        warn('malformed frame; dropping', err, event.data)
        return
      }
      frameCount += 1
      if (frameCount === 1 || frameCount % 5 === 0 || 'type' in frame) {
        log(`frame #${frameCount}`, frame)
      }
      onFrame(frame)
    }

    socket.onerror = (event): void => {
      warn('socket error', event)
      // Some failure modes (CSP block, certain network errors) fire `error`
      // without ever firing `close`. Without this we'd stay stuck on
      // "connecting" forever. teardown() is idempotent so a later `close`
      // event is a harmless no-op.
      teardown('error event')
    }

    socket.onclose = (event): void => {
      warn(
        `closed (code=${event.code} reason=${event.reason || '-'} clean=${event.wasClean}) after ${frameCount} frame(s)`
      )
      teardown(`close event code=${event.code}`)
    }
  }

  open()

  return {
    close: (): void => {
      log('handle.close() called by caller')
      closed = true
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (socket) {
        try {
          socket.close()
        } catch {
          // ignore
        }
        socket = null
      }
    }
  }
}

import type { BehaviorSocketFrame } from '../types/contracts'

export type SocketStatus = 'connecting' | 'open' | 'closed'

const WS_URL =
  (import.meta.env.VITE_BACKEND_WS_URL as string | undefined) ?? 'ws://127.0.0.1:8765/ws/state'

const RECONNECT_DELAY_MS = 2000

export interface BehaviorSocketHandle {
  close: () => void
}

const warn = (...args: unknown[]): void => console.warn('[ws]', ...args)

export function connectBehaviorSocket(
  onFrame: (frame: BehaviorSocketFrame) => void,
  onStatus: (status: SocketStatus) => void
): BehaviorSocketHandle {
  let socket: WebSocket | null = null
  let reconnectTimer: number | null = null
  let closed = false
  // Some Chromium failure modes (e.g. CSP block) fire `error` without firing
  // `close`. Without this guard, both handlers race to schedule reconnects.
  let teardownStarted = false

  const teardown = (): void => {
    if (teardownStarted) return
    teardownStarted = true
    onStatus('closed')
    socket = null
    if (closed) return
    reconnectTimer = window.setTimeout(open, RECONNECT_DELAY_MS)
  }

  const open = (): void => {
    if (closed) return
    teardownStarted = false
    onStatus('connecting')
    try {
      socket = new WebSocket(WS_URL)
    } catch (err) {
      warn('constructor threw', err)
      teardown()
      return
    }

    socket.onopen = (): void => onStatus('open')

    socket.onmessage = (event): void => {
      try {
        onFrame(JSON.parse(event.data) as BehaviorSocketFrame)
      } catch (err) {
        warn('malformed frame; dropping', err)
      }
    }

    socket.onerror = (event): void => {
      warn('socket error', event)
      teardown()
    }

    socket.onclose = (event): void => {
      if (!event.wasClean) {
        warn(`closed (code=${event.code} reason=${event.reason || '-'})`)
      }
      teardown()
    }
  }

  open()

  return {
    close: (): void => {
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

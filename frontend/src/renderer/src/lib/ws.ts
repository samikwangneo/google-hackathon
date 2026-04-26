import type { BehaviorSocketFrame } from '../types/contracts'

export type SocketStatus = 'connecting' | 'open' | 'closed'

const WS_URL =
  (import.meta.env.VITE_BACKEND_WS_URL as string | undefined) ??
  'ws://127.0.0.1:8765/ws/state'

const RECONNECT_DELAY_MS = 2000

export interface BehaviorSocketHandle {
  close: () => void
}

export function connectBehaviorSocket(
  onFrame: (frame: BehaviorSocketFrame) => void,
  onStatus: (status: SocketStatus) => void
): BehaviorSocketHandle {
  let socket: WebSocket | null = null
  let reconnectTimer: number | null = null
  let closed = false

  const open = (): void => {
    if (closed) return
    onStatus('connecting')
    try {
      socket = new WebSocket(WS_URL)
    } catch {
      onStatus('closed')
      reconnectTimer = window.setTimeout(open, RECONNECT_DELAY_MS)
      return
    }

    socket.onopen = (): void => onStatus('open')

    socket.onmessage = (event): void => {
      try {
        const frame = JSON.parse(event.data) as BehaviorSocketFrame
        onFrame(frame)
      } catch {
        // ignore malformed frame
      }
    }

    socket.onerror = (): void => {
      // surfacing handled by onclose
    }

    socket.onclose = (): void => {
      onStatus('closed')
      socket = null
      if (closed) return
      reconnectTimer = window.setTimeout(open, RECONNECT_DELAY_MS)
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

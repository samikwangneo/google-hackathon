import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'

import { brainChat, brainExplain } from '../lib/api'
import type { BrainChatMessage } from '../types/contracts'

type ChatBubble = BrainChatMessage & { id: number }

export function BrainPanel(): React.JSX.Element {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatBubble[]>([])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const nextIdRef = useRef(0)
  const messagesRef = useRef<HTMLDivElement | null>(null)

  const appendMessage = (msg: BrainChatMessage): ChatBubble => {
    const bubble: ChatBubble = { ...msg, id: nextIdRef.current++ }
    setMessages((prev) => [...prev, bubble])
    return bubble
  }

  useEffect(() => {
    let cancelled = false
    setPending(true)
    setError(null)
    brainExplain(null)
      .then((res) => {
        if (cancelled) return
        setSessionId(res.session_id)
        appendMessage({ role: 'assistant', text: res.reply })
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Could not read your screen')
      })
      .finally(() => {
        if (!cancelled) setPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const container = messagesRef.current
    if (!container) return
    const last = container.lastElementChild as HTMLElement | null
    if (!last) return
    container.scrollTop = last.offsetTop
  }, [messages, pending])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed || !sessionId || pending) return

    const history: BrainChatMessage[] = messages.map(({ role, text }) => ({ role, text }))
    appendMessage({ role: 'user', text: trimmed })
    setDraft('')
    setPending(true)
    setError(null)
    try {
      const res = await brainChat(sessionId, trimmed, history)
      appendMessage({ role: 'assistant', text: res.reply })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Brain failed to respond')
    } finally {
      setPending(false)
    }
  }

  return (
    <motion.section
      className="panel brain-panel"
      initial={{ opacity: 0, y: 18, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 18, scale: 0.96 }}
    >
      <div className="panel__eyebrow">Brain</div>
      <h2>What&apos;s on your screen</h2>
      <div className="brain-panel__messages" ref={messagesRef}>
        {messages.map((m) => (
          <div key={m.id} className={`brain-panel__bubble brain-panel__bubble--${m.role}`}>
            {m.text}
          </div>
        ))}
        {pending && (
          <div className="brain-panel__bubble brain-panel__bubble--assistant brain-panel__bubble--thinking">
            thinking…
          </div>
        )}
      </div>
      <form className="brain-panel__form" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder={sessionId ? 'Ask a follow-up…' : 'Reading your screen…'}
          value={draft}
          disabled={!sessionId || pending}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button
          type="submit"
          className="button"
          disabled={!sessionId || pending || draft.trim().length === 0}
        >
          Send
        </button>
      </form>
      {error && <p className="panel__error">{error}</p>}
    </motion.section>
  )
}

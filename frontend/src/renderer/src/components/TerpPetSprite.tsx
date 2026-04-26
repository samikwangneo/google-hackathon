import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from 'react'

export interface SpriteSheetConfig {
  src: string
  frameWidth?: number
  frameHeight?: number
  frames: number
  frameDurationMs?: number
}

export interface TerpPetSpriteHandle {
  start: () => void
  stop: () => void
  reset: () => void
}

interface TerpPetSpriteProps {
  sheet: SpriteSheetConfig
  autoPlay?: boolean
  loop?: boolean
  className?: string
  title?: string
  onComplete?: () => void
}

const DEFAULT_FRAME_SIZE = 704
const DEFAULT_FRAME_DURATION_MS = 135

export const TerpPetSprite = forwardRef<TerpPetSpriteHandle, TerpPetSpriteProps>(
  ({ sheet, autoPlay = true, loop = true, className, title, onComplete }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement | null>(null)
    const imageRef = useRef<HTMLImageElement | null>(null)
    const animationFrameRef = useRef<number | null>(null)
    const frameRef = useRef(0)
    const lastFrameAtRef = useRef(0)
    const playingRef = useRef(false)
    const completeRef = useRef(onComplete)

    const frameWidth = sheet.frameWidth ?? DEFAULT_FRAME_SIZE
    const frameHeight = sheet.frameHeight ?? DEFAULT_FRAME_SIZE
    const frameDurationMs = sheet.frameDurationMs ?? DEFAULT_FRAME_DURATION_MS

    useEffect(() => {
      completeRef.current = onComplete
    }, [onComplete])

    const cancelTick = useCallback((): void => {
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current)
        animationFrameRef.current = null
      }
    }, [])

    const drawFrame = useCallback(
      (frameIndex: number): void => {
        const canvas = canvasRef.current
        const image = imageRef.current
        if (!canvas || !image || !image.complete) return

        const context = canvas.getContext('2d')
        if (!context) return

        context.clearRect(0, 0, frameWidth, frameHeight)
        context.imageSmoothingEnabled = false
        context.drawImage(
          image,
          frameIndex * frameWidth,
          0,
          frameWidth,
          frameHeight,
          0,
          0,
          frameWidth,
          frameHeight
        )
      },
      [frameHeight, frameWidth]
    )

    const tick = useCallback(
      (timestamp: number): void => {
        if (!playingRef.current) return

        if (lastFrameAtRef.current === 0) {
          lastFrameAtRef.current = timestamp
        }

        if (timestamp - lastFrameAtRef.current >= frameDurationMs) {
          const nextFrame = frameRef.current + 1

          if (nextFrame >= sheet.frames) {
            if (loop) {
              frameRef.current = 0
            } else {
              frameRef.current = sheet.frames - 1
              playingRef.current = false
              drawFrame(frameRef.current)
              completeRef.current?.()
              return
            }
          } else {
            frameRef.current = nextFrame
          }

          drawFrame(frameRef.current)
          lastFrameAtRef.current = timestamp
        }

        animationFrameRef.current = window.requestAnimationFrame(tick)
      },
      [drawFrame, frameDurationMs, loop, sheet.frames]
    )

    const start = useCallback((): void => {
      if (playingRef.current) return
      playingRef.current = true
      lastFrameAtRef.current = 0
      cancelTick()
      animationFrameRef.current = window.requestAnimationFrame(tick)
    }, [cancelTick, tick])

    const stop = useCallback((): void => {
      playingRef.current = false
      cancelTick()
    }, [cancelTick])

    const reset = useCallback((): void => {
      frameRef.current = 0
      lastFrameAtRef.current = 0
      drawFrame(0)
    }, [drawFrame])

    useImperativeHandle(ref, () => ({ start, stop, reset }), [reset, start, stop])

    useEffect(() => {
      const image = new Image()
      image.decoding = 'async'
      image.onload = () => {
        imageRef.current = image
        reset()
        if (autoPlay) start()
      }
      image.src = sheet.src

      return () => {
        stop()
        image.onload = null
      }
      // Restart the animation when a different sheet or playback mode is selected.
    }, [
      autoPlay,
      loop,
      sheet.src,
      sheet.frames,
      frameWidth,
      frameHeight,
      frameDurationMs,
      reset,
      start,
      stop
    ])

    useEffect(() => {
      if (autoPlay) {
        start()
      } else {
        stop()
      }

      return cancelTick
    }, [autoPlay, cancelTick, start, stop])

    return (
      <canvas
        ref={canvasRef}
        className={className}
        width={frameWidth}
        height={frameHeight}
        aria-label={title}
        role={title ? 'img' : undefined}
      />
    )
  }
)

TerpPetSprite.displayName = 'TerpPetSprite'

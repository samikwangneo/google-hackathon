import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import { useTerpPetStore } from '../store'

export function EvolutionEffect(): React.JSX.Element {
  const showEvolution = useTerpPetStore((state) => state.showEvolution)
  const level = useTerpPetStore((state) => state.level)
  const clearEvolution = useTerpPetStore((state) => state.clearEvolution)

  useEffect(() => {
    if (!showEvolution) return
    const timeout = window.setTimeout(clearEvolution, 2400)
    return () => window.clearTimeout(timeout)
  }, [clearEvolution, showEvolution])

  return (
    <AnimatePresence>
      {showEvolution && (
        <motion.div
          className="evolution-effect"
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.2 }}
        >
          {Array.from({ length: 18 }).map((_, index) => (
            <motion.span
              // Static count and order: index is stable here.
              key={index}
              style={{ '--spark-angle': `${index * 20}deg` } as React.CSSProperties}
              initial={{ opacity: 0, x: 0, y: 0 }}
              animate={{
                opacity: [0, 1, 0],
                x: Math.cos((index * 20 * Math.PI) / 180) * 112,
                y: Math.sin((index * 20 * Math.PI) / 180) * 112
              }}
              transition={{ duration: 1.2, delay: index * 0.018 }}
            />
          ))}
          <motion.strong initial={{ y: 12 }} animate={{ y: 0 }}>
            Level {level}
          </motion.strong>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

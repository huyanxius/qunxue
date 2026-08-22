import { GrainGradient } from '@paper-design/shaders-react'
import { useEffect, useRef, useState } from 'react'

export function FoundationLightPaperShader() {
  const fieldRef = useRef<HTMLDivElement>(null)
  const [nearby, setNearby] = useState(false)
  const [reduceMotion, setReduceMotion] = useState(false)

  useEffect(() => {
    setReduceMotion(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)

    const field = fieldRef.current
    const section = field?.closest('#knowledge-preview')
    if (!field || !section) return

    if (typeof IntersectionObserver === 'undefined') {
      setNearby(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return
        const beforeKnowledge = entry.boundingClientRect.top > window.innerHeight + 640
        setNearby(!beforeKnowledge)
      },
      { rootMargin: '640px 0px', threshold: 0.01 },
    )
    observer.observe(section)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="foundation-knowledge__paper-field" ref={fieldRef} aria-hidden="true">
      {nearby && !reduceMotion ? (
        <GrainGradient
          className="foundation-knowledge__paper-flow"
          colorBack="#f7f7f2"
          colors={['#fbfaf4', '#d8d0c1', '#888b83', '#c2b29b']}
          softness={0.72}
          intensity={0.42}
          noise={0.18}
          shape="wave"
          fit="none"
          scale={0.72}
          rotation={344}
          speed={0.2}
          minPixelRatio={1}
          maxPixelCount={960 * 540}
          style={{ position: 'absolute', inset: 0 }}
        />
      ) : null}
    </div>
  )
}

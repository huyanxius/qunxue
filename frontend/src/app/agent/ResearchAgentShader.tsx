import { NeuroNoise } from '@paper-design/shaders-react'
import { useEffect, useState } from 'react'

function usePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ))

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updateMotionPreference = () => setReducedMotion(motionQuery.matches)
    motionQuery.addEventListener('change', updateMotionPreference)
    return () => motionQuery.removeEventListener('change', updateMotionPreference)
  }, [])

  return reducedMotion
}

export function ResearchAgentShader() {
  const reducedMotion = usePrefersReducedMotion()
  const supportsWebGl2 = typeof window !== 'undefined' && 'WebGL2RenderingContext' in window

  return (
    <div aria-hidden="true" className="research-agent-page__shader">
      {supportsWebGl2 ? (
        <NeuroNoise
          brightness={0.04}
          className="research-agent-page__shader-canvas"
          colorBack="#f7f4f2"
          colorFront="#94869a"
          colorMid="#c9c0cc"
          contrast={0.28}
          fit="none"
          frame={1840}
          maxPixelCount={960 * 540}
          minPixelRatio={1}
          rotation={10}
          scale={1.18}
          speed={reducedMotion ? 0 : 0.16}
          style={{ position: 'absolute', inset: 0 }}
        />
      ) : null}
    </div>
  )
}

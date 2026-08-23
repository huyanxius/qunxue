import { useEffect, useState } from 'react'
import { GrainGradient } from '@paper-design/shaders-react'

const appFramePalette = ['#f8f7f2', '#d6ddd8', '#8f9f97', '#c3ad94']

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

export function AppFrameShader() {
  const reducedMotion = usePrefersReducedMotion()

  if (typeof window === 'undefined' || !('WebGL2RenderingContext' in window)) {
    return null
  }

  return (
    <GrainGradient
      className="app-frame__shader-canvas"
      colorBack="#f7f7f3"
      colors={appFramePalette}
      softness={0.64}
      intensity={0.62}
      noise={0.18}
      shape="wave"
      fit="none"
      scale={0.64}
      rotation={344}
      speed={reducedMotion ? 0 : 1.1}
      frame={1200}
      minPixelRatio={1}
      maxPixelCount={960 * 540}
      style={{ position: 'absolute', inset: 0 }}
      aria-hidden="true"
    />
  )
}

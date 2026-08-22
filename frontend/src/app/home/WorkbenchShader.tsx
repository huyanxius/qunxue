import { useEffect, useState } from 'react'
import { GrainGradient } from '@paper-design/shaders-react'

const workbenchPalette = ['#f8f7f2', '#dde1dd', '#aeb8b2', '#cbbba7']

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

export function WorkbenchShader() {
  const reducedMotion = usePrefersReducedMotion()

  if (typeof window === 'undefined' || !('WebGL2RenderingContext' in window)) {
    return null
  }

  return (
    <GrainGradient
      className="work-home__shader-canvas"
      colorBack="#f7f7f3"
      colors={workbenchPalette}
      softness={0.72}
      intensity={0.54}
      noise={0.18}
      shape="wave"
      fit="none"
      scale={0.76}
      rotation={344}
      speed={reducedMotion ? 0 : 0.68}
      frame={1200}
      minPixelRatio={1}
      maxPixelCount={960 * 540}
      style={{ position: 'absolute', inset: 0 }}
      aria-hidden="true"
    />
  )
}

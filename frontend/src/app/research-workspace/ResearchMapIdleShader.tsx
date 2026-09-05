import { MeshGradient } from '@paper-design/shaders-react'
import { useEffect, useState } from 'react'
import './research-map-idle-shader.css'

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

export function ResearchMapIdleShader({
  colors = ['#f7f7f4', '#e8ede9', '#cbd6cf', '#ece5e1'],
}: { colors?: string[] }) {
  const reducedMotion = usePrefersReducedMotion()
  const supportsWebGl2 = typeof window !== 'undefined' && 'WebGL2RenderingContext' in window

  if (!supportsWebGl2) return null

  return (
    <div aria-hidden="true" className="research-map__idle-shader">
      <MeshGradient
        className="research-map__idle-shader-canvas"
        colors={colors}
        distortion={0.56}
        fit="cover"
        frame={980}
        grainMixer={0.05}
        grainOverlay={0.018}
        maxPixelCount={720 * 440}
        minPixelRatio={1}
        rotation={12}
        scale={1.05}
        speed={reducedMotion ? 0 : 0.16}
        swirl={0.13}
        style={{ position: 'absolute', inset: 0 }}
      />
    </div>
  )
}

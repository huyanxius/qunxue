import { useColorScheme } from '../../styles/useColorScheme'
import { Warp } from '@paper-design/shaders-react'
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

export function KnowledgeLibraryShader() {
  const dark = useColorScheme()
  const reducedMotion = usePrefersReducedMotion()
  const supportsWebGl2 = typeof window !== 'undefined' && 'WebGL2RenderingContext' in window

  return (
    <div className="knowledge-library__shader" aria-hidden="true">
      {supportsWebGl2 ? (
        <Warp
          className="knowledge-library__shader-canvas"
          colors={dark ? ['#20262b', '#34434f', '#566d81', '#414f5b'] : ['#f3f5f8', '#d7e0eb', '#8fa4bf', '#e8edf3']}
          distortion={0.12}
          fit="cover"
          frame={760}
          minPixelRatio={1}
          maxPixelCount={960 * 540}
          proportion={0.38}
          rotation={24}
          scale={1.3}
          shape="edge"
          shapeScale={0.82}
          softness={1}
          speed={reducedMotion ? 0 : 0.08}
          swirl={0.18}
          swirlIterations={3}
          style={{ position: 'absolute', inset: 0 }}
        />
      ) : null}
    </div>
  )
}

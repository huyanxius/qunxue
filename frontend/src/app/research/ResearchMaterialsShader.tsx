import { SimplexNoise } from '@paper-design/shaders-react'
import { useEffect, useState } from 'react'

function usePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ))

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return reducedMotion
}

/** 材料页用低对比的冷灰雾面，不复用工作台、画布或知识库的渐变。 */
export function ResearchMaterialsShader() {
  const reducedMotion = usePrefersReducedMotion()
  if (typeof window === 'undefined' || !('WebGL2RenderingContext' in window)) return null

  return (
    <div className="research-materials-page__shader" aria-hidden="true">
      <SimplexNoise
        colors={['#f2f7f7', '#d7e9e8', '#8fbfc0', '#e7efed']}
        maxPixelCount={960 * 540}
        minPixelRatio={1}
        softness={0.9}
        speed={reducedMotion ? 0 : 0.04}
        stepsPerColor={2}
        style={{ position: 'absolute', inset: 0 }}
      />
    </div>
  )
}

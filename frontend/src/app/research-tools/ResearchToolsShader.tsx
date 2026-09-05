import { useColorScheme } from '../../styles/useColorScheme'
import { MeshGradient } from '@paper-design/shaders-react'
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

/** 工具页用局部矿物黄光晕，与冷色研究页面区分，但不覆盖整张纸面。 */
export function ResearchToolsShader() {
  const dark = useColorScheme()
  const reducedMotion = usePrefersReducedMotion()
  if (typeof window === 'undefined' || !('WebGL2RenderingContext' in window)) return null

  return (
    <div className="research-tools-page__shader" aria-hidden="true">
      <MeshGradient
        className="research-tools-page__shader-canvas"
        colors={dark ? ['#25271e', '#414832', '#677449', '#494f39'] : ['#fafaf3', '#e6e8b8', '#9eaa52', '#d8dfbd']}
        distortion={0.42}
        fit="cover"
        frame={1080}
        grainMixer={0.035}
        grainOverlay={0.012}
        maxPixelCount={960 * 540}
        minPixelRatio={1}
        rotation={8}
        scale={1.08}
        speed={reducedMotion ? 0 : 0.08}
        swirl={0.1}
        style={{ position: 'absolute', inset: 0 }}
      />
    </div>
  )
}

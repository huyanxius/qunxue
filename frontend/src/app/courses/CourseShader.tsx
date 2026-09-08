import { SurfaceShader, type SkyPalette } from '../../styles/SurfaceShader'

// Preserve cloud contrast while keeping the reading surface light and the motion unobtrusive.
const COURSE_LIGHT: SkyPalette = ['#ffffff', '#fafcfb', '#e4ebe7', '#c7d5cf']
const COURSE_DARK: SkyPalette = ['#8caaa1', '#506d64', '#314b43', '#1f332d']

export function CourseShader() {
  return <SurfaceShader className="app-frame__shader-canvas" lightPalette={COURSE_LIGHT}
    darkPalette={COURSE_DARK} lightYshift={-0.38} motionScale={0.8} />
}

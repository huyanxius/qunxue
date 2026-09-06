import { SurfaceShader } from '../../styles/SurfaceShader'
import type { SkyPalette } from '../../styles/SurfaceShader'

// 工作台要白为主色、蓝只做强调，同时保住云的形状。
// 色板整体抬亮但 u_mid 压着不跟上去——四档明暗的落差没了，云就变成雾。
// u_low 铺在画面下沿，光调色板只能改它的深浅、改不了宽度，所以靠取景上抬把它推出视野。
const WORKBENCH_LIGHT: SkyPalette = ['#fafcfe', '#edf1f7', '#c2ccdb', '#8c94a4']
const WORKBENCH_YSHIFT = -0.32

export function AppFrameShader() {
  return <SurfaceShader className="app-frame__shader-canvas" lightPalette={WORKBENCH_LIGHT} lightYshift={WORKBENCH_YSHIFT} />
}

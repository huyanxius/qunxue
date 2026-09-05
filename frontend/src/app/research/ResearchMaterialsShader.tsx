import { ResearchMapIdleShader } from '../research-workspace/ResearchMapIdleShader'

const LIBRARY_COLORS = ['#f6f7f7', '#e4e8eb', '#c6ced4', '#dde2e6']

export function ResearchMaterialsShader() {
  return <ResearchMapIdleShader colors={LIBRARY_COLORS} darkColors={['#20262b', '#34434f', '#566d81', '#414f5b']} />
}

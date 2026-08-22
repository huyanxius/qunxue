import { GrainGradient, PaperTexture } from '@paper-design/shaders-react'

export function AccountPaperShader() {
  return (
    <>
      <PaperTexture
        className="account-paper-field__paper"
        colorFront="#ddd6c8"
        colorBack="#f7f7f2"
        contrast={0.18}
        roughness={0.28}
        fiber={0.16}
        fiberSize={0.24}
        crumples={0.08}
        crumpleSize={0.42}
        folds={0.18}
        foldCount={3}
        fade={0.45}
        drops={0.04}
        seed={12.6}
        fit="cover"
        scale={1.1}
        speed={0}
        minPixelRatio={1}
        maxPixelCount={1600 * 900}
        style={{ position: 'absolute', inset: 0 }}
        aria-hidden="true"
      />
      <GrainGradient
        className="account-paper-field__flow"
        colorBack="#f7f7f2"
        colors={['#fbfaf4', '#d8d0c1', '#888b83', '#c2b29b']}
        softness={0.72}
        intensity={0.52}
        noise={0.22}
        shape="wave"
        fit="none"
        scale={0.72}
        rotation={344}
        speed={0.72}
        minPixelRatio={1}
        maxPixelCount={1600 * 900}
        style={{ position: 'absolute', inset: 0 }}
        aria-hidden="true"
      />
    </>
  )
}

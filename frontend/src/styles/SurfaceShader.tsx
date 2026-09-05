import { useEffect, useRef } from 'react'
import { useColorScheme } from './useColorScheme'
import { stormLightFragment } from './storm-light.glsl'

/** Sky 使用原站的着色器、随机灰度噪声、参数映射和时间步长。 */
export function SurfaceShader({ className }: { className: string }) {
  const dark = useColorScheme()
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    const gl = canvas?.getContext('webgl')
    if (!canvas || !gl) return
    const program = gl.createProgram()!
    const shaders = [
      [gl.VERTEX_SHADER, 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'],
      [gl.FRAGMENT_SHADER, stormLightFragment],
    ] as const
    const compiled = shaders.map(([type, source]) => {
      const shader = gl.createShader(type)!
      gl.shaderSource(shader, source); gl.compileShader(shader)
      gl.attachShader(program, shader)
      return shader
    })
    gl.bindAttribLocation(program, 0, 'p'); gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error(gl.getProgramInfoLog(program))
      compiled.forEach(shader => gl.deleteShader(shader)); gl.deleteProgram(program)
      return
    }
    gl.useProgram(program)
    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
    const texture = gl.createTexture()
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texture)
    const noise = new Uint8Array(256 * 256 * 4)
    for (let i = 0; i < 256 * 256; i++) {
      const value = Math.random() * 256 | 0
      noise[i * 4] = value; noise[i * 4 + 1] = value; noise[i * 4 + 2] = value; noise[i * 4 + 3] = 255
    }
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 256, 0, gl.RGBA, gl.UNSIGNED_BYTE, noise)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    const uniform = (name: string) => gl.getUniformLocation(program, name)
    gl.uniform1i(uniform('u_noise'), 0)
    const palette = dark ? ['#87909f', '#515b6d', '#343f52', '#202a3b'] : ['#E8EAEE', '#CDD3D9', '#B7BDC9', '#8C94A4']
    ;['u_high', 'u_main', 'u_mid', 'u_low'].forEach((name, index) => {
      const color = parseInt(palette[index].slice(1), 16)
      gl.uniform3f(uniform(name), (color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)
    })
    gl.uniform1f(uniform('u_nscale'), .35 + .92 * 1.15)
    gl.uniform1f(uniform('u_warp'), .10 * .47)
    gl.uniform1f(uniform('u_wind'), 1 * .36)
    gl.uniform2f(uniform('u_dirv'), 1, 0)
    const resolution = uniform('u_res'), clock = uniform('u_t')
    let time = 20.75, last = 0, request = 0
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const draw = (now: number) => {
      if (last && !motion.matches) time += .58 * 1.2 * Math.min(.05, (now - last) / 1000)
      last = now
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.uniform2f(resolution, canvas.width, canvas.height); gl.uniform1f(clock, time)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      if (!motion.matches && !document.hidden) request = requestAnimationFrame(draw)
    }
    const restart = () => { cancelAnimationFrame(request); last = 0; request = requestAnimationFrame(draw) }
    const observer = new ResizeObserver(() => {
      const rect = canvas.getBoundingClientRect()
      const ratio = Math.min(3, window.devicePixelRatio || 1)
      const scale = Math.min(1, 2560 / Math.max(1, rect.width * ratio, rect.height * ratio))
      canvas.width = Math.max(1, Math.round(rect.width * ratio * scale))
      canvas.height = Math.max(1, Math.round(rect.height * ratio * scale))
      restart()
    })
    observer.observe(canvas); restart()
    motion.addEventListener('change', restart); document.addEventListener('visibilitychange', restart)
    return () => {
      cancelAnimationFrame(request); observer.disconnect()
      motion.removeEventListener('change', restart); document.removeEventListener('visibilitychange', restart)
      gl.deleteTexture(texture); gl.deleteBuffer(buffer)
      compiled.forEach(shader => gl.deleteShader(shader)); gl.deleteProgram(program)
    }
  }, [dark])
  return <canvas ref={ref} className={className} data-renderer="feralui-sky" data-color-scheme={dark ? 'dark' : 'light'} aria-hidden="true"
    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 1 }} />
}

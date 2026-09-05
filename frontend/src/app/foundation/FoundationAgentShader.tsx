import { useColorScheme } from '../../styles/useColorScheme'
import { ShaderMount } from '@paper-design/shaders-react'

const grainFragmentShader = `#version 300 es
precision mediump float;

uniform float u_time;
uniform float u_dark;
uniform vec2 u_resolution;
out vec4 fragColor;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
    mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0)), f.x),
    f.y
  );
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 4; i++) {
    value += amplitude * valueNoise(p);
    p = mat2(0.82, -0.57, 0.57, 0.82) * p * 2.03;
    amplitude *= 0.5;
  }
  return value;
}

vec3 grainField(vec2 uv, float t) {
  float aspect = u_resolution.x / max(1.0, u_resolution.y);
  vec2 p = uv - 0.5;
  p.x *= aspect;
  p = mat2(cos(-0.105), -sin(-0.105), sin(-0.105), cos(-0.105)) * p;

  float drift = fbm(p * 1.65 + vec2(t * 0.055, -t * 0.032));
  float wave = sin(p.x * 1.35 + p.y * 1.1 - t * 0.22 + drift * 1.6);
  float bands = smoothstep(0.18, 0.9, 0.5 + 0.5 * wave + (drift - 0.5) * 0.24);

  vec3 color = mix(mix(vec3(0.0824), vec3(0.10, 0.115, 0.105), u_dark), mix(vec3(0.1373, 0.1412, 0.1216), vec3(0.17, 0.20, 0.17), u_dark), smoothstep(0.0, 0.42, bands));
  color = mix(color, mix(vec3(0.2275, 0.2667, 0.2667), vec3(0.25, 0.31, 0.29), u_dark), smoothstep(0.38, 0.7, bands) * 0.72);
  color = mix(color, mix(vec3(0.5020), vec3(0.40, 0.45, 0.40), u_dark), smoothstep(0.66, 0.88, bands) * 0.48);
  color = mix(color, mix(vec3(0.8980, 0.9020, 0.8824), vec3(0.58, 0.63, 0.56), u_dark), smoothstep(0.84, 1.0, bands) * 0.34);

  color += (hash21(floor(gl_FragCoord.xy * 0.72)) - 0.5) * 0.045;
  color += (fbm(p * 3.1 + vec2(t * 0.06, -t * 0.04)) - 0.5) * 0.035;
  return color;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution;
  fragColor = vec4(grainField(uv, u_time), 1.0);
}`

export function FoundationAgentShader() {
  const dark = useColorScheme()
  const reduceMotion = typeof window !== 'undefined'
    && (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)

  return (
    <ShaderMount
      className="foundation-agent__background-shader"
      fragmentShader={grainFragmentShader}
      uniforms={{ u_dark: dark ? 1 : 0 }}
      speed={reduceMotion ? 0 : 0.62}
      minPixelRatio={1}
      maxPixelCount={1280 * 720}
      style={{ position: 'absolute', inset: 0 }}
      aria-hidden="true"
    />
  )
}

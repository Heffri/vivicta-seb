import { useEffect, useRef, useState } from 'react'
import { fragmentShader } from './orb-shader'

// ElevenLabs' MIT orb shader, rendered locally with no CDN, audio or account.
// Three is loaded only when Ask is mounted; reduced-motion users get a still orb.
export function ThinkingOrb({ thinking = false, className = '' }: { thinking?: boolean; className?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const state = useRef(thinking)
  const [ready, setReady] = useState(false)
  useEffect(() => { state.current = thinking }, [thinking])

  useEffect(() => {
    let disposed = false
    let cleanup = () => {}
    void import('three').then(THREE => {
      if (disposed || !canvas.current) return
      const element = canvas.current
      const gl = element.getContext('webgl2', { alpha: true, antialias: true })
      if (!gl) return // The CSS fallback remains visible on machines without WebGL.
      const renderer = new THREE.WebGLRenderer({ canvas: element, context: gl, alpha: true, antialias: true })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
      const scene = new THREE.Scene()
      const camera = new THREE.OrthographicCamera(-1.12, 1.12, 1.12, -1.12, 0.1, 10)
      camera.position.z = 2
      // Smooth periodic noise replaces the upstream externally hosted texture.
      const size = 128, noise = new Uint8Array(size * size * 4)
      for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
        const a = x / size * Math.PI * 2, b = y / size * Math.PI * 2
        const n = Math.round(156 + 25 * Math.sin(a * 3 + Math.cos(b * 2)) + 20 * Math.cos(b * 4 + Math.sin(a * 2)) + 10 * Math.sin(a * 7 + b * 5))
        const offset = (y * size + x) * 4
        noise[offset] = noise[offset + 1] = noise[offset + 2] = n
        noise[offset + 3] = 255
      }
      const texture = new THREE.DataTexture(noise, size, size)
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping
      texture.minFilter = texture.magFilter = THREE.LinearFilter
      texture.needsUpdate = true
      const uniforms = {
        uColor1: { value: new THREE.Color('#7e81c9') }, uColor2: { value: new THREE.Color('#b1eeee') },
        uOffsets: { value: new Float32Array([0.3, 1.1, 2.2, 3.4, 4.1, 5.2, 6.0]) },
        uPerlinTexture: { value: texture }, uTime: { value: 4 }, uAnimation: { value: 0.4 },
        uInverted: { value: 1 }, uInputVolume: { value: 0.2 }, uOutputVolume: { value: 0.4 }, uOpacity: { value: 1 },
      }
      const material = new THREE.ShaderMaterial({ uniforms, fragmentShader, transparent: true,
        vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      })
      const geometry = new THREE.CircleGeometry(1, 96)
      scene.add(new THREE.Mesh(geometry, material))
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
      let frame = 0, last = 0, visible = true
      const render = () => {
        uniforms.uInverted.value = document.documentElement.dataset.tone === 'light' ? 0 : 1
        renderer.render(scene, camera)
      }
      const tick = (now: number) => {
        if (disposed) return
        frame = requestAnimationFrame(tick)
        if (reduced.matches || document.hidden || !visible || now - last < 32) { if (document.hidden || !visible) last = now; return }
        const delta = Math.min((now - last) / 1000, 0.05)
        last = now
        uniforms.uTime.value += delta * 0.5
        uniforms.uAnimation.value += delta * (state.current ? 0.6 : 0.12)
        uniforms.uInputVolume.value += ((state.current ? 0.4 : 0.15) - uniforms.uInputVolume.value) * 0.1
        uniforms.uOutputVolume.value = state.current ? 0.5 + Math.sin(now / 1000) * 0.1 : 0.3
        render()
      }
      const resize = new ResizeObserver(() => {
        if (element.clientWidth && element.clientHeight) { renderer.setSize(element.clientWidth, element.clientHeight, false); render() }
      })
      resize.observe(element)
      const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
      intersection.observe(element)
      const tone = new MutationObserver(render)
      tone.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tone'] })
      const onMotionChange = () => { cancelAnimationFrame(frame); render(); if (!reduced.matches) frame = requestAnimationFrame(tick) }
      const onContextLost = (event: Event) => { event.preventDefault(); cancelAnimationFrame(frame); setReady(false) }
      element.addEventListener('webglcontextlost', onContextLost)
      reduced.addEventListener('change', onMotionChange)
      renderer.setSize(element.clientWidth || 120, element.clientHeight || 120, false)
      render()
      setReady(true)
      if (!reduced.matches) frame = requestAnimationFrame(tick)
      cleanup = () => {
        cancelAnimationFrame(frame); resize.disconnect(); intersection.disconnect(); tone.disconnect()
        reduced.removeEventListener('change', onMotionChange); element.removeEventListener('webglcontextlost', onContextLost)
        geometry.dispose(); material.dispose(); texture.dispose(); renderer.dispose()
      }
    }).catch(() => { if (!disposed) setReady(false) })
    return () => { disposed = true; cleanup() }
  }, [])

  return <div aria-hidden="true" data-orb-state={thinking ? 'thinking' : 'idle'} className={`relative shrink-0 ${className}`}>
    <div className={`absolute inset-[9%] rounded-full bg-[radial-gradient(circle_at_30%_25%,#a5f3fc,#6366f1_48%,#252453_80%)] shadow-[0_0_36px_#6366f130] ${ready ? 'opacity-0' : ''}`} />
    <canvas ref={canvas} className={`relative h-full w-full ${ready ? 'opacity-100' : 'opacity-0'}`} />
  </div>
}

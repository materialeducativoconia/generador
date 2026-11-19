import { Component, createElement, type ReactNode } from 'react'
import * as React from 'react'
import { transform } from 'sucrase'
import { AbsoluteFill, Easing, interpolate, random, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { MOTION_ICONS } from './motion'
import { FONT, type Look, LOOKS } from './spec'

/* «Escena a medida»: a scene Claude programmed as a Remotion component (backend app/coder.py says what it may use).
 * The code is compiled here, once per version, and run with only the names it is given: the browser's globals are
 * shadowed. A scene that does not compile or throws while drawing shows its template instead, so a video never breaks. */

export type SceneProps = { frame: number; fps: number; dur: number; width: number; height: number; look: { bg: string; ink: string; accent: string }
  caption: string; voice: string; text: string; title: string; book: string; step: number | null }
type Compiled = { Scene: React.ComponentType<SceneProps> } | { error: string }

function Icon({ name, size = 48, color = 'currentColor', stroke = 2 }: { name: string; size?: number; color?: string; stroke?: number }) {
  const d = MOTION_ICONS[name as keyof typeof MOTION_ICONS] ?? MOTION_ICONS.sparkle
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ display: 'block', flex: 'none' }}>
      <path d={d} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

const GIVEN = { React, AbsoluteFill, interpolate, spring, Easing, random, Icon, FONT }
const HIDDEN = ['window', 'document', 'globalThis', 'self', 'top', 'parent', 'frames', 'fetch', 'XMLHttpRequest', 'WebSocket', 'localStorage',
  'sessionStorage', 'indexedDB', 'navigator', 'location', 'history', 'Function', 'importScripts', 'setTimeout', 'setInterval']
const cache = new Map<string, Compiled>()

export function compileScene(code: string): Compiled {
  const kept = cache.get(code)
  if (kept) return kept
  let out: Compiled
  try {
    const js = transform(code, { transforms: ['jsx'], jsxRuntime: 'classic', production: true }).code
    const make = new Function(...Object.keys(GIVEN), ...HIDDEN, `"use strict";\n${js}\nreturn Scene;`)
    const Scene = make(...Object.values(GIVEN), ...HIDDEN.map(() => undefined))
    out = typeof Scene === 'function' ? { Scene } : { error: 'El código no define Scene.' }
  } catch (e) {
    out = { error: e instanceof Error ? e.message : String(e) }
  }
  if (cache.size > 200) cache.clear()
  cache.set(code, out)
  return out
}

/** Claude's scene, in its frame; the template while it cannot be drawn. */
export function CustomScene({ code, fallback, ...props }: Omit<SceneProps, 'frame' | 'fps' | 'width' | 'height' | 'look'> & { code: string; look: Look; fallback: ReactNode }) {
  const compiled = compileScene(code)
  if ('error' in compiled) return <>{fallback}</>
  return <Guard key={code} fallback={fallback}><Run Scene={compiled.Scene} {...props} /></Guard>
}

function Run({ Scene, look, ...props }: Omit<SceneProps, 'frame' | 'fps' | 'width' | 'height' | 'look'> & { Scene: React.ComponentType<SceneProps>; look: Look }) {
  const frame = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const { bg, ink, accent } = LOOKS[look]
  return (
    <AbsoluteFill style={{ background: bg, color: ink, fontFamily: FONT, overflow: 'hidden' }}>
      {createElement(Scene, { ...props, frame, fps, width, height, look: { bg, ink, accent } })}
    </AbsoluteFill>
  )
}

class Guard extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(e: unknown) { console.warn('Escena a medida falló; se muestra la plantilla.', e) }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

/** Why a scene's code cannot be drawn (the editor shows it), or null. */
export function codeProblem(code: string): string | null {
  const c = compileScene(code)
  return 'error' in c ? c.error : null
}

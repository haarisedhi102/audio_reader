#!/usr/bin/env node
/**
 * Headless smoke test against the Even Hub simulator's automation plane.
 * Asserts: app boots, renders text, playback advances the display, double-tap exits.
 *
 *   evenhub-simulator http://localhost:5173 --automation-port 9898
 *   node scripts/smoke.mjs
 */
const BASE = process.env.SIM ?? 'http://127.0.0.1:9898'
const READY = '[glasses-reader] ready'

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function json(path, init) {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}
async function shot() {
  const res = await fetch(`${BASE}/api/screenshot/glasses`)
  const buf = new Uint8Array(await res.arrayBuffer())
  return buf
}
async function lit(buf) {
  // RGBA PNG. Decode via the webview-less path: use the simulator's own console
  // to avoid a PNG dependency — instead compare byte length and use the app's
  // reported state. For a true lit-pixel count, decode with sharp/pngjs.
  return buf.byteLength
}
async function waitReady(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  let since = 0
  while (Date.now() < deadline) {
    const { entries } = await json(`/api/console?since_id=${since}`)
    for (const e of entries) {
      since = Math.max(since, e.id)
      if (e.message.includes(READY)) return e.message
    }
    await sleep(250)
  }
  throw new Error('app never signalled ready')
}

const info = await waitReady()
console.log('ready:', info)

const boot = await shot()
if (boot.byteLength < 1000) throw new Error('framebuffer suspiciously empty at boot')
console.log('boot framebuffer bytes:', boot.byteLength)

// Tap = play. Then confirm the framebuffer changes (clock + line advance).
await json('/api/input', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'click' }) })
await sleep(5000)
const playing = await shot()
if (playing.byteLength === boot.byteLength) throw new Error('framebuffer identical after 5 s of playback — is the audio clock running?')
console.log('framebuffer after 5 s playback:', playing.byteLength, '(changed)')

// Double-tap = exit.
await json('/api/input', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'double_click' }) })
await sleep(800)
const after = await shot()
console.log('framebuffer after exit:', after.byteLength)
if (after.byteLength > boot.byteLength * 0.5) throw new Error('page did not shut down on double-tap')

const { entries } = await json('/api/console')
const errors = entries.filter(e => e.level === 'error')
if (errors.length) {
  console.error('console errors:', errors.map(e => e.message))
  process.exit(1)
}
console.log('OK')

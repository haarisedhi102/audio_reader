import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
  MenuContainerProperty,
  MenuItemProperty,
} from '@evenrealities/even_hub_sdk'
import { loadLibrary, loadCues, audioUrl, type Book, type Track, type Cue } from './library'
import { wrapText } from './wrap'

declare const __APP_VERSION__: string

// ---------------------------------------------------------------- layout
const W = 576
const PAD = 4
const HEADER_H = 36
const BODY_Y = 38
const BODY_H = 208
const FOOTER_Y = 250
const FOOTER_H = 36
const LINE_HEIGHT = 27
const INNER_W = W - 2 * PAD
const HINT = 'tap play/pause · swipe ±30 · hold hide · 2× exit'
const MARK_W = 22
const VISIBLE_LINES = Math.floor((BODY_H - 2 * PAD) / LINE_HEIGHT) // 7

// ---------------------------------------------------------------- model
interface Line { text: string; cue: number }
interface TrackModel { lines: Line[]; cueFirst: number[]; cueLines: number[] }

function buildModel(cues: Cue[]): TrackModel {
  const lines: Line[] = []
  const cueFirst: number[] = []
  const cueLines: number[] = []
  cues.forEach((cue, ci) => {
    const wrapped = wrapText(cue.text, INNER_W - MARK_W)
    cueFirst.push(lines.length)
    cueLines.push(wrapped.length)
    for (const text of wrapped) lines.push({ text, cue: ci })
  })
  return { lines, cueFirst, cueLines }
}

function cueAt(cues: Cue[], t: number): number {
  let lo = 0, hi = cues.length - 1, best = 0
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (cues[mid].t0 <= t) { best = mid; lo = mid + 1 } else { hi = mid - 1 }
  }
  return best
}

// ---------------------------------------------------------------- state
const audio = new Audio()
audio.preload = 'auto'

type SavedPos = { id?: string; track?: number; offset?: number }
let saved: SavedPos = {}
let storageStatus = 'unknown'

const qs = new URLSearchParams(location.search)
console.log('[glasses-reader] url', location.href)
const startAt = Number(qs.get('seek') ?? NaN)

let books: Book[] = []
let bookIndex = 0
let trackIndex = 0
let track: Track | null = null
let model: TrackModel = { lines: [], cueFirst: [], cueLines: [] }
let windowStart = -1
let activeLine = -1
let resumeNote = ''
let screenOff = false

const el = {
  status: () => document.getElementById('status')!,
  now: () => document.getElementById('now')!,
  list: () => document.getElementById('books')!,
  scrub: () => document.getElementById('scrub') as HTMLInputElement,
  play: () => document.getElementById('play')!,
  hide: () => document.getElementById('hide')!,
  ver: () => document.getElementById('ver'),
  events: () => document.getElementById('events'),
}

function trace(msg: string) {
  const n = el.events()
  if (n) n.textContent = msg
}

// ---------------------------------------------------------------- bridge
let bridge: Awaited<ReturnType<typeof waitForEvenAppBridge>> | null = null
try {
  bridge = await Promise.race([
    waitForEvenAppBridge(),
    new Promise<null>(r => setTimeout(() => r(null), 3000)),
  ])
} catch {
  bridge = null
}

/** The Even app exposes native storage; a WebView's own localStorage is not
 * reliable across launches. Fall back to it only in a plain browser. */
const store = {
  async get(key: string): Promise<string | null> {
    if (bridge) {
      try { return (await bridge.getLocalStorage(key)) || null } catch { /* fall through */ }
    }
    try { return localStorage.getItem(key) } catch { return null }
  },
  async set(key: string, value: string): Promise<boolean> {
    if (bridge) {
      try { if (await bridge.setLocalStorage(key, value)) return true } catch { /* fall through */ }
    }
    try { localStorage.setItem(key, value); return true } catch { return false }
  },
}

/** Restore state that has to be known before the first render. */
async function loadSaved() {
  const raw = await store.get('reader.pos')
  if (raw) {
    try { saved = JSON.parse(raw) } catch { saved = {} }
  }
  storageStatus = (await store.set('reader.probe', '1')) ? (bridge ? 'native' : 'localStorage') : 'unavailable'
  if (!qs.get('track')) trackIndex = Number(saved.track ?? 0)
  console.log('[glasses-reader] build', __APP_VERSION__, 'storage', storageStatus,
              'saved', JSON.stringify(saved))
}
await loadSaved()

const verEl = el.ver()
if (verEl) verEl.textContent = `v${__APP_VERSION__}`

async function createContainers() {
  if (!bridge) return
  const header = new TextContainerProperty({
    xPosition: 0, yPosition: 0, width: W, height: HEADER_H,
    borderWidth: 0, paddingLength: PAD, containerID: 1, containerName: 'header',
    content: `Reader v${__APP_VERSION__}`, isEventCapture: 0, textColor: 2,
  })
  const body = new TextContainerProperty({
    xPosition: 0, yPosition: BODY_Y, width: W, height: BODY_H,
    borderWidth: 0, paddingLength: PAD, containerID: 2, containerName: 'body',
    content: ' ', isEventCapture: 1, textColor: 4,
  })
  const footer = new TextContainerProperty({
    xPosition: 0, yPosition: FOOTER_Y, width: W, height: FOOTER_H,
    borderWidth: 0, paddingLength: PAD, containerID: 3, containerName: 'footer',
    content: HINT, isEventCapture: 0, textColor: 2,
  })
  // The OS owns tap-then-hold, so the reliable way to reach "hide" from the
  // glasses is an item in that menu. 1 = hide, 2 = show.
  const menu = new MenuContainerProperty({
    menuItems: [
      new MenuItemProperty({ itemID: 1, itemName: 'Hide text' }),
      new MenuItemProperty({ itemID: 2, itemName: 'Show text' }),
      new MenuItemProperty({ itemID: 3, itemName: 'Exit' }),
    ],
  })
  const rc = await bridge.createStartUpPageContainer(
    new CreateStartUpPageContainer({
      containerTotalNum: 3, textObject: [header, body, footer], menuObject: menu,
    }),
  )
  if (rc !== 0) console.error('createStartUpPageContainer failed', rc)
}

let writing: Promise<unknown> = Promise.resolve()
function push(containerID: number, containerName: string, content: string) {
  if (!bridge) return
  writing = writing.then(() =>
    bridge!.textContainerUpgrade(new TextContainerUpgrade({ containerID, containerName, content })),
  ).catch(e => {
    console.error('upgrade failed', e)
    trace(`push failed: ${containerName}`)
  })
}

function showError(title: string, detail: string) {
  el.status().textContent = `${title} — ${detail}`
  console.log('[glasses-reader] error', title, detail)
  push(1, 'header', title)
  push(2, 'body', detail)
  push(3, 'footer', 'check the library URL — see docs/hosting.md')
}

/** Long-press blanks the display and keeps playing: listen without reading. */
function setScreenOff(off: boolean) {
  screenOff = off
  if (off) {
    push(1, 'header', ' ')
    push(2, 'body', ' ')
    push(3, 'footer', ' ')
    el.status().textContent = 'listening — screen hidden (tap to show)'
    trace('hidden — tap to show')
    el.hide().textContent = 'show'
  } else {
    push(3, 'footer', HINT)
    el.hide().textContent = 'hide'
    trace('visible')
    renderChrome()
    renderLines(true)
  }
}

// ---------------------------------------------------------------- playback
function fmt(sec: number) {
  const s = Math.max(0, Math.floor(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function renderChrome() {
  if (!track) return
  const book = books[bookIndex]
  const label = book.tracks.length > 1 ? `${track.title} — ` : ''
  const header = `${label}${fmt(audio.currentTime)} / ${fmt(audio.duration || 0)}`
  if (!screenOff) push(1, 'header', header.length > 95 ? header.slice(0, 95) : header)
  if (!screenOff) {
    el.status().textContent =
      `${book.title} · ${track.title}${resumeNote}` +
      (storageStatus === 'unavailable' ? ' · storage unavailable' : '')
  }
  el.play().textContent = audio.paused ? '▶︎' : '❚❚'
  const s = el.scrub()
  s.max = String(Math.max(1, audio.duration || 1))
  s.value = String(audio.currentTime)
}

function renderLines(force = false) {
  if (!track) return
  const cues = track.cuesData
  const t = audio.currentTime
  const ci = cueAt(cues, t)
  const cue = cues[ci]
  if (!cue) return
  const span = Math.max(0.001, cue.t1 - cue.t0)
  const progress = Math.min(0.999, Math.max(0, (t - cue.t0) / span))
  const nLines = model.cueLines[ci] ?? 1
  const lineInCue = Math.min(nLines - 1, Math.floor(progress * nLines))
  const line = model.cueFirst[ci] + lineInCue

  const maxStart = Math.max(0, model.lines.length - VISIBLE_LINES)
  const start = Math.min(maxStart, Math.max(0, line - 2))
  if (!force && start === windowStart && line === activeLine) return
  const lineMoved = line !== activeLine
  windowStart = start
  activeLine = line

  const out: string[] = []
  for (let i = start; i < Math.min(model.lines.length, start + VISIBLE_LINES); i++) {
    out.push((i === line ? '> ' : '  ') + model.lines[i].text)
  }
  if (!screenOff) push(2, 'body', out.join('\n'))
  if (lineMoved) el.now().textContent = model.lines[line]?.text ?? ''
}

function applyStartOffset(offset: number) {
  if (!(offset > 0)) return
  const set = () => {
    const d = audio.duration
    audio.currentTime = Number.isFinite(d) && d > 1 ? Math.min(offset, d - 1) : offset
    renderLines(true)
    renderChrome()
  }
  // currentTime before metadata is unreliable across webviews; wait for it
  if (audio.readyState >= 1) set()
  else audio.addEventListener('loadedmetadata', set, { once: true })
}

let verifiedStore = false
function savePos() {
  if (!track) return
  const payload = JSON.stringify({
    id: books[bookIndex].id, track: trackIndex, offset: Math.floor(audio.currentTime),
  })
  void store.set('reader.pos', payload).then(async ok => {
    if (verifiedStore) return
    verifiedStore = true
    // one read-back per launch: proves the native store works, or that it lies
    const back = await store.get('reader.pos')
    console.log('[glasses-reader] storage roundtrip',
                back === payload ? 'ok' : `mismatch${ok ? '' : ' (set failed)'}: ${back}`)
  })
}

async function select(bookIdx: number, trackIdx = 0, autoplay = false) {
  bookIndex = bookIdx
  trackIndex = trackIdx
  const book = books[bookIndex]
  const ref = book.tracks[trackIndex]
  const cues = await loadCues(book, ref)
  track = { ...ref, cuesData: cues }
  model = buildModel(cues)
  windowStart = -1
  activeLine = -1

  audio.src = audioUrl(book, ref)
  const resume = Number.isFinite(startAt)
    ? startAt
    : saved.id === book.id && saved.track === trackIdx ? Number(saved.offset ?? 0) : 0
  if (resume > 0) console.log('[glasses-reader] resume', book.id, trackIdx, resume)
  resumeNote = resume > 0 ? ` · resumed ${fmt(resume)}` : ''
  applyStartOffset(resume)
  if (autoplay) void audio.play().catch(() => {})

  document.querySelectorAll('.book').forEach(n => n.classList.remove('on'))
  document.querySelector(`[data-book="${bookIdx}"]`)?.classList.add('on')
  renderChrome()
  renderLines(true)
}

function toggle() {
  if (audio.paused) void audio.play().catch(() => {})
  else audio.pause()
  renderChrome()
}


function seek(delta: number) {
  audio.currentTime = Math.max(0, Math.min((audio.duration || 0) - 0.2, audio.currentTime + delta))
  renderLines(true)
  renderChrome()
}

// ---------------------------------------------------------------- events
function eventTypeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

if (bridge) {
  bridge.onEvenHubEvent(event => {
    const sysType = eventTypeOf(event.sysEvent)
    const textType = eventTypeOf(event.textEvent)
    trace(`ev sys=${sysType ?? '-'} txt=${textType ?? '-'} off=${screenOff ? 1 : 0}`)
    const menuItem = event.menuItemClickEvent?.itemID
    if (menuItem !== undefined) console.log('[glasses-reader] menu item', menuItem)
    if (menuItem === 1) { setScreenOff(true); return }
    if (menuItem === 2) { setScreenOff(false); return }
    if (menuItem === 3) { bridge!.shutDownPageContainer(1); return }
    if (sysType === OsEventTypeList.FOREGROUND_ENTER_EVENT) {
      // coming back from the menu: repaint whatever the current state is
      if (screenOff) setScreenOff(true)
      else { renderChrome(); renderLines(true) }
      return
    }
    if (sysType === OsEventTypeList.FOREGROUND_EXIT_EVENT) { savePos(); return }
    if (sysType === OsEventTypeList.DOUBLE_CLICK_EVENT || textType === OsEventTypeList.DOUBLE_CLICK_EVENT) {
      bridge!.shutDownPageContainer(1)
      return
    }
    // the release half of a long press is not an input of its own
    if (sysType === OsEventTypeList.LONG_PRESS_RELEASE_EVENT ||
        textType === OsEventTypeList.LONG_PRESS_RELEASE_EVENT) return
    if (sysType === OsEventTypeList.LONG_PRESS_EVENT || textType === OsEventTypeList.LONG_PRESS_EVENT) {
      setScreenOff(!screenOff)
      return
    }
    // while hidden, the first input only brings the text back
    if (screenOff) { setScreenOff(false); return }
    if (textType === OsEventTypeList.SCROLL_TOP_EVENT) { seek(-30); return }
    if (textType === OsEventTypeList.SCROLL_BOTTOM_EVENT) { seek(30); return }
    if (sysType === OsEventTypeList.CLICK_EVENT || textType === OsEventTypeList.CLICK_EVENT) toggle()
  })
}

audio.addEventListener('timeupdate', () => renderLines())
audio.addEventListener('durationchange', () => renderChrome())
audio.addEventListener('ended', async () => {
  if (!track) return
  if (trackIndex + 1 < books[bookIndex].tracks.length) await select(bookIndex, trackIndex + 1, true)
})

setInterval(() => {
  renderLines()
  renderChrome()
  savePos()
}, 1000)

audio.addEventListener('pause', savePos)
addEventListener('pagehide', savePos)
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') savePos()
})

// ---------------------------------------------------------------- companion UI
function renderBookList() {
  el.list().innerHTML = books.map((b, i) =>
    `<button data-book="${i}" class="book${i === bookIndex ? ' on' : ''}">
      <strong>${b.title}</strong><span>${b.author}${b.tracks.length > 1 ? ` · ${b.tracks.length} parts` : ''}</span>
    </button>`).join('')
}

el.list().addEventListener('click', e => {
  const btn = (e.target as HTMLElement).closest('button[data-book]') as HTMLButtonElement | null
  if (!btn) return
  void select(Number(btn.dataset.book), 0, false)
})

el.play().addEventListener('click', toggle)
el.hide().addEventListener('click', () => setScreenOff(!screenOff))
el.scrub().addEventListener('input', () => {
  audio.currentTime = Number(el.scrub().value)
  renderLines(true)
  renderChrome()
})

// ---------------------------------------------------------------- boot
await createContainers()
try {
  books = await loadLibrary()
} catch (e) {
  const msg = e instanceof Error ? e.message : String(e)
  showError('library unreachable', msg)
  throw e
}
if (!books.length) {
  showError('library empty', 'run: ./reader add <file>, then ./reader publish')
  console.log('[glasses-reader] ready empty')
  throw new Error('empty library')
}
const qBook = qs.get('book')
bookIndex = qBook
  ? Math.max(0, books.findIndex(b => b.id === qBook))
  : Math.max(0, books.findIndex(b => b.id === saved.id))
renderBookList()
await select(bookIndex, Math.min(trackIndex, books[bookIndex].tracks.length - 1), false)
if (qs.get('hidden') !== null) setScreenOff(true)
console.log('[glasses-reader] ready', books[bookIndex].id, model.lines.length, 'lines')

import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'
import { loadLibrary, loadCues, audioUrl, type Book, type Track, type Cue } from './library'
import { wrapText } from './wrap'

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

const saved = JSON.parse(localStorage.getItem('reader.pos') ?? '{}')
const qs = new URLSearchParams(location.search)
console.log('[glasses-reader] url', location.href)
const startAt = Number(qs.get('seek') ?? NaN)

let books: Book[] = []
let bookIndex = 0
let trackIndex = Number(qs.get('track') ?? saved.track ?? 0)
let track: Track | null = null
let model: TrackModel = { lines: [], cueFirst: [], cueLines: [] }
let windowStart = -1
let activeLine = -1

const el = {
  status: () => document.getElementById('status')!,
  now: () => document.getElementById('now')!,
  list: () => document.getElementById('books')!,
  scrub: () => document.getElementById('scrub') as HTMLInputElement,
  play: () => document.getElementById('play')!,
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

async function createContainers() {
  if (!bridge) return
  const header = new TextContainerProperty({
    xPosition: 0, yPosition: 0, width: W, height: HEADER_H,
    borderWidth: 0, paddingLength: PAD, containerID: 1, containerName: 'header',
    content: 'Loading…', isEventCapture: 0, textColor: 2,
  })
  const body = new TextContainerProperty({
    xPosition: 0, yPosition: BODY_Y, width: W, height: BODY_H,
    borderWidth: 0, paddingLength: PAD, containerID: 2, containerName: 'body',
    content: ' ', isEventCapture: 1, textColor: 4,
  })
  const footer = new TextContainerProperty({
    xPosition: 0, yPosition: FOOTER_Y, width: W, height: FOOTER_H,
    borderWidth: 0, paddingLength: PAD, containerID: 3, containerName: 'footer',
    content: 'tap pause · swipe ±30s · double-tap exit', isEventCapture: 0, textColor: 2,
  })
  const rc = await bridge.createStartUpPageContainer(
    new CreateStartUpPageContainer({ containerTotalNum: 3, textObject: [header, body, footer] }),
  )
  if (rc !== 0) console.error('createStartUpPageContainer failed', rc)
}

let writing: Promise<unknown> = Promise.resolve()
function push(containerID: number, containerName: string, content: string) {
  if (!bridge) return
  writing = writing.then(() =>
    bridge!.textContainerUpgrade(new TextContainerUpgrade({ containerID, containerName, content })),
  ).catch(e => console.error('upgrade failed', e))
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
  push(1, 'header', header.length > 95 ? header.slice(0, 95) : header)
  el.status().textContent = `${book.title} · ${track.title}`
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
  push(2, 'body', out.join('\n'))
  if (lineMoved) el.now().textContent = model.lines[line]?.text ?? ''
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
  audio.currentTime = Number.isFinite(startAt) ? startAt : 0
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
    if (sysType === OsEventTypeList.DOUBLE_CLICK_EVENT || textType === OsEventTypeList.DOUBLE_CLICK_EVENT) {
      bridge!.shutDownPageContainer(1)
      return
    }
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
  localStorage.setItem('reader.pos', JSON.stringify({
    book: bookIndex, track: trackIndex, offset: Math.floor(audio.currentTime),
  }))
}, 1000)

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
el.scrub().addEventListener('input', () => {
  audio.currentTime = Number(el.scrub().value)
  renderLines(true)
  renderChrome()
})

// ---------------------------------------------------------------- boot
await createContainers()
books = await loadLibrary()
if (!books.length) {
  el.status().textContent = 'library empty — run: ./reader add <file>'
  console.log('[glasses-reader] ready empty')
  throw new Error('empty library')
}
const qBook = qs.get('book')
bookIndex = qBook
  ? Math.max(0, books.findIndex(b => b.id === qBook))
  : Math.min(books.length - 1, Number(saved.book ?? 0))
renderBookList()
await select(bookIndex, Math.min(trackIndex, books[bookIndex].tracks.length - 1), false)
console.log('[glasses-reader] ready', books[bookIndex].id, model.lines.length, 'lines')

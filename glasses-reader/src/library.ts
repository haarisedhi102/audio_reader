export interface Cue { t0: number; t1: number; text: string }
export interface TrackRef { title: string; audio: string; cues: string }
export interface Book {
  id: string
  title: string
  author: string
  tracks: TrackRef[]
}

export interface Track extends TrackRef { cuesData: Cue[] }

/**
 * The library is just a folder of books plus an index.json. Adding an article
 * is a write to that folder — no rebuild of this app, no code change.
 *
 * In development the Vite middleware serves it at /library. A packed app is
 * served from the app origin, so it needs an absolute base (VITE_LIB_BASE) —
 * normally the CDN host the library is published to.
 */
const trim = (u: string) => u.replace(/\/+$/, '')
const LIB_BASE = trim((import.meta.env.VITE_LIB_BASE as string | undefined) ?? '/library')
const AUDIO_BASE = trim((import.meta.env.VITE_AUDIO_BASE as string | undefined) ?? LIB_BASE)

const join = (base: string, ...parts: string[]) =>
  `${base}/${parts.map(p => encodeURIComponent(p)).join('/')}`

export async function loadLibrary(): Promise<Book[]> {
  const url = join(LIB_BASE, 'index.json')
  let res: Response
  try {
    res = await fetch(url, { cache: 'no-store' })
  } catch (e) {
    throw new Error(`can't reach ${LIB_BASE} (${e instanceof Error ? e.message : e})`)
  }
  if (!res.ok) throw new Error(`${url} → ${res.status}`)
  const type = res.headers.get('content-type') ?? ''
  if (!type.includes('json')) throw new Error(`${url} returned "${type || 'no content-type'}" — wrong base URL?`)
  const data = await res.json()
  return (data.books ?? []) as Book[]
}

export async function loadCues(book: Book, track: TrackRef): Promise<Cue[]> {
  const res = await fetch(join(LIB_BASE, book.id, track.cues), { cache: 'no-store' })
  if (!res.ok) throw new Error(`cues ${track.cues}: ${res.status}`)
  const data = await res.json()
  return (data.cues ?? data) as Cue[]
}

export function audioUrl(book: Book, track: TrackRef): string {
  return join(AUDIO_BASE, book.id, track.audio)
}

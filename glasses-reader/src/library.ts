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
 */
/** Where the library lives. Dev server serves it at /library; a packed app
 * running off the dev server needs an absolute URL to the Mac. */
const LIB_BASE = (import.meta.env.VITE_LIB_BASE as string | undefined) ?? '/library'

export async function loadLibrary(): Promise<Book[]> {
  const res = await fetch(`${LIB_BASE}/index.json`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`library index: ${res.status}`)
  const data = await res.json()
  return (data.books ?? []) as Book[]
}

export async function loadCues(book: Book, track: TrackRef): Promise<Cue[]> {
  const res = await fetch(`${LIB_BASE}/${book.id}/${track.cues}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`cues ${track.cues}: ${res.status}`)
  const data = await res.json()
  return (data.cues ?? data) as Cue[]
}

export function audioUrl(book: Book, track: TrackRef): string {
  const base = (import.meta.env.VITE_AUDIO_BASE as string | undefined) ?? LIB_BASE
  return `${base}/${book.id}/${track.audio}`
}

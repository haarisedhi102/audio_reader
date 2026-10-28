import { defineConfig, type Plugin } from 'vite'
import { resolve, join, normalize, extname } from 'node:path'
import { createReadStream, statSync } from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'

// The library (books + index.json) and the narration audio live outside this
// app folder. Serve them directly in dev/preview so adding an article never
// requires a rebuild or a copy.
const ROOT = resolve(__dirname, '..')
const MOUNTS: Record<string, string> = {
  '/library': resolve(ROOT, 'library'),
  '/audio': resolve(ROOT, 'audio'),
}

const TYPES: Record<string, string> = {
  '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4',
  '.wav': 'audio/wav',
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
}

function serveFile(root: string, req: IncomingMessage, res: ServerResponse, urlPath: string) {
  const rel = normalize(decodeURIComponent(urlPath.split('?')[0])).replace(/^(\.\.[/\\])+/, '')
  const file = join(root, rel)
  if (!file.startsWith(root)) { res.statusCode = 403; res.end(); return }

  let size: number
  try { size = statSync(file).size } catch { res.statusCode = 404; res.end('not found'); return }

  // a packed app is served from the app origin, not this one: allow cross-origin reads
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Headers', 'Range')
  res.setHeader('Access-Control-Expose-Headers', 'Content-Range, Content-Length, Accept-Ranges')
  if (req.method === 'OPTIONS') { res.statusCode = 204; res.end(); return }
  res.setHeader('Content-Type', TYPES[extname(file)] ?? 'application/octet-stream')
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Accept-Ranges', 'bytes')
  const range = req.headers.range

  if (range) {
    const m = /bytes=(\d*)-(\d*)/.exec(range)
    const start = m && m[1] ? parseInt(m[1], 10) : 0
    const end = m && m[2] ? parseInt(m[2], 10) : size - 1
    if (start >= size) {
      res.statusCode = 416
      res.setHeader('Content-Range', `bytes */${size}`)
      res.end()
      return
    }
    res.statusCode = 206
    res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`)
    res.setHeader('Content-Length', String(end - start + 1))
    if (req.method === 'HEAD') { res.end(); return }
    createReadStream(file, { start, end }).pipe(res)
    return
  }

  res.setHeader('Content-Length', String(size))
  if (req.method === 'HEAD') { res.end(); return }
  createReadStream(file).pipe(res)
}

function serveLibrary(): Plugin {
  const mount = (server: { middlewares: { use: Function } }) => {
    for (const [prefix, dir] of Object.entries(MOUNTS)) {
      server.middlewares.use(prefix, (req: IncomingMessage, res: ServerResponse, next: () => void) => {
        const url = (req as IncomingMessage & { url?: string }).url
        if (!url) return next()
        serveFile(dir, req, res, url)
      })
    }
  }
  return {
    name: 'serve-library',
    configureServer(server) { mount(server as never) },
    configurePreviewServer(server) { mount(server as never) },
  }
}

export default defineConfig({
  plugins: [serveLibrary()],
  publicDir: false,
  server: { host: true, fs: { allow: [ROOT] } },
  build: { target: 'es2022' },
})

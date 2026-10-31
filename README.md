# reader — give it an article, read and listen on your glasses

One command turns a PDF, Markdown or text file into an audiobook that scrolls on
Even Realities G2 in sync with the audio.

```bash
./reader add article.pdf --title "Title" --author "Name"
./reader add https://author.substack.com/p/slug   # pulls the post, then builds
./reader pull https://author.substack.com/p/slug  # pull the markdown only
./reader publish               # transcode + upload to R2, then listen anywhere
./reader pack                  # bump, build against R2, package glasses-reader.ehpk
./reader serve                 # or open http://localhost:5173
./reader sim                   # or drive the Even Hub simulator
```

`./reader add` prints a `?book=<id>` link at the end.

`./reader publish` is what makes the library portable: it stages a 64 kbps
`+faststart` copy and syncs it to S3-compatible storage, so playback needs no
process running here. Setup: `docs/hosting.md`.

## What happens

```
pdf/url ─► extract ─► [listenability] ─► narrate+scrub ─► synthesise ─► normalise ─► cues ─► library/
           (text layer  (PDFs only; LLM      (markdown,      (Fish base,     (gain +      (exact
            + OCR only   swaps, verbatim)     urls, emoji,    Eleven for      limiter,     per-sentence
            where glyphs                      symbols)        non-Latin)      aac_at)      timings)
            are missing)
```

- **extract** — the PDF text layer is the source of truth. Missing glyphs
  (broken font encodings) are detected as "ghost" spaces with the missing
  advance width. Each page is then classified: `clean` (use the layer),
  `light` (layer + Tesseract gap fill, matched by position) or `heavy` (a local
  PaddleOCR-VL page read, with the layer restoring diacritics). See
  `docs/extraction.md` — the engines have one job each and do not overlap.
- **listenability** (PDFs only) — an LLM pass that may only return literal
  find-and-replace pairs (`Dr.` → `Doctor`, `&` → `and`, drop running heads).
  Every swap must match the source verbatim; anything that changes wording is
  rejected. Text sources skip it entirely.
- **narrate + scrub** — strips markdown, then a deterministic scrub removes
  links, URLs, emails, footnote markers and emoji, and expands
  `± ≈ № π × ÷ = + < > § ~` into words. No dictionary and no accent stripping:
  Arabic/Urdu/Farsi script and accented Latin (`Jāvīdnāma`) are preserved.
- **synthesise** — Fish Audio's direct API with a persistent `reference_id`
  (`FISH_VOICE_ID`), so no reference audio is sent per chunk. Any chunk
  containing a non-Latin letter or math symbol goes to ElevenLabs direct
  (`TTS_FALLBACK=eleven`, `eleven_v4_turbo`); everything else stays on Fish.
  Chunks are cached by text hash and synthesized in parallel.
  `TTS_MODEL=fish|eleven` picks the base engine.
- **normalise** — one loudness analysis pass, then a static gain + limiter, so
  the whole library sits at −16 LUFS without the expensive dynamic filter.
- **cues** — sentence timings are read back from the chunk WAVs, so the glasses
  text is driven by the audio clock rather than by microphone guessing.

## Guarantees

- **The author's wording is preserved.** The only LLM stage left (PDF
  listenability) applies declared string swaps only; text sources never touch a
  model. On the sample corpus every diff hunk is accounted for by a swap.
- **Hand-checked work survives.** A book whose transcript was verified is marked
  `"verified": true` in `library/index.json`; `./reader add` refuses to
  overwrite it without `--re-extract`.
- **No model in the transcription path.** OCR supplies characters, never
  paraphrase.

## Layout

```
library/                 # the only thing the app reads (gitignored: content)
  index.json             # books, tracks, which cues/audio belong to each
  <book>/cues_0.json     # [{t0,t1,text}, …]
  <book>/<book>.m4a
  <book>/text.md
audio/<book>_*_parts/    # cached sentence WAVs (source of truth for cues)
work/<book>/             # extracted markdown + narration script + edit logs
glasses-reader/          # the Even Hub plugin (reads library/ at runtime)
docs/extraction.md       # which engine owns which page, and why
```

Adding an article never requires rebuilding the app — it is a new folder plus a
manifest entry.

## Controls on the glasses

| Input | Action |
|---|---|
| Tap | play / pause |
| Swipe up / down | −30 s / +30 s |
| Long-press | hide/show the text — playback continues; any tap brings it back |
| Menu (from the glasses' own long-press) | Hide text / Show text / Exit — the phone's `hide` button always works, even if the OS claims the press |
| Double-tap | exit |

## Requirements

- macOS on Apple Silicon, `ffmpeg` (with `aac_at`), `tesseract`
- `.venv-tts` with `mlx-audio`, `pymupdf`, and optionally `mlx-vlm` (heavy OCR path)
- Node 18+ for the Even Hub plugin
- An OpenAI-compatible key in `.env` for PDF metadata/listenability
  (`--no-llm` runs without one)

## Notes

- Voice: Fish uses `FISH_VOICE_ID` + `FISH_KEY` (model via `FISH_MODEL`, default
  `s2.1-pro-free` until credit is added). Eleven uses `ELEVEN_KEY` /
  `ELEVEN_VOICE_ID` / `ELEVEN_MODEL` (default `eleven_v4_turbo`, George).
- Router: any chunk with a non-Latin letter (Arabic/Urdu/Farsi script, Turkish
  diacritics) or math symbol goes to Eleven; everything else stays on Fish.
  `TTS_FALLBACK=` disables the split. The cache is keyed by the routing
  signature and voice IDs.
- Parallelism: `TTS_CONCURRENCY` requests at a time (default 6) — measured ~5×
  faster on a 37-chunk book. Workers retry with backoff and write chunks
  atomically (`.part.wav` → rename).
- Re-running `./reader add` on the same `--id` updates the entry in place, except
  for verified books.
- TTS and OCR caches are keyed by content, so iterating on one paragraph is cheap.
- `./reader extract <file>` stops after extraction, for proof-reading before you
  spend synthesis time.
- A packed `.ehpk` runs from the app origin, not the dev server: build it with
  `VITE_LIB_BASE=<public host>/library npm run build:prod && npm run pack`. The
  base is baked in at build time, and `build:prod` refuses to build without it.
- Publishing stages into `.publish/` (gitignored) and never modifies `library/`
  or `audio/`; re-publishing only re-encodes files whose source changed.

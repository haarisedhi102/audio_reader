# reader — give it an article, read and listen on your glasses

One command turns a PDF, Markdown or text file into an audiobook that scrolls on
Even Realities G2 in sync with the audio.

```bash
./reader add article.pdf --title "Title" --author "Name"
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
article.pdf ─► extract ─► listenability ─► narrate ─► synthesise ─► normalise ─► cues ─► library/
              (text layer   (LLM: symbols     (markdown    (Breeze TTS    (gain +      (exact
               + OCR only    + abbreviations    cleanup,     chunks,        limiter,     per-sentence
               where glyphs  only, as literal   lexicon,     cached per     aac_at)      timings)
               are missing)  replacements)      homophones)  text hash)
```

- **extract** — the PDF text layer is the source of truth. Missing glyphs
  (broken font encodings) are detected as "ghost" spaces with the missing
  advance width. Each page is then classified: `clean` (use the layer),
  `light` (layer + Tesseract gap fill, matched by position) or `heavy` (a local
  PaddleOCR-VL page read, with the layer restoring diacritics). See
  `docs/extraction.md` — the engines have one job each and do not overlap.
- **listenability** — an LLM pass that may only return literal find-and-replace
  pairs (`Dr.` → `Doctor`, `&` → `and`, drop running heads). Every swap must
  match the source verbatim; anything that changes wording is rejected. This is
  what makes the narration an *enjoyable* listenable text without paraphrasing.
- **narrate** — strips markdown, expands numbers/abbreviations, applies a
  pronunciation lexicon for Ottoman/Turkish/Arabic terms, and picks the archery
  reading of "bow" (`data/lexicon.json`, 297 terms).
- **synthesise** — Breeze TTS on MLX (Apple Silicon), chunked per sentence,
  cached by text hash so edits only re-render what changed.
- **normalise** — one loudness analysis pass, then a static gain + limiter, so
  the whole library sits at −16 LUFS without the expensive dynamic filter.
- **cues** — sentence timings are read back from the chunk WAVs, so the glasses
  text is driven by the audio clock rather than by microphone guessing. Cue text
  has pronunciation respellings reversed, so the screen shows `Okçular Tekkesi`,
  not the phonetic form.

## Guarantees

- **The author's wording is preserved.** The LLM stages cannot rewrite prose:
  the repair pass accepts only character-level edits, and the listenability pass
  only applies declared string swaps. On the sample corpus every diff hunk in
  the output is accounted for by a declared swap.
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
data/lexicon.json        # hand-curated pronunciations
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
- An OpenAI-compatible key in `.env` for the metadata/listenability stages
  (`--no-llm` runs without one)

## Notes

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

# Extraction: who does what

Three engines touch a page, and each has exactly one job. The rule between them
is a **per-page decision**, not a pipeline that runs everything.

| Engine | Job | Never does | Cost |
|---|---|---|---|
| **Text layer** (PyMuPDF) | The transcription. Exact characters, order, diacritics, italics. | Nothing else. It is the source of truth wherever it has characters. | ~0 |
| **Tesseract** | Fill the holes. Only where the text layer lost glyphs (broken font maps), matched line by line by geometry. | Transcribe a page on its own. | fast |
| **VLM OCR** (PaddleOCR-VL) | Read a page the text layer cannot represent at all — scans, no ToUnicode map, image-only PDFs. | Provide "a second opinion" on a page that already has good text. | ~5–40 s/page |
| **LLM** (gpt-5.6-sol) | Metadata (title/author) and pronunciation respellings. Optionally flag mechanical damage. | Read images. Transcribe. Rewrite prose. | cheap |

## The decision, per page

```
                 ghosts in text layer?
                   0 ────────────────► CLEAN
                   │                    use text layer as-is
                   │                    no OCR, no LLM
                   ▼
        layer still covers ≥ 90% of the page's characters?
                   │
          yes ─────┴─────► LIGHT
          │                 text layer + tesseract gap fill (per line, by position)
          │
          no ────────────► HEAVY
                            VLM reads the page
                            text layer only restores diacritics/proper nouns
```

"Ghosts" are spaces whose advance width is that of the missing glyph: the
signature of a character the PDF could not encode. They are the only reason to
invoke OCR on a born-digital page.

## Why not just VLM everything

Measured on the same 8-page article against a hand-checked transcript:

| Path | Agreement |
|---|---|
| Text layer alone | 0.87 |
| Text layer + tesseract gap fill | **0.95** |
| VLM everywhere | 0.92 |

The text layer is right about things a VLM guesses wrong (diacritics,
hyphenation, proper nouns). Mixing sources by default makes the result worse.

## Why not LLM repair by default

Asked to clean OCR, a model will also "improve" prose: on this corpus it turned
"scudded" into "seduced" and "most popular" into "more spectacular". The repair
step is therefore opt-in (`--polish`) and its edits are applied token by token,
rejecting anything that is not a character-level fix.

## Output of each stage

| Stage | Artifact | Where |
|---|---|---|
| text layer | per-page lines + char boxes | in memory |
| tesseract | page TSV | `<workdir>/pNNNN.tsv` |
| VLM | raw page text | `<workdir>/pNNNN.vlm.txt` |
| merged | `text.md` | `work/<book>/text.md` |
| LLM | polished text + change log | `work/<book>/text.polished.md` |

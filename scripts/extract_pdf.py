"""
General PDF text extraction for the reader pipeline.

Two failure modes of naive extraction are handled:
  1. Broken font encodings: characters missing from the ToUnicode map become
     "ghost" spaces whose advance width is the missing glyph's width. Detected
     here, and only those pages are rendered + OCR'd to recover the characters.
  2. Page furniture: footnotes (smaller type at the page foot), page numbers
     and running headers are dropped.

Output: markdown with paragraphs and headings, no page furniture.
"""
import fitz, re, sys, os, subprocess, csv, difflib, statistics

OCR_DPI = 400
PTS = 72.0 / OCR_DPI

_TESS = None

def _tess_env():
    """Pick a tessdata dir that exists and the best language set it supports."""
    global _TESS
    if _TESS:
        return _TESS
    cands = [os.environ.get("TESSDATA_PREFIX"),
             os.path.join(os.environ.get("COMMANDCODE_SCRATCHPAD", ""), "tessdata"),
             "/opt/homebrew/share/tessdata", "/usr/local/share/tessdata"]
    for d in cands:
        if d and os.path.exists(os.path.join(d, "eng.traineddata")):
            langs = "eng+tur" if os.path.exists(os.path.join(d, "tur.traineddata")) else "eng"
            _TESS = (d, langs)
            return _TESS
    _TESS = (None, "eng")
    return _TESS

def ocr_lines(png, tessdata=None):
    # tesseract fails on /tmp symlink paths on macOS; resolve to /private/tmp
    png = os.path.realpath(png)
    base = png[:-4]
    dir_, langs = _tess_env()
    if tessdata:
        dir_ = tessdata
        langs = "eng+tur" if os.path.exists(os.path.join(tessdata, "tur.traineddata")) else "eng"
    cmd = ["tesseract", png, base, "-l", langs, "--psm", "3"]
    if dir_:
        cmd += ["--tessdata-dir", dir_]
    cmd += ["tsv"]
    subprocess.run(cmd, capture_output=True)
    tsv = base + ".tsv"
    if not os.path.exists(tsv) or os.path.getsize(tsv) == 0:
        return []
    rows = list(csv.reader(open(tsv), delimiter="\t"))[1:]
    lines = {}
    for r in rows:
        if len(r) < 12 or r[0] != "5":
            continue
        key = (int(r[2]), int(r[3]), int(r[4]))
        left, top, w, h = (float(r[6]), float(r[7]), float(r[8]), float(r[9]))
        d = lines.setdefault(key, {"words": [], "bbox": [left, top, left + w, top + h]})
        b = d["bbox"]
        b[0], b[1] = min(b[0], left), min(b[1], top)
        b[2], b[3] = max(b[2], left + w), max(b[3], top + h)
        d["words"].append((left, r[11]))
    return [{"text": " ".join(w for _, w in sorted(d["words"]) if w.strip()),
             "bbox": [c * PTS for c in d["bbox"]]}
            for _, d in lines.items()]

def page_lines(page):
    """Visual lines (fragments sharing a baseline are merged), page furniture removed."""
    H = page.rect.height
    raw, sizes = [], {}
    for b in page.get_text("rawdict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            chars, size = [], 0
            for sp in l["spans"]:
                for ch in sp["chars"]:
                    chars.append([ch["c"], ch["bbox"][0], ch["bbox"][2]])
                size = max(size, sp["size"])
            if not chars:
                continue
            chars.sort(key=lambda c: c[1])
            raw.append({"chars": chars, "size": size, "bbox": list(l["bbox"]),
                        "y": (l["bbox"][1] + l["bbox"][3]) / 2})
            sizes[size] = sizes.get(size, 0) + len(chars)

    body_size = max(sizes, key=sizes.get) if sizes else 11.25

    # merge fragments that share a baseline
    raw.sort(key=lambda l: (round(l["y"]), l["bbox"][0]))
    merged = []
    for l in raw:
        h = l["bbox"][3] - l["bbox"][1]
        if merged and abs(merged[-1]["y"] - l["y"]) < max(2.0, 0.5 * h):
            merged[-1]["chars"] += l["chars"]
            merged[-1]["bbox"][0] = min(merged[-1]["bbox"][0], l["bbox"][0])
            merged[-1]["bbox"][2] = max(merged[-1]["bbox"][2], l["bbox"][2])
            merged[-1]["size"] = max(merged[-1]["size"], l["size"])
        else:
            merged.append(dict(l, chars=list(l["chars"])))

    out = []
    for l in merged:
        text = "".join(c[0] for c in l["chars"]).strip()
        if not text:
            continue
        y0 = l["bbox"][1]
        if y0 > H * 0.92 and re.fullmatch(r"\d{1,4}", text):      # page number
            continue
        if l["size"] <= body_size - 1.5 and y0 > H * 0.72:          # footnote block
            continue
        l["chars"].sort(key=lambda c: c[1])
        out.append(l)
    out.sort(key=lambda l: (round(l["y"]), l["bbox"][0]))
    return out

def ghost_count(chars):
    gaps = [c[2] - c[1] for c in chars if c[0].strip() == ""]
    if not gaps:
        return 0
    normal = statistics.median(gaps)
    return sum(1 for g in gaps if g > normal * 1.6)

def merge_ocr(base_text, ocr_text):
    if not ocr_text:
        return base_text
    b = re.sub(r"\s", "", base_text)
    o = re.sub(r"\s", "", ocr_text)
    if not o or len(b) / len(o) >= 0.995:
        return base_text
    sm = difflib.SequenceMatcher(None, base_text, ocr_text, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        bseg, oseg = base_text[i1:i2], ocr_text[j1:j2]
        out.append(bseg if tag in ("equal", "delete") else (oseg if tag == "insert" else (oseg if not bseg.strip() else bseg)))
    return "".join(out)

VLM_MODEL = os.environ.get("OCR_VLM", "mlx-community/PaddleOCR-VL-1.6-4bit")
VLM_PROMPT = ("Extract all text from this page in reading order. "
              "Output plain text only, one block per line, no commentary.")

def vlm_lines(png: str) -> list[str]:
    """Whole-page OCR with a small local VLM (mlx-vlm). Cached per page."""
    png = os.path.realpath(png)
    cache = png[:-4] + ".vlm.txt"
    if os.path.exists(cache) and os.path.getsize(cache):
        text = open(cache).read()
    else:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "mlx_vlm.generate", "--model", VLM_MODEL,
                 "--image", png, "--prompt", VLM_PROMPT, "--max-tokens", "4096",
                 "--temp", "0"],
                capture_output=True, text=True, timeout=600)
            text = r.stdout
        except Exception as e:
            print(f"  vlm ocr failed: {e}", file=sys.stderr)
            return []
        open(cache, "w").write(text)
    text = re.sub(r"<\|[^|]*\|>", " ", text)          # strip <|LOC_x|> markers
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    return [l for l in lines if l]

def page_word_merge(base_lines: list[str], vlm_text: str) -> list[str]:
    """Repair whole-page words using the VLM transcript.

    The text layer is authoritative wherever it has characters; the VLM supplies
    words for spans the layer could not encode (where its word count differs).
    """
    if not vlm_text.strip():
        return base_lines
    vw = vlm_text.split()
    bw, owner = [], []
    for li, line in enumerate(base_lines):
        for w in line.split():
            bw.append(w); owner.append(li)
    sm = difflib.SequenceMatcher(None, bw, vw, autojunk=False)
    fixed = list(bw)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            if (i2 - i1) == (j2 - j1):
                for k, (x, y) in enumerate(zip(bw[i1:i2], vw[j1:j2])):
                    if _lev_ok(x, y):
                        fixed[i1 + k] = y
            else:
                # base lost characters here; the VLM span is the better reading
                span = vw[j1:j2]
                if span and (i2 - i1) <= len(span) + 2:
                    for k, y in enumerate(span):
                        if i1 + k < len(fixed):
                            fixed[i1 + k] = y
    out, ptr = [], 0
    for li, line in enumerate(base_lines):
        n = len(line.split())
        out.append(" ".join(fixed[ptr:ptr + n]))
        ptr += n
    return out

def _lev_ok(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 2:
        return False
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.72

def best_match(base: str, candidates: list[str]) -> str:
    best, score = "", 0.0
    for c in candidates:
        r = difflib.SequenceMatcher(None, base, c, autojunk=False).ratio()
        if r > score:
            best, score = c, r
    return best if score >= 0.55 else ""

def classify_page(lines) -> tuple[str, int, float]:
    """Decide which engine owns this page.

    Returns (kind, ghosts, coverage) where coverage estimates how much of the
    page the text layer actually encodes: each ghost is one missing character.
    """
    ghosts = sum(ghost_count(l["chars"]) for l in lines)
    base_chars = sum(len("".join(c[0] for c in l["chars"]).replace(" ", "")) for l in lines)
    if ghosts == 0:
        return "clean", 0, 1.0
    return ("light" if base_chars / (base_chars + ghosts) >= 0.90 else "heavy"), ghosts, \
           base_chars / (base_chars + ghosts)


def restore_from_layer(vlm_text: str, base_words: dict) -> str:
    """Give the VLM transcript the text layer's diacritics and spelling.

    The VLM writes "okmeydan" where the layer has "okmeydanı"; the layer is
    authoritative for characters it does contain.
    """
    out = []
    for w in vlm_text.split():
        key = w.lower().strip(".,;:()[]\u201c\u201d\u2019'\"")
        out.append(base_words.get(key, w))
    return " ".join(out)


def extract(pdf, out_md, tessdata=None, workdir="/tmp/reader_ocr", ocr="auto"):
    doc = fitz.open(pdf)
    os.makedirs(workdir, exist_ok=True)
    blocks, kinds = [], {}

    for pno, page in enumerate(doc, 1):
        lines = page_lines(page)
        if not lines:
            continue
        kind, ghosts, coverage = classify_page(lines)
        kinds[kind] = kinds.get(kind, 0) + 1
        base_lines = ["".join(c[0] for c in l["chars"]) for l in lines]
        texts = [re.sub(r"\s+", " ", t).strip() for t in base_lines]

        if kind == "clean":
            pass                                   # text layer is the transcription

        elif kind == "light":
            png = os.path.join(workdir, f"p{pno:04d}.png")
            if not os.path.exists(png) or os.path.getsize(png) == 0:
                page.get_pixmap(dpi=OCR_DPI).save(png)
            if ocr == "vlm":                       # forced: use the stronger reader
                vlm = " ".join(vlm_lines(png))
                texts = restore_from_layer(vlm, layer_word_map(base_lines)).split("\n")
                blocks.extend({"text": t, "x0": lines[0]["bbox"][0], "y": 0, "page": pno}
                              for t in texts if t)
                continue
            tsv = ocr_lines(png, tessdata)
            for i, l in enumerate(lines):
                cand, bestd = None, 1e9
                ly0, ly1 = l["bbox"][1], l["bbox"][3]
                for o in tsv:
                    ov = min(ly1, o["bbox"][3]) - max(ly0, o["bbox"][1])
                    if ov <= 0.3 * max(ly1 - ly0, 1):
                        continue
                    d = abs((o["bbox"][1] + o["bbox"][3]) / 2 - l["y"])
                    if d < bestd:
                        cand, bestd = o, d
                texts[i] = re.sub(r"\s+", " ", merge_ocr(base_lines[i], cand["text"] if cand else "")).strip()

        else:                                      # heavy: VLM owns the page
            png = os.path.join(workdir, f"p{pno:04d}.png")
            if not os.path.exists(png) or os.path.getsize(png) == 0:
                page.get_pixmap(dpi=OCR_DPI).save(png)
            vlm = "\n".join(vlm_lines(png))
            texts = restore_from_layer(vlm, layer_word_map(base_lines)).splitlines()

        for i, t in enumerate(texts):
            if not t:
                continue
            blocks.append({"text": t, "x0": lines[i]["bbox"][0] if i < len(lines) else 100,
                           "y": lines[i]["y"] if i < len(lines) else 0, "page": pno})

    print(f"  pages: {kinds}", file=sys.stderr)

if __name__ == "__main__":
    pdf, out = sys.argv[1], sys.argv[2]
    td = sys.argv[3] if len(sys.argv) > 3 else None
    n = extract(pdf, out, td)
    print(f"{out}: {n} words")

def layer_word_map(base_lines: list[str]) -> dict:
    """lowercased, punctuation-stripped word -> the layer's exact spelling."""
    out = {}
    for line in base_lines:
        for w in line.split():
            key = w.lower().strip(".,;:()[]“”’'\"")
            if key and key not in out and any(ord(c) > 127 for c in w):
                out[key] = w
    return out

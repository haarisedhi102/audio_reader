import fitz, re, sys, json

PDF = "/Users/haarisedhi/ocr _to_speech/The_Spiritual_in_Islamic_calligraphy_a_p.pdf"
OUT = "/Users/haarisedhi/ocr _to_speech/The_Spiritual_in_Islamic_calligraphy.md"

doc = fitz.open(PDF)
blocks_out = []          # list of (kind, text)
prev_end_y = 0

for pno, page in enumerate(doc, 1):
    H = page.rect.height
    lines = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"]:
            continue
        text = " ".join("".join(sp["text"] for sp in l["spans"]) for l in b["lines"]).strip()
        if not text:
            continue
        sizes = [sp["size"] for l in b["lines"] for sp in l["spans"] if sp["text"].strip()]
        size = max(sizes) if sizes else 0
        y0, y1 = b["bbox"][1], b["bbox"][3]
        x0 = b["bbox"][0]
        # drop page number (bottom, digits only)
        if y0 > H - 90 and re.fullmatch(r"\d{1,4}", text):
            continue
        # drop footnotes (smaller type at the foot of the page)
        if size < 11.0:
            continue
        spans = [sp for l in b["lines"] for sp in l["spans"] if sp["text"].strip()]
        italic_only = bool(spans) and all(sp["flags"] & 2 for sp in spans)
        lines.append({"text": text, "x0": x0, "y0": y0, "y1": y1, "size": size,
                      "italic": italic_only})

    lines.sort(key=lambda l: (round(l["y0"]), l["x0"]))
    for i, l in enumerate(lines):
        t = re.sub(r"\s+", " ", l["text"]).strip()
        # strip footnote markers glued to punctuation or words
        t = re.sub(r"(?<=[.,;:’”\)])\d{1,3}(?=\s|$)", "", t)
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        indented = l["x0"] >= 138
        short = len(t) < 65
        heading = (l["italic"] and len(t) < 70 and not indented
                   and not t.endswith((".", ",", ";", ":", "!", "?", "’", "”"))
                   and len(t.split()) <= 10)
        blocks_out.append({"kind": "heading" if heading else "text", "text": t,
                           "indented": indented, "page": pno})

# paragraph assembly: indented line starts a new paragraph
paras, cur = [], ""
for b in blocks_out:
    if b["kind"] == "heading":
        if cur: paras.append(("p", cur)); cur = ""
        paras.append(("h", b["text"]))
        continue
    if b["indented"] and cur:
        paras.append(("p", cur)); cur = b["text"]
    else:
        if not cur:
            cur = b["text"]
        elif cur.endswith("-") and b["text"][:1].islower():
            cur = cur[:-1] + b["text"]
        else:
            cur = cur + " " + b["text"]
if cur: paras.append(("p", cur))

md, words = [], 0
for kind, text in paras:
    text = re.sub(r"\s+", " ", text).strip()
    if not text: continue
    if kind == "h":
        md.append(f"\n### {text}\n")
    else:
        md.append(text + "\n")
        words += len(text.split())
open(OUT, "w").write("\n".join(md))

print(f"{len(paras)} blocks, {words} words, {sum(len(t) for _, t in paras)} chars")
heads = [t for k, t in paras if k == "h"]
print(f"{len(heads)} headings; first 25:")
for h in heads[:25]: print("  ", h[:80])

import re, sys, os
sys.path.insert(0, "/Users/haarisedhi/ocr _to_speech/scripts")
import narrate as N

SRC = "/Users/haarisedhi/ocr _to_speech/The_Spiritual_in_Islamic_calligraphy.md"
text = open(SRC).read()

def occ(kw, nth=0):
    hits = [m.start() for m in re.finditer(re.escape(kw), text)]
    return hits[nth] if len(hits) > nth else -1

intro = occ("INTRODUCTION", 1)          # skip the TOC entry
concl = occ("CONCLUSIONS", 1)
biblio = occ("BIBLIOGRAPHY", 1)
assert 0 < intro < concl < biblio, (intro, concl, biblio)

chapters = []
for n, word in enumerate(["ONE","TWO","THREE","FOUR","FIVE","SIX","SEVEN"], 1):
    p = occ(f"CHAPTER {word}")
    assert p > intro, (word, p)
    chapters.append((n, p))

bounds = [("00_intro", intro, chapters[0][1])]
for i, (n, p) in enumerate(chapters):
    nxt = chapters[i + 1][1] if i + 1 < len(chapters) else concl
    bounds.append((f"0{n}_ch{n}", p, nxt))
bounds.append(("08_conclusions", concl, biblio))

total = 0
for label, i, j in bounds:
    seg = text[i:j]
    seg = re.sub(r"(?m)^(Table|Figure|Plate|Image)\s*\d+.*$", "", seg)
    seg = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", seg)          # stray page numbers
    seg = re.sub(r"(?m)^.*\.{5,}.*$", "", seg)             # TOC dot leaders
    paras = [N.apply_lexicon(N.spoken(p)) for p in re.split(r"\n\s*\n", seg) if p.strip()]
    paras = [p for p in paras if len(p.split()) > 2]
    out = f"/Users/haarisedhi/ocr _to_speech/narration_thesis_{label}.txt"
    open(out, "w").write("\n\n".join(paras))
    w = sum(len(p.split()) for p in paras)
    total += w
    print(f"  {label:15s} {w:6d} words")
print("total words:", total)

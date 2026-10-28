import re, sys

src = open("/Users/haarisedhi/ocr _to_speech/A_Turkish_Archer_On_The_Tracks_Of_His_An.md").read()
blocks = [b.strip() for b in src.split("\n\n") if b.strip()]

ORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
       7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh",
       12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth",
       16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth",
       20: "twentieth"}

def spoken(t):
    t = t.replace("**", "").strip()
    t = re.sub(r"^#+\s*", "", t)
    t = t.strip("*").strip()
    t = t.replace("Dr.", "Doctor")
    t = t.replace("PhD", "P H D")
    # ordinals
    def ordn(m):
        n = int(m.group(1))
        if n in ORD:
            return ORD[n]
        return m.group(0)
    t = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", ordn, t)
    # decades like 1940s, 50s, 60s
    t = t.replace("1940s", "nineteen forties").replace("1950s", "nineteen fifties")
    t = t.replace("60s", "sixties")
    # metres
    t = re.sub(r"\b(\d{2,3})\s*m\b", r"\1 meters", t)
    t = re.sub(r"\((\d{3})\s*meters?\)", r"(\1 meters)", t)
    t = re.sub(r"(\d+)-(\d+)", r"\1 to \2", t)
    t = t.replace("No: 46", "number 46")
    t = t.replace("etc.", "etcetera.")
    t = t.replace("e.g.", "for example")
    t = t.replace("distance/(flight)", "distance and flight")
    t = t.replace("bow(-grip)", "bow grip")
    t = t.replace("Sultan Mehmed II", "Sultan Mehmed the Second")
    t = t.replace("Sultan Mahmud II", "Sultan Mahmud the Second")
    t = t.replace("Sultan Selim III", "Sultan Selim the Third")
    t = t.replace("(Selim III)", "(Selim the Third)")
    t = t.replace(" (Photo: Author’s archive)", "")
    t = re.sub(r" \(Photos?: [^)]*\)", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

out = []
for b in blocks:
    out.append(spoken(b))

paras = [p for p in out if p]
open("/Users/haarisedhi/ocr _to_speech/narration.txt", "w").write("\n\n".join(paras))
print("\n\n".join(paras))
print("\n---", sum(len(p.split()) for p in paras), "words,", len(paras), "blocks")

#!/usr/bin/env python3
"""
One article in, one library entry out.

    .venv-tts/bin/python scripts/build_book.py article.pdf --title "..." --author "..."

Steps: extract -> narrate -> synthesise -> normalise -> cue -> manifest.
Everything is cached: re-running after a change only re-synthesises the chunks
whose text actually changed.
"""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)

import narrate as N
import llm
from generate_audio import main as synth_book, MODEL
import make_cues_lib as M

LIB = ROOT / "library"
AUDIO = ROOT / "audio"
SCRATCH = Path(os.environ.get("COMMANDCODE_SCRATCHPAD", "/tmp"))

def slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:48] or "article"

def extract(src: Path, out_md: Path) -> None:
    ext = src.suffix.lower()
    if ext == ".pdf":
        import extract_pdf
        extract_pdf.extract(str(src), str(out_md))
    elif ext in (".md", ".markdown", ".txt"):
        shutil.copy(src, out_md)
    else:
        sys.exit(f"unsupported input: {ext} (use .pdf, .md or .txt)")

def build_narration(md: Path, out_txt: Path) -> int:
    text = md.read_text()
    blocks, buf, skip = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^(#+\s*)?(references|bibliography|kaynakça)\s*$", s, re.I):
            skip = True
        if skip:
            continue
        if not s:
            if buf: blocks.append(" ".join(buf)); buf = []
            continue
        if s.startswith("#"):
            if buf: blocks.append(" ".join(buf)); buf = []
            blocks.append(re.sub(r"^#+\s*", "", s))
            continue
        buf.append(s)
    if buf: blocks.append(" ".join(buf))

    paras = []
    for b in blocks:
        t = N.spoken(b)
        if not t:
            continue
        paras.append(N.apply_lexicon(t))
    out_txt.write_text("\n\n".join(paras))
    return sum(len(p.split()) for p in paras)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--title")
    ap.add_argument("--author", default="")
    ap.add_argument("--id")
    ap.add_argument("--voice", default=str(SCRATCH / "tts_test/ref_000.wav"))
    ap.add_argument("--voice-text", default=str(SCRATCH / "ref.txt"))
    ap.add_argument("--extract-only", action="store_true")
    ap.add_argument("--polish", action="store_true",
                    help="let the LLM repair mechanical damage (opt-in, edit-gated)")
    ap.add_argument("--ocr", default="auto", choices=["auto", "tesseract", "vlm"])
    ap.add_argument("--no-llm", action="store_true", help="skip all LLM stages")
    ap.add_argument("--re-extract", action="store_true",
                    help="replace a book whose transcript was hand-verified")
    args = ap.parse_args()

    src = Path(args.source).expanduser().resolve()
    if not src.exists():
        sys.exit(f"no such file: {src}")

    title = args.title or re.sub(r"[_-]+", " ", src.stem).strip()
    author = args.author
    bid = args.id or slug(title)

    index_path0 = ROOT / "library" / "index.json"
    if index_path0.exists():
        prev = {b["id"]: b for b in json.load(open(index_path0)).get("books", [])}.get(bid)
        if prev and prev.get("verified") and not args.re_extract:
            print(f"'{bid}' has a hand-verified transcript — refusing to overwrite.\n"
                  f"  pass --re-extract to replace it, or use --id for a new version.")
            return

    work = ROOT / "work" / bid
    work.mkdir(parents=True, exist_ok=True)
    md = work / "text.md"

    print(f"[1/5] extract  {src.name}")
    extract(src, md)
    if llm.available() and not args.no_llm:
        meta = llm.metadata(md.read_text())
        if not args.title and meta.get("title"):
            title = meta["title"]; bid = args.id or slug(title)
        if not author and meta.get("author"):
            author = meta["author"]
        print(f"      llm metadata: {title!r} / {author!r}")
    if args.polish and not args.no_llm:
        if not llm.available():
            print("      polish skipped: no LLM key in .env")
        else:
            print("      polish: repair pass (edit-gated)")
            fixed, changes = llm.repair(md.read_text())
            md.write_text(fixed)
            (work / "changes.json").write_text(json.dumps(changes, indent=1))
            print(f"      {len(changes)} accepted edits -> changes.json")
    words = len(md.read_text().split())
    print(f"      {words} words -> {md}")

    if llm.available() and not args.no_llm:
        print("[2/5] listenability  (symbol/abbrev expansion, artefact removal)")
        text = md.read_text()
        spoken, edits = llm.speakable(text, verbose=True)
        if edits:
            md.write_text(spoken)
            (work / "speech.json").write_text(json.dumps(edits, indent=1, ensure_ascii=False))
            print(f"      {len(edits)} listenability edits -> speech.json")

    print("[2/5] narrate")
    narration = work / "narration.txt"
    nwords = build_narration(md, narration)
    if llm.available():
        import re as _re
        foreign = sorted({w for w in _re.findall(r"[^\W\d_]+", narration.read_text())
                          if any(ord(c) > 127 for c in w)} - set(N.LEX))
        if foreign:
            say = llm.respell_terms(foreign[:40])
            if say:
                text = narration.read_text()
                for term, resp in say.items():
                    if resp and any(ord(c) > 127 for c in term):
                        text = text.replace(term, resp)
                narration.write_text(text)
                (work / "lexicon.json").write_text(json.dumps(say, indent=1, ensure_ascii=False))
                print(f"      llm respelled {len(say)} terms -> lexicon.json")
    print(f"      {nwords} spoken words")

    if args.extract_only:
        print("done (extract only)")
        return

    print("[3/5] synthesise (cached chunks are reused)")
    ref = Path(args.voice)
    ref_text = Path(args.voice_text).read_text().strip() if Path(args.voice_text).exists() else ""
    if not ref.exists():
        sys.exit(f"voice reference missing: {ref}")
    synth_book(str(narration), bid, str(ref), ref_text)

    print("[4/5] normalise")
    wav = AUDIO / f"{bid}.wav"
    if not wav.exists():
        sys.exit("synthesis produced no wav")
    subprocess.run([sys.executable, str(ROOT / "scripts/postprocess.py"),
                    str(wav), title], check=True)

    print("[5/5] cues + manifest")
    LIB.mkdir(exist_ok=True)
    book_dir = LIB / bid
    book_dir.mkdir(exist_ok=True)
    cues = M.build(str(narration), bid)
    json.dump({"tag": bid, "cues": cues}, open(book_dir / "cues_0.json", "w"))
    for ext in (".m4a", ".mp3"):
        f = AUDIO / f"{bid}{ext}"
        if f.exists():
            dest = book_dir / f.name
            if not dest.exists():
                os.symlink(f.resolve(), dest)
            break
    shutil.copy(md, book_dir / "text.md")

    index_path = LIB / "index.json"
    index = json.load(open(index_path)) if index_path.exists() else {"books": []}
    index["books"] = [b for b in index["books"] if b["id"] != bid]
    audio_name = next((f.name for f in book_dir.iterdir() if f.suffix in (".m4a", ".mp3")), "")
    verified = src.suffix.lower() in (".md", ".markdown")
    index["books"].append({
        "id": bid, "title": title, "author": author, "verified": verified,
        "tracks": [{"title": "Full text", "audio": audio_name, "cues": "cues_0.json"}],
    })
    json.dump(index, open(index_path, "w"), indent=1)
    mins = len(cues) and cues[-1]["t1"] / 60
    print(f"\nadded '{title}'  (~{mins:.0f} min, {len(cues)} cues)")
    print(f"listen:  cd glasses-reader && npm run dev   →  /?book={bid}")

if __name__ == "__main__":
    main()

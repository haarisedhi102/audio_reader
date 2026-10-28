import os, subprocess, sys, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from generate_audio import chunks, MODEL
from narrate import display_text

AUDIO = ROOT / "audio"

def dur(path: str) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout)

def build(narration: str, tag: str, model: str = MODEL, gap_block=0.85, gap_sent=0.35) -> list:
    """Rebuild the exact timeline the stitcher produced, from chunk durations."""
    text = Path(narration).read_text()
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    parts = ROOT / "audio" / f"{tag}_{model.split('/')[-1]}_parts"
    cues, t, missing = [], 0.0, 0
    for bi, b in enumerate(blocks):
        if bi:
            t += gap_block
        for ci, c in enumerate(chunks(b)):
            h = hashlib.sha1(c.encode()).hexdigest()[:16]
            p = parts / f"{bi:03d}_{ci:02d}_{h}.wav"
            if not p.exists():
                missing += 1
                continue
            d = dur(str(p))
            cues.append({"t0": round(t, 3), "t1": round(t + d, 3), "text": display_text(c)})
            t += d + gap_sent
    if missing:
        print(f"  warning: {missing} chunks had no audio", file=sys.stderr)
    return cues

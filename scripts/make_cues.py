import json, os, subprocess, sys, hashlib, re
sys.path.insert(0, "/Users/haarisedhi/ocr _to_speech/scripts")
from generate_audio import chunks

AUDIO = "/Users/haarisedhi/ocr _to_speech/audio"
OUT = "/Users/haarisedhi/ocr _to_speech/glasses-reader/src/cues"
os.makedirs(OUT, exist_ok=True)

def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of", "default=nw=1:nk=1", path],
                                capture_output=True, text=True).stdout)

def build(narration, tag, gap_block=0.85, gap_sent=0.35):
    text = open(narration).read()
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    parts = os.path.join(AUDIO, f"{tag}_Breeze-TTS-2-mlx_parts")
    cues, t = [], 0.0
    missing = 0
    for bi, b in enumerate(blocks):
        if bi:
            t += gap_block
        for ci, c in enumerate(chunks(b)):
            h = hashlib.sha1(c.encode()).hexdigest()[:16]
            p = os.path.join(parts, f"{bi:03d}_{ci:02d}_{h}.wav")
            if not os.path.exists(p):
                missing += 1
                continue
            d = dur(p)
            cues.append({"t0": round(t, 3), "t1": round(t + d, 3), "text": c})
            t += d + gap_sent
    json.dump({"tag": tag, "cues": cues}, open(os.path.join(OUT, f"{tag}.json"), "w"))
    print(f"{tag:20s} {len(cues):4d} cues  {t/60:6.1f} min  missing {missing}")

build("/Users/haarisedhi/ocr _to_speech/narration_archer.txt", "archer")
build("/Users/haarisedhi/ocr _to_speech/narration_okculuk.txt", "okculuk")
for p in ["00_intro","01_ch1","02_ch2","03_ch3","04_ch4","05_ch5","06_ch6","07_ch7","08_conclusions"]:
    f = f"/Users/haarisedhi/ocr _to_speech/narration_thesis_{p}.txt"
    if os.path.exists(f):
        build(f, f"thesis_{p}")

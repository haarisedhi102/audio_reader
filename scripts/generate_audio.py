import os, re, sys, hashlib, json, subprocess
import numpy as np
from mlx_audio.tts import load
from mlx_audio.audio_io import write as write_audio

MODEL = os.environ.get("TTS_MODEL", "mlx-community/Breeze-TTS-2-mlx")
CFG = float(os.environ.get("TTS_CFG", "4"))
SEED = int(os.environ.get("TTS_SEED", "42"))
OUT = "/Users/haarisedhi/ocr _to_speech/audio"
os.makedirs(OUT, exist_ok=True)

def chunks(text, limit=240):
    """Sentence-aware chunks under `limit` chars."""
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"'])", text)
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) + 1 <= limit:
            cur = (cur + " " + s).strip()
        else:
            if cur: out.append(cur)
            while len(s) > limit:
                cut = s.rfind(", ", 0, limit)
                cut = cut + 1 if cut > 80 else limit
                out.append(s[:cut].strip()); s = s[cut:].strip()
            cur = s
    if cur: out.append(cur)
    return [c for c in out if c]

def main(txt_path, tag, ref_wav, ref_text, gap_block=0.85, gap_sent=0.35):
    text = open(txt_path).read()
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    workdir = os.path.join(OUT, f"{tag}_{MODEL.split('/')[-1]}_parts")
    os.makedirs(workdir, exist_ok=True)

    model = load(MODEL, strict=True)
    sr = 24000
    pieces = []
    idx = 0
    for bi, b in enumerate(blocks):
        if bi:
            pieces.append(("silence", gap_block))
        for ci, c in enumerate(chunks(b)):
            h = hashlib.sha1(c.encode()).hexdigest()[:16]
            path = os.path.join(workdir, f"{bi:03d}_{ci:02d}_{h}.wav")
            if not os.path.exists(path):
                def synth(t):
                    if "breeze" in MODEL.lower():
                        r = next(model.generate(text=t, ref_audio=ref_wav, ref_text=ref_text,
                                                cfg_scale=CFG, seed=SEED))
                    else:
                        r = next(model.generate(text=t, lang_code="en",
                                                ref_audio=ref_wav, ref_text=ref_text))
                    return r.audio, r.sample_rate
                a, sr = synth(c)
                # repetition guard: audio far longer than the text warrants
                if len(a) / sr > max(6.0, len(c) / 16.0 * 2.2):
                    print(f"[{tag}] retry {bi:03d}.{ci:02d}: {len(a)/sr:.1f}s for {len(c)}ch", flush=True)
                    cut = c.rfind(" ", 0, len(c) // 2)
                    cut = cut if cut > 60 else len(c) // 2
                    a1, sr = synth(c[:cut].strip() + ".")
                    a2, sr = synth(c[cut:].strip())
                    a = np.concatenate([a1, np.zeros(int(sr * 0.3), dtype=np.float32), a2])
                write_audio(path, a, sr)
                print(f"[{tag}] {bi:03d}.{ci:02d} {len(c):3d}ch -> {len(a)/sr:5.1f}s", flush=True)
            pieces.append(("wav", path))
            pieces.append(("silence", gap_sent))
            idx += 1

    # stitch
    audio = []
    for kind, val in pieces:
        if kind == "silence":
            audio.append(np.zeros(int(sr * val), dtype=np.float32))
        else:
            import soundfile as sf
            a, s = sf.read(val, dtype="float32")
            sr = s
            if a.ndim > 1: a = a.mean(axis=1)
            if s != sr:
                raise SystemExit(f"sample rate mismatch {s} != {sr}")
            audio.append(a)
    full = np.concatenate(audio) if audio else np.zeros(1, dtype=np.float32)
    raw = os.path.join(OUT, f"{tag}.wav")
    write_audio(raw, full, sr)
    print(f"[{tag}] stitched {len(full)/sr/60:.1f} min -> {raw}", flush=True)
    return raw

if __name__ == "__main__":
    txt, tag = sys.argv[1], sys.argv[2]
    ref_wav = sys.argv[3]
    ref_text = open(sys.argv[4]).read().strip()
    main(txt, tag, ref_wav, ref_text)

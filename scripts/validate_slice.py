import os, sys, re, difflib
import numpy as np
from mlx_audio.tts import load
from mlx_audio.audio_io import write as write_audio
import mlx_audio.stt as stt

OUT = os.environ["COMMANDCODE_SCRATCHPAD"]
MODEL = "mlx-community/chatterbox-multilingual-v3"
REF = f"{OUT}/tts_test/ref_000.wav"
REFTXT = open(f"{OUT}/ref.txt").read().strip()

sys.path.insert(0, "/Users/haarisedhi/ocr _to_speech/scripts")
from generate_audio import chunks

blocks = [b for b in open("/Users/haarisedhi/ocr _to_speech/narration_okculuk.txt").read().split("\n\n") if b.strip()]
sample = blocks[6:10]

model = load(MODEL, strict=True)
asr = stt.load("mlx-community/whisper-large-v3-turbo-asr-fp16")

def norm(t):
    return re.findall(r"[a-z]+", t.lower())

for bi, b in enumerate(sample):
    for ci, c in enumerate(chunks(b)):
        r = next(model.generate(text=c, lang_code="en", ref_audio=REF, ref_text=REFTXT))
        p = f"{OUT}/tts_test/val_{bi}_{ci}.wav"
        write_audio(p, r.audio, r.sample_rate)
        dur = len(r.audio) / r.sample_rate
        hyp = asr.generate(p).text
        ref, h = norm(c), norm(hyp)
        sim = difflib.SequenceMatcher(None, ref, h, autojunk=False).ratio()
        print(f"[{bi}.{ci}] {len(c):3d}ch {dur:5.1f}s sim={sim:.2f}  {c[:60]}...")
        if sim < 0.75:
            print(f"    HEARD: {hyp[:200]}")

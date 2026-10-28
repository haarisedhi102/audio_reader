import sys, re, difflib, os
sys.path.insert(0, "/Users/haarisedhi/ocr _to_speech/scripts")
from generate_audio import chunks, MODEL, CFG, SEED
from mlx_audio.tts import load
from mlx_audio.audio_io import write as write_audio
import mlx_audio.stt as stt

SCRATCH = os.environ["COMMANDCODE_SCRATCHPAD"]
REF, REFTXT = f"{SCRATCH}/tts_test/ref_000.wav", open(f"{SCRATCH}/ref.txt").read().strip()

text = open("/Users/haarisedhi/ocr _to_speech/narration_thesis_01_ch1.txt").read()
blocks = [b for b in text.split("\n\n") if b.strip()]
sample = []
for b in blocks[4:8]:
    sample.extend(chunks(b))
sample = sample[:8]

model = load(MODEL, strict=True)
asr = stt.load("mlx-community/whisper-large-v3-turbo-asr-fp16")
norm = lambda t: re.findall(r"[a-z]+", t.lower())

for i, c in enumerate(sample):
    r = next(model.generate(text=c, ref_audio=REF, ref_text=REFTXT, cfg_scale=CFG, seed=SEED))
    p = f"{SCRATCH}/tts_test/valb_{i}.wav"
    write_audio(p, r.audio, r.sample_rate)
    dur = len(r.audio) / r.sample_rate
    hyp = asr.generate(p).text
    sim = difflib.SequenceMatcher(None, norm(c), norm(hyp), autojunk=False).ratio()
    flag = "" if sim > 0.8 else "  <-- CHECK"
    print(f"[{i}] {len(c):3d}ch {dur:5.1f}s sim={sim:.2f}{flag}")
    if sim <= 0.8:
        print("    REF:", c[:150])
        print("    HYP:", hyp[:150])

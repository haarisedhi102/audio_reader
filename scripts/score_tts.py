import sys, re, difflib, subprocess, json
import mlx_audio.stt as stt

def norm(t):
    t = t.lower()
    t = re.sub(r"[“”„\"'’]" , "", t)
    t = re.sub(r"[^a-z0-9şğıöüçâîûéèà ]+", " ", t)
    return re.findall(r"\w+", t)

def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    sm = difflib.SequenceMatcher(None, r, h, autojunk=False)
    err = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            err += max(i2 - i1, j2 - j1)
    return err / max(len(r), 1), len(r), len(h)

ref = open(sys.argv[1]).read()
model = stt.load("mlx-community/whisper-large-v3-turbo-asr-fp16")

for path in sys.argv[2:]:
    out = model.generate(path)
    text = out.text if hasattr(out, "text") else str(out)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout)
    e, nr, nh = wer(ref, text)
    print(f"{path.split('/')[-1]:22s} dur={dur:6.2f}s wer={e*100:5.1f}% words={nh}/{nr}")
    print("   heard:", text.strip()[:220])

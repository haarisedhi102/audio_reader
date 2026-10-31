"""Synthesise narration with Fish (base) and Eleven (fallback), in parallel."""
import os
import re
import sys
import json
import hashlib
import subprocess
import threading
import time
import urllib.error
import concurrent.futures as cf

import numpy as np
from mlx_audio.audio_io import write as write_audio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio")
os.makedirs(OUT, exist_ok=True)

MODEL = os.environ.get("TTS_MODEL", "fish")
FALLBACK_MODEL = os.environ.get("TTS_FALLBACK", "eleven")

_ENV_CACHE = None


def _env_file():
    """Parse .env once: strip `export`, quotes and inline comments."""
    global _ENV_CACHE
    if _ENV_CACHE is None:
        _ENV_CACHE = {}
        path = os.path.join(ROOT, ".env")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:].strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
                    v = v.strip('"').strip("'")
                    _ENV_CACHE[k.strip()] = v
    return _ENV_CACHE


def _env(name):
    v = os.environ.get(name)
    if v:
        return v
    return _env_file().get(name)


class TTSError(RuntimeError):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def _retryable(e):
    """Only 408, 429, 5xx and transport errors are worth another attempt."""
    if isinstance(e, TTSError):
        s = e.status
        return s is not None and (s in (408, 429) or 500 <= s < 600)
    return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def _decode_mp3(data):
    with __import__("tempfile").NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", tmp, "-f", "f32le",
             "-ac", "1", "-ar", "24000", "-"],
            check=True, capture_output=True).stdout
    finally:
        os.unlink(tmp)
    return np.frombuffer(raw, dtype=np.float32).copy(), 24000


def eleven_speech(text):
    import json, urllib.request
    key = _env("ELEVEN_KEY") or _env("ELEVENLABS_API_KEY")
    voice = _env("ELEVEN_VOICE_ID") or "JBFqnCBsd6RMkjVDRZzb"
    model = _env("ELEVEN_MODEL") or "eleven_v4_turbo"
    if not key:
        raise TTSError("ELEVEN_KEY missing from environment and .env")
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
           "?output_format=mp3_44100_128")
    req = urllib.request.Request(
        url, data=json.dumps({"text": text, "model_id": model}).encode(),
        method="POST", headers={"xi-api-key": key, "Content-Type": "application/json",
                                "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise TTSError(f"eleven {e.code}: {e.read().decode(errors='replace')[:300]}", e.code)
    return _decode_mp3(data)


def fish_speech(text):
    import json, urllib.request
    key = _env("FISH_KEY") or _env("FISH_API_KEY")
    voice = _env("FISH_VOICE_ID")
    model = _env("FISH_MODEL") or "s2.1-pro-free"
    if not key or not voice:
        raise TTSError("FISH_KEY / FISH_VOICE_ID missing from environment and .env")
    req = urllib.request.Request(
        "https://api.fish.audio/v1/tts",
        data=json.dumps({"text": text, "reference_id": voice, "format": "mp3"}).encode(),
        method="POST", headers={"Authorization": f"Bearer {key}",
                                "Content-Type": "application/json", "model": model})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise TTSError(f"fish {e.code}: {e.read().decode(errors='replace')[:300]}", e.code)
    return _decode_mp3(data)


LIGATURES = str.maketrans({
    "\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi",
    "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
})
MATH_RE = re.compile(r"[±≈№π×÷=+<>≤≥√∞]")


def has_non_english(text):
    """Any non-Latin letter after ligatures are folded to plain ASCII."""
    text = text.translate(LIGATURES)
    return any(ord(c) > 127 and c.isalpha() for c in text)


def needs_fallback(text):
    return bool(MATH_RE.search(text) or has_non_english(text))


ABBREV = {"dr.", "st.", "mr.", "mrs.", "ms.", "prof.", "fig.", "figs.",
          "no.", "p.", "pp.", "vs.", "etc.", "cf.", "al.", "e.g.", "i.e."}


def split_sentences(text):
    """Split on ., !, ? followed by whitespace and a new sentence."""
    out, start = [], 0
    for m in re.finditer(r"[.!?][\"\u201d\u2019']?(?=\s+)", text):
        rest = text[m.end():]
        nxt = rest.lstrip()[:1]
        if not nxt:
            continue
        if not (nxt.isupper() or nxt in "\u201c\u2018\"'"):
            continue
        head = text[start:m.end()]
        last = head.split()[-1].lower().strip("\u201c\u201d\u2018\u2019\"'") if head.split() else ""
        if last in ABBREV or (len(last) == 2 and last[0].isalpha() and last.endswith(".")):  # "J."
            continue
        out.append(head.strip())
        start = m.end() + (len(rest) - len(rest.lstrip()))
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def chunks(text, limit=240):
    """Sentence-aware chunks under `limit` chars, cutting on word boundaries."""
    sents = split_sentences(text)
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) + 1 <= limit:
            cur = (cur + " " + s).strip()
        else:
            if cur:
                out.append(cur)
            while len(s) > limit:
                cut = s.rfind(", ", 0, limit)
                if cut > 80:
                    cut = cut + 1
                else:
                    cut = s.rfind(" ", 0, limit)
                if cut <= 0:
                    cut = limit
                out.append(s[:cut].strip())
                s = s[cut:].strip()
            cur = s
    if cur:
        out.append(cur)
    return [c for c in out if c]


FISH_PAR = max(1, int(os.environ.get("TTS_CONCURRENCY", "6")))
ELEVEN_PAR = max(1, int(os.environ.get("TTS_ELEVEN_CONCURRENCY", "2")))
_SEMAPHORES = {"fish": threading.Semaphore(FISH_PAR),
               "eleven": threading.Semaphore(ELEVEN_PAR)}


def engine_for(text, base=None):
    base = (base or MODEL).lower()
    if FALLBACK_MODEL and needs_fallback(text):
        return "eleven"
    return "fish" if base.startswith("fish") else "eleven"


def _engine_sig(engine):
    if engine == "fish":
        return f"fish|{_env('FISH_VOICE_ID')}|{_env('FISH_MODEL') or 's2.1-pro-free'}"
    return f"eleven|{_env('ELEVEN_VOICE_ID') or 'JBFqnCBsd6RMkjVDRZzb'}|{_env('ELEVEN_MODEL') or 'eleven_v4_turbo'}"


def parts_dir(tag, model=None):
    model = model or MODEL
    return os.path.join(OUT, f"{tag}_{model.split('/')[-1]}_parts")


def chunk_path(workdir, text, engine=None):
    """Cache key is engine|voice+model|text — independent of block/chunk index."""
    engine = engine or engine_for(text)
    key = hashlib.sha1(f"{_engine_sig(engine)}|{text}".encode()).hexdigest()[:16]
    return os.path.join(workdir, f"{key}.wav")


def _postprocess(a, sr):
    """Trim edge silence and normalise loudness so engine joins sit evenly."""
    a = np.asarray(a, dtype=np.float32)
    if a.ndim > 1:
        a = a.mean(axis=1)
    if a.size == 0:
        return a
    peak = float(np.max(np.abs(a)))
    if peak > 0:
        idx = np.flatnonzero(np.abs(a) > peak * 0.02)
        if idx.size:
            a = a[idx[0]:idx[-1] + 1]
    if a.size:
        rms = float(np.sqrt(np.mean(a * a)))
        peak = float(np.max(np.abs(a)))
        if rms > 0 and peak > 0:
            gain = min(0.06 / rms, 0.97 / peak)
            a = np.clip(a * gain, -1.0, 1.0).astype(np.float32)
    return a


def main(txt_path, tag, gap_block=0.85, gap_sent=0.35):
    with open(txt_path, encoding="utf-8") as f:
        text = f.read()
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    base = MODEL.lower()
    if not (base.startswith("fish") or base.startswith("eleven")):
        raise SystemExit(f"unsupported TTS_MODEL: {MODEL}")

    workdir = parts_dir(tag)
    os.makedirs(workdir, exist_ok=True)

    def synth(t, engine):
        with _SEMAPHORES[engine]:
            a, sr = fish_speech(t) if engine == "fish" else eleven_speech(t)
        return a, sr

    def synth_one(job):
        bi, ci, c, path, engine = job
        try:
            def render(t):
                a, sr = None, 24000
                for attempt in range(4):
                    try:
                        a, sr = synth(t, engine)
                        break
                    except Exception as e:
                        if attempt == 3 or not _retryable(e):
                            raise
                        time.sleep(1.5 * (2 ** attempt))
                if a is None or len(a) == 0:
                    raise TTSError(f"empty decode for {bi:03d}.{ci:02d}")
                a = _postprocess(a, sr)
                dur = len(a) / sr
                if dur < max(0.15, len(t) / 45.0):
                    raise TTSError(f"short decode {dur:.2f}s for {len(t)}ch at {bi:03d}.{ci:02d}")
                return a, sr

            a, sr = render(c)
            if len(a) / sr > max(6.0, len(c) / 16.0 * 2.2):
                print(f"[{tag}] retry {bi:03d}.{ci:02d}: {len(a)/sr:.1f}s for {len(c)}ch", flush=True)
                cut = c.rfind(" ", 0, len(c) // 2)
                cut = cut if cut > 60 else len(c) // 2
                a1, sr = render(c[:cut].strip() + ".")
                a2, _ = render(c[cut:].strip())
                a = np.concatenate([a1, np.zeros(int(sr * 0.3), dtype=np.float32), a2])
            tmp = path + ".part.wav"
            write_audio(tmp, a, sr)
            os.replace(tmp, path)
            return bi, ci, len(c), len(a) / sr
        except Exception as e:
            raise RuntimeError(f"chunk {bi:03d}.{ci:02d} failed: {e}") from e

    sr = 24000
    pieces, jobs = [], []
    for bi, b in enumerate(blocks):
        if bi:
            pieces.append(("silence", gap_block))
        for ci, c in enumerate(chunks(b)):
            if ci:                                     # gap between chunks only
                pieces.append(("silence", gap_sent))
            engine = engine_for(c, base)
            path = chunk_path(workdir, c, engine)
            pieces.append(("wav", path, c, engine))
            if not os.path.exists(path):
                jobs.append((bi, ci, c, path, engine))

    workers = max(1, FISH_PAR + ELEVEN_PAR)
    if jobs and workers > 1:
        ex = cf.ThreadPoolExecutor(max_workers=workers)
        futs = [ex.submit(synth_one, j) for j in jobs]
        try:
            for f in cf.as_completed(futs):
                bi, ci, ch, d = f.result()
                print(f"[{tag}] {bi:03d}.{ci:02d} {ch:3d}ch -> {d:5.1f}s", flush=True)
        except BaseException as e:
            ex.shutdown(wait=False, cancel_futures=True)
            print(f"[{tag}] aborted: {e}", file=sys.stderr, flush=True)
            raise
        else:
            ex.shutdown(wait=False)
    else:
        for j in jobs:
            bi, ci, ch, d = synth_one(j)
            print(f"[{tag}] {bi:03d}.{ci:02d} {ch:3d}ch -> {d:5.1f}s", flush=True)

    audio, cues, t = [], [], 0.0
    for piece in pieces:
        if piece[0] == "silence":
            n = int(sr * piece[1])
            audio.append(np.zeros(n, dtype=np.float32))
            t += n / sr
        else:
            _, val, c, engine = piece
            import soundfile as sf
            a, s = sf.read(val, dtype="float32")
            sr = s
            if a.ndim > 1:
                a = a.mean(axis=1)
            audio.append(a)
            d = len(a) / sr
            cues.append({"t0": round(t, 3), "t1": round(t + d, 3),
                         "text": c, "engine": engine})
            t += d
    full = np.concatenate(audio) if audio else np.zeros(1, dtype=np.float32)
    raw = os.path.join(OUT, f"{tag}.wav")
    write_audio(raw, full, sr)
    manifest = os.path.join(OUT, f"{tag}.cues.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(cues, f, ensure_ascii=False, indent=1)
    print(f"[{tag}] stitched {len(full)/sr/60:.1f} min -> {raw}", flush=True)
    return raw


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("txt")
    ap.add_argument("tag")
    a = ap.parse_args()
    main(a.txt, a.tag)

import subprocess, sys, os, re, json

src, title = sys.argv[1], sys.argv[2]
fmt = sys.argv[3] if len(sys.argv) > 3 else "m4a"
codec = sys.argv[4] if len(sys.argv) > 4 else "aac_at"
base = os.path.splitext(src)[0]
out = f"{base}.{fmt}"

# Pass 1: measure loudness once (full decode — unavoidable, ~60x realtime).
p = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                   capture_output=True, text=True)
m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
if not m:
    sys.exit("loudness analysis failed")

meas = json.loads(m.group(0))
gain = -16.0 - float(meas["input_i"])          # linear gain to hit -16 LUFS
tp = float(meas["input_tp"])
if tp + gain > -1.5:                            # never clip the true peak
    gain = -1.5 - tp
gain = max(-30.0, min(30.0, gain))

# Pass 2: encode once, applying that gain statically. A static gain preserves
# the performance exactly like two-pass loudnorm's linear mode, at ~1/5 the cost
# of the dynamic filter.
enc = ["-c:a", "aac_at", "-b:a", "192k"] if codec == "aac_at" else \
      ["-c:a", "libmp3lame", "-b:a", "192k"]

subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                "-af", f"volume={gain:.2f}dB", "-ar", "44100", "-ac", "1",
                *enc, "-metadata", f"title={title}", out], check=True)

print(f"{out}  gain={gain:+.2f} dB  {os.path.getsize(out)/1e6:.1f} MB")

#!/bin/bash
set -u
cd "/Users/haarisedhi/ocr _to_speech"
SRC="${1:-audio/thesis_08_conclusions.wav}"
OUT=/tmp/bench
mkdir -p $OUT

run () {  # $1 label, rest: ffmpeg args
  local label="$1"; shift
  local start=$(python3 -c 'import time;print(time.time())')
  ffmpeg -y -hide_banner -loglevel error "$@" >/dev/null 2>&1
  local end=$(python3 -c 'import time;print(time.time())')
  local size=$(stat -f%z "$LASTOUT" 2>/dev/null || echo 0)
  printf "%-46s %6.1fs  %5.1f MB\n" "$label" "$(python3 -c "print($end-$start)")" "$(python3 -c "print($size/1e6)")"
}

echo "source: $SRC  ($(python3 -c "import os;print(round(os.path.getsize('$SRC')/1e6,1))") MB)"

# 1. analysis pass (what postprocess.py does first)
LASTOUT=/dev/null
run "loudnorm analysis pass (full decode)" -i "$SRC" -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -

# 2. each encoding strategy
LASTOUT=$OUT/a.mp3
run "mp3 + 2-pass loudnorm" -i "$SRC" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -ac 1 -c:a libmp3lame -b:a 192k $OUT/a.mp3

LASTOUT=$OUT/b.m4a
run "aac (ffmpeg software) + 2-pass loudnorm" -i "$SRC" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -ac 1 -c:a aac -b:a 192k $OUT/b.m4a

LASTOUT=$OUT/c.m4a
run "aac_at (AudioToolbox) + 2-pass loudnorm" -i "$SRC" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -ac 1 -c:a aac_at -b:a 192k $OUT/c.m4a

LASTOUT=$OUT/d.m4a
run "aac_at + single-pass loudnorm" -i "$SRC" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -ac 1 -c:a aac_at -b:a 192k $OUT/d.m4a

LASTOUT=$OUT/e.m4a
run "aac_at only (no filter)" -i "$SRC" -ar 44100 -ac 1 -c:a aac_at -b:a 192k $OUT/e.m4a

echo
for f in $OUT/*.m4a $OUT/*.mp3; do
  [ -f "$f" ] || continue
  echo "$(basename $f): $(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f")s  $(du -h "$f" | cut -f1)"
done

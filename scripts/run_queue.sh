#!/bin/bash
set -u
cd "/Users/haarisedhi/ocr _to_speech"
export TTS_MODEL="mlx-community/Breeze-TTS-2-mlx"
SCRATCH="$COMMANDCODE_SCRATCHPAD"
REF="$SCRATCH/tts_test/ref_000.wav"
REFTXT="$SCRATCH/ref.txt"
PY=.venv-tts/bin/python

run () {  # $1 narration basename, $2 tag, $3 title
  [ -f "audio/$2.mp3" ] && { echo "skip $2 (done)"; return; }
  echo "=== $2 ==="
  $PY scripts/generate_audio.py "narration_$1.txt" "$2" "$REF" "$REFTXT" || { echo "FAILED $2"; return; }
  [ -f "audio/$2.wav" ] && $PY scripts/postprocess.py "audio/$2.wav" "$3"
}

run archer  archer  "A Turkish Archer On The Tracks Of His Ancestors"
run okculuk okculuk "Archery and the Art of Calligraphy"

for part in 00_intro 01_ch1 02_ch2 03_ch3 04_ch4 05_ch5 06_ch6 07_ch7 08_conclusions; do
  run "thesis_$part" "thesis_$part" "The Spiritual in Islamic Calligraphy — $part"
done

if [ ! -f audio/thesis.mp3 ]; then
  echo "=== stitching thesis ==="
  : > /tmp/thesis_concat.txt
  for part in 00_intro 01_ch1 02_ch2 03_ch3 04_ch4 05_ch5 06_ch6 07_ch7 08_conclusions; do
    f="audio/thesis_$part.wav"
    [ -f "$f" ] && printf "file '%s'\n" "$PWD/$f" >> /tmp/thesis_concat.txt
  done
  ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i /tmp/thesis_concat.txt \
         -c copy audio/thesis_raw.wav && \
  $PY scripts/postprocess.py audio/thesis_raw.wav "The Spiritual in Islamic Calligraphy"
fi
echo "QUEUE COMPLETE"

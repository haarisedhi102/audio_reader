# Glasses Reader — synced teleprompter for Even Realities G2

Reads the generated narration aloud on your phone and scrolls the matching text on
the G2 display, in step with the audio.

## Why this beats the built-in teleprompter

The stock teleprompter listens through the phone microphone and guesses where you
are, so it drifts, lags, and fails in a quiet room or when you skip ahead.

Here the clock is the audio itself. Every sentence has a start/end timestamp
produced during speech synthesis, so the display position is derived from
`audio.currentTime` — no microphone, no ASR, no feedback loop:

```
narration text ──► TTS chunks ──► per-chunk WAVs ──► durations
                                        │
                        cues.json {t0,t1,text}
                                        │
   phone audio element ──► currentTime ──┴──► current cue ──► line window ──► glasses
```

A seek, a skip, a pause — the text follows exactly, because it is a function of
time, not of listening.

## Run it

```bash
cd glasses-reader
npm install

# desktop simulator
npm run dev
npx evenhub-simulator http://localhost:5173

# on real glasses: scan this with the Even Hub app on your phone
npx @evenrealities/evenhub-cli qr --url http://<your-lan-ip>:5173
```

The phone must be on the same Wi-Fi as the Mac, and `npm run dev` must keep
running: audio and cues stream from it.

### Packed build

A packed app runs from the app origin, not the dev server, so point the library
at the Mac when building:

```bash
VITE_LIB_BASE=http://<your-lan-ip>:5173/library npm run build
npx @evenrealities/evenhub-cli pack app.json dist -o glasses-reader.ehpk
npx @evenrealities/evenhub-cli create glasses-reader.ehpk --name Reader --tagline "Read along on your glasses"
```

The dev server sets CORS on `/library` and `/audio` so the packed app can read
them.

Useful query params: `?book=thesis&track=2&seek=300`
(`book` is `archer`, `okculuk`, or `thesis`; `track` is 0-based).

## Controls

| Input | Action |
|---|---|
| Tap | play / pause |
| Swipe up / down | seek −30 s / +30 s |
| Long-press | hide/show the text — playback continues; any tap brings it back |
| Menu (from the glasses' own long-press) | Hide text / Show text / Exit — the phone's `hide` button always works, even if the OS claims the press |
| Double-tap | exit |

## Layout on the glasses

576×288, 4-bit green. Header shows position, body shows seven 27 px lines with the
spoken line marked `>`, footer holds the control hints. Text is wrapped with
`@evenrealities/pretext`, whose metrics mirror LVGL's on the device, so a line that
fits in the simulator fits on hardware.

## Regenerating the cues

Cues are produced from the TTS chunk WAVs, so timings are exact rather than
estimated:

```bash
# in the repo root, with the TTS venv
.venv-tts/bin/python scripts/make_cues.py     # writes glasses-reader/src/cues/*.json
```

Each cue is one synthesized chunk (~1–2 sentences). Line-level movement inside a
long cue is interpolated from within-cue progress.

## Audio

`vite.config.ts` serves `../audio` at `/audio` with HTTP range support, so seeking
works and nothing is duplicated into `dist`. To run the packaged app on a phone,
host the MP3s somewhere reachable and build with:

```bash
VITE_AUDIO_BASE=https://your-host/audio npm run build
```

## Headless test

```bash
evenhub-simulator http://localhost:5173 --automation-port 9898 &
node scripts/smoke.mjs
```

Asserts boot, rendering, that the audio clock advances the display, and that
double-tap exits.

## Known simulator quirk

A small 4×14 px mark sits at the top-right of the framebuffer in the simulator. It
is present even with a single-line body and no header text, so it is simulator
chrome, not this app's layout. Confirm on hardware during beta testing.
